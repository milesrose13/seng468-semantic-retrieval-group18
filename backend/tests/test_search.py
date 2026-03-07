"""
Tests for GET /search?q=<query>

- Qdrant replaced by unittest.mock (search_embeddings)
- Auth handled the same way as test_documents.py
"""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from pwdlib import PasswordHash
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import storage, vector
from backend.app.database import Base, get_db  # noqa: F401
from backend.app.main import app
from backend.app.models.user import User

# ---------------------------------------------------------------------------
# Test database — SQLite in-memory via StaticPool
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


SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
password_hash = PasswordHash.recommended()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    with patch.object(storage, "ensure_bucket_exists"):
        with TestClient(app) as c:
            yield c
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


def _create_user_and_token(username: str) -> tuple[str, int]:
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


FAKE_RESULTS = [
    {
        "text": "The quick brown fox",
        "score": 0.95,
        "document_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "filename": "doc1.pdf",
    },
    {
        "text": "Jumped over the lazy dog",
        "score": 0.82,
        "document_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "filename": "doc2.pdf",
    },
]


# ---------------------------------------------------------------------------
# GET /search
# ---------------------------------------------------------------------------


class TestSearch:
    def test_requires_auth(self, client):
        resp = client.get("/search?q=hello")
        assert resp.status_code in (401, 403)

    def test_invalid_token(self, client):
        resp = client.get(
            "/search?q=hello",
            headers={"Authorization": "Bearer bad-token"},
        )
        assert resp.status_code == 401

    def test_returns_results(self, client):
        token, _ = _create_user_and_token("search_user1")
        with patch.object(vector, "search_embeddings", return_value=FAKE_RESULTS):
            resp = client.get("/search?q=fox", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["text"] == "The quick brown fox"
        assert data[0]["score"] == 0.95

    def test_result_fields_present(self, client):
        token, _ = _create_user_and_token("search_user2")
        with patch.object(vector, "search_embeddings", return_value=FAKE_RESULTS):
            resp = client.get("/search?q=fox", headers=_auth(token))
        assert resp.status_code == 200
        for item in resp.json():
            assert "text" in item
            assert "score" in item
            assert "document_id" in item
            assert "filename" in item

    def test_results_sorted_by_score_descending(self, client):
        token, _ = _create_user_and_token("search_user3")
        with patch.object(vector, "search_embeddings", return_value=FAKE_RESULTS):
            resp = client.get("/search?q=fox", headers=_auth(token))
        scores = [r["score"] for r in resp.json()]
        assert scores == sorted(scores, reverse=True)

    def test_empty_results(self, client):
        token, _ = _create_user_and_token("search_user4")
        with patch.object(vector, "search_embeddings", return_value=[]):
            resp = client.get("/search?q=nothing", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_search_called_with_correct_user_id(self, client):
        token, user_id = _create_user_and_token("search_user5")
        with patch.object(vector, "search_embeddings", return_value=[]) as mock_search:
            client.get("/search?q=test", headers=_auth(token))
            mock_search.assert_called_once_with("test", user_id, limit=5)

    def test_max_five_results(self, client):
        token, _ = _create_user_and_token("search_user6")
        many_results = [
            {
                "text": f"result {i}",
                "score": 1.0 - i * 0.1,
                "document_id": f"doc-{i}",
                "filename": f"file{i}.pdf",
            }
            for i in range(5)
        ]
        with patch.object(vector, "search_embeddings", return_value=many_results):
            resp = client.get("/search?q=test", headers=_auth(token))
        assert len(resp.json()) <= 5
