"""
Tests for document management endpoints:
  POST   /documents
  GET    /documents
  DELETE /documents/{id}
"""

import io
import os

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from pwdlib import PasswordHash
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models.user import User

# ---------------------------------------------------------------------------
# Test database — SQLite in-memory via StaticPool (single shared connection)
# ---------------------------------------------------------------------------
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
password_hash = PasswordHash.recommended()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)


def _create_user_and_token(username: str) -> tuple[str, int]:
    """Insert a user directly and return a valid JWT token + user id."""
    db = TestingSessionLocal()
    try:
        user = User(
            username=username,
            hashed_password=password_hash.hash("irrelevant"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    finally:
        db.close()

    token = jwt.encode({"sub": username}, SECRET_KEY, algorithm=ALGORITHM)
    return token, user_id


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _pdf(name: str = "test.pdf"):
    return ("file", (name, io.BytesIO(b"%PDF-1.4 fake"), "application/pdf"))


# ---------------------------------------------------------------------------
# POST /documents
# ---------------------------------------------------------------------------


class TestUpload:
    def test_requires_auth(self, client):
        resp = client.post("/documents", files=[_pdf()])
        assert resp.status_code in (401, 403)

    def test_invalid_token(self, client):
        resp = client.post(
            "/documents",
            files=[_pdf()],
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert resp.status_code == 401

    def test_accepts_pdf(self, client):
        token, _ = _create_user_and_token("upload_user1")
        resp = client.post("/documents", files=[_pdf()], headers=_auth(token))
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "processing"
        assert data["message"] == "PDF uploaded, processing started"
        assert "document_id" in data

    def test_returns_valid_uuid(self, client):
        import uuid

        token, _ = _create_user_and_token("upload_user2")
        resp = client.post("/documents", files=[_pdf()], headers=_auth(token))
        assert resp.status_code == 202
        uuid.UUID(resp.json()["document_id"])  # raises if invalid

    def test_rejects_non_pdf(self, client):
        token, _ = _create_user_and_token("upload_user3")
        bad_file = ("file", ("notes.txt", io.BytesIO(b"hello"), "text/plain"))
        resp = client.post("/documents", files=[bad_file], headers=_auth(token))
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /documents
# ---------------------------------------------------------------------------


class TestList:
    def test_requires_auth(self, client):
        resp = client.get("/documents")
        assert resp.status_code in (401, 403)

    def test_empty_for_new_user(self, client):
        token, _ = _create_user_and_token("list_user1")
        resp = client.get("/documents", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_shows_uploaded_documents(self, client):
        token, _ = _create_user_and_token("list_user2")
        h = _auth(token)
        client.post("/documents", files=[_pdf("a.pdf")], headers=h)
        client.post("/documents", files=[_pdf("b.pdf")], headers=h)

        resp = client.get("/documents", headers=h)
        assert resp.status_code == 200
        docs = resp.json()
        assert len(docs) == 2
        assert {d["filename"] for d in docs} == {"a.pdf", "b.pdf"}

    def test_document_fields_present(self, client):
        token, _ = _create_user_and_token("list_user3")
        h = _auth(token)
        client.post("/documents", files=[_pdf("check.pdf")], headers=h)

        doc = client.get("/documents", headers=h).json()[0]
        assert "document_id" in doc
        assert "filename" in doc
        assert "upload_date" in doc
        assert doc["status"] == "processing"
        assert "page_count" in doc

    def test_user_isolation(self, client):
        token_a, _ = _create_user_and_token("iso_a")
        token_b, _ = _create_user_and_token("iso_b")

        client.post("/documents", files=[_pdf("private.pdf")], headers=_auth(token_a))

        resp = client.get("/documents", headers=_auth(token_b))
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# DELETE /documents/{id}
# ---------------------------------------------------------------------------


class TestDelete:
    def test_requires_auth(self, client):
        import uuid

        resp = client.delete(f"/documents/{uuid.uuid4()}")
        assert resp.status_code in (401, 403)

    def test_delete_own_document(self, client):
        token, _ = _create_user_and_token("del_user1")
        h = _auth(token)

        doc_id = client.post("/documents", files=[_pdf()], headers=h).json()[
            "document_id"
        ]

        resp = client.delete(f"/documents/{doc_id}", headers=h)
        assert resp.status_code == 200

        docs = client.get("/documents", headers=h).json()
        assert not any(d["document_id"] == doc_id for d in docs)

    def test_delete_not_found(self, client):
        import uuid

        token, _ = _create_user_and_token("del_user2")
        resp = client.delete(f"/documents/{uuid.uuid4()}", headers=_auth(token))
        assert resp.status_code == 404

    def test_cannot_delete_other_users_document(self, client):
        token_a, _ = _create_user_and_token("del_owner")
        token_b, _ = _create_user_and_token("del_thief")

        doc_id = client.post(
            "/documents", files=[_pdf()], headers=_auth(token_a)
        ).json()["document_id"]

        resp = client.delete(f"/documents/{doc_id}", headers=_auth(token_b))
        assert resp.status_code == 404

        # Owner still has the doc
        docs = client.get("/documents", headers=_auth(token_a)).json()
        assert any(d["document_id"] == doc_id for d in docs)
