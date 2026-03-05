"""
Tests for document management endpoints:
  POST   /documents
  GET    /documents
  DELETE /documents/{id}

MinIO/S3 is replaced by moto's in-process fake — no real object storage needed.
"""

import io
import os

import boto3
import pytest
from fastapi.testclient import TestClient
from jose import jwt
from moto import mock_aws
from pwdlib import PasswordHash
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import storage
from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models.user import User

# ---------------------------------------------------------------------------
# Ensure moto intercepts boto3 (no real endpoint during tests)
# ---------------------------------------------------------------------------
os.environ.pop("MINIO_ENDPOINT", None)
os.environ["MINIO_ACCESS_KEY"] = "test"
os.environ["MINIO_SECRET_KEY"] = "test"
os.environ["MINIO_BUCKET"] = "documents"

# Reload the module-level constants in storage so the env changes above apply
storage.MINIO_ENDPOINT = None
storage.MINIO_ACCESS_KEY = "test"
storage.MINIO_SECRET_KEY = "test"
storage.MINIO_BUCKET = "documents"

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
def aws_mock():
    """Start moto's fake S3 for the entire test module."""
    with mock_aws():
        # Create the bucket once — mirrors what ensure_bucket_exists() does at startup
        boto3.client(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test",
        ).create_bucket(Bucket="documents")
        yield


@pytest.fixture(scope="module")
def client(aws_mock):
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)


def _s3():
    """Direct boto3 client for asserting bucket state in tests."""
    return boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def _create_user_and_token(username: str) -> tuple[str, int]:
    """Insert a user directly and return a valid JWT + user id."""
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


def _bucket_keys() -> list[str]:
    """Return all object keys currently in the moto bucket."""
    resp = _s3().list_objects_v2(Bucket="documents")
    return [obj["Key"] for obj in resp.get("Contents", [])]


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

    def test_file_stored_in_s3(self, client):
        """After upload, the object must exist in the fake S3 bucket."""
        token, _ = _create_user_and_token("upload_s3_user")
        resp = client.post(
            "/documents", files=[_pdf("stored.pdf")], headers=_auth(token)
        )
        assert resp.status_code == 202

        doc_id = resp.json()["document_id"]
        keys = _bucket_keys()
        assert any(doc_id in k for k in keys), f"{doc_id} not found in bucket: {keys}"

    def test_file_content_preserved(self, client):
        """The bytes stored in S3 must match what was uploaded."""
        token, _ = _create_user_and_token("upload_content_user")
        content = b"%PDF-1.4 this is the real content"
        file = ("file", ("real.pdf", io.BytesIO(content), "application/pdf"))

        resp = client.post("/documents", files=[file], headers=_auth(token))
        doc_id = resp.json()["document_id"]

        key = next(k for k in _bucket_keys() if doc_id in k)
        body = _s3().get_object(Bucket="documents", Key=key)["Body"].read()
        assert body == content


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

    def test_delete_removes_object_from_s3(self, client):
        """After delete, the object must be gone from the fake S3 bucket."""
        token, _ = _create_user_and_token("del_s3_user")
        h = _auth(token)

        doc_id = client.post("/documents", files=[_pdf()], headers=h).json()[
            "document_id"
        ]
        assert any(doc_id in k for k in _bucket_keys())

        client.delete(f"/documents/{doc_id}", headers=h)
        assert not any(doc_id in k for k in _bucket_keys())

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
