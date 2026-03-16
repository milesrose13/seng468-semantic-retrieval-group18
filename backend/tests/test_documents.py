"""
Tests for document management endpoints:
  POST   /documents
  GET    /documents
  DELETE /documents/{id}

- MinIO/S3 replaced by moto's in-process fake
- RabbitMQ replaced by unittest.mock (publish_job)
- Qdrant replaced by unittest.mock (delete_embeddings)
"""

import io
import os
from unittest.mock import patch

import boto3
import jwt
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pwdlib import PasswordHash
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import queue, storage, vector
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

storage.MINIO_ENDPOINT = None
storage.MINIO_ACCESS_KEY = "test"
storage.MINIO_SECRET_KEY = "test"
storage.MINIO_BUCKET = "documents"

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
def aws_mock():
    """Start moto's fake S3 for the entire test module."""
    with mock_aws():
        boto3.client(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test",
        ).create_bucket(Bucket="documents")
        yield


@pytest.fixture(scope="module")
def client(aws_mock):
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    with (
        patch.object(storage, "ensure_bucket_exists"),
        patch.object(queue, "publish_job"),
        patch.object(vector, "delete_embeddings"),
    ):
        with TestClient(app) as c:
            yield c
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


def _s3():
    return boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


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


def _pdf(name: str = "test.pdf"):
    return ("file", (name, io.BytesIO(b"%PDF-1.4 fake"), "application/pdf"))


def _bucket_keys() -> list[str]:
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
        uuid.UUID(resp.json()["document_id"])

    def test_rejects_non_pdf(self, client):
        token, _ = _create_user_and_token("upload_user3")
        bad_file = ("file", ("notes.txt", io.BytesIO(b"hello"), "text/plain"))
        resp = client.post("/documents", files=[bad_file], headers=_auth(token))
        assert resp.status_code == 400

    def test_file_stored_in_s3(self, client):
        token, _ = _create_user_and_token("upload_s3_user")
        resp = client.post(
            "/documents", files=[_pdf("stored.pdf")], headers=_auth(token)
        )
        assert resp.status_code == 202
        doc_id = resp.json()["document_id"]
        keys = _bucket_keys()
        assert any(doc_id in k for k in keys), f"{doc_id} not found in bucket: {keys}"

    def test_file_content_preserved(self, client):
        token, _ = _create_user_and_token("upload_content_user")
        content = b"%PDF-1.4 this is the real content"
        file = ("file", ("real.pdf", io.BytesIO(content), "application/pdf"))

        resp = client.post("/documents", files=[file], headers=_auth(token))
        doc_id = resp.json()["document_id"]

        key = next(k for k in _bucket_keys() if doc_id in k)
        body = _s3().get_object(Bucket="documents", Key=key)["Body"].read()
        assert body == content

    def test_job_published_to_queue(self, client):
        """publish_job must be called with the correct document_id and storage_key."""
        token, _ = _create_user_and_token("upload_queue_user")
        with patch.object(queue, "publish_job") as mock_publish:
            resp = client.post("/documents", files=[_pdf()], headers=_auth(token))
            assert resp.status_code == 202
            doc_id = resp.json()["document_id"]
            mock_publish.assert_called_once()
            call_kwargs = mock_publish.call_args
            assert call_kwargs[0][0] == doc_id  # first positional arg is document_id
            assert doc_id in call_kwargs[0][1]  # storage_key contains the doc_id

    def test_db_record_committed_before_queue_publish(self, client):
        """DB record with status=processing must exist before publish_job is called."""
        import uuid as uuid_mod

        from backend.app.models.document import Document, DocumentStatus

        token, _ = _create_user_and_token("upload_order_user")
        committed_statuses = []

        def capture_then_publish(doc_id, storage_key, user_id):
            # Open a fresh session to verify the commit happened before this call
            db = TestingSessionLocal()
            try:
                doc = (
                    db.query(Document)
                    .filter(Document.id == uuid_mod.UUID(doc_id))
                    .first()
                )
                committed_statuses.append(doc.status if doc else None)
            finally:
                db.close()

        with patch.object(queue, "publish_job", side_effect=capture_then_publish):
            resp = client.post("/documents", files=[_pdf()], headers=_auth(token))

        assert resp.status_code == 202
        assert committed_statuses == [DocumentStatus.PROCESSING]

    def test_queue_failure_returns_500_and_marks_error(self, client):
        """If publish_job raises, endpoint returns 500 and document status is ERROR."""
        from backend.app.models.document import Document, DocumentStatus

        token, _ = _create_user_and_token("upload_fail_user")
        with patch.object(queue, "publish_job", side_effect=Exception("broker down")):
            resp = client.post("/documents", files=[_pdf()], headers=_auth(token))

        assert resp.status_code == 500

        # The DB record should still exist but with status=error
        db = TestingSessionLocal()
        try:
            docs = (
                db.query(Document).filter(Document.status == DocumentStatus.ERROR).all()
            )
            assert any(True for _ in docs)  # at least one error doc exists
        finally:
            db.close()


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

    def test_document_id_is_valid_uuid(self, client):
        import uuid

        token, _ = _create_user_and_token("list_uuid_user")
        h = _auth(token)
        client.post("/documents", files=[_pdf()], headers=h)

        doc = client.get("/documents", headers=h).json()[0]
        uuid.UUID(doc["document_id"])  # raises ValueError if not a valid UUID

    def test_upload_date_is_iso8601(self, client):
        from datetime import datetime

        token, _ = _create_user_and_token("list_date_user")
        h = _auth(token)
        client.post("/documents", files=[_pdf()], headers=h)

        doc = client.get("/documents", headers=h).json()[0]
        # fromisoformat raises ValueError if the string isn't valid ISO 8601
        datetime.fromisoformat(doc["upload_date"])

    def test_status_ready_returned_correctly(self, client):
        """When a worker marks a document ready, GET should reflect status=ready."""
        from backend.app.models.document import Document, DocumentStatus

        token, _ = _create_user_and_token("list_ready_user")
        h = _auth(token)
        resp = client.post("/documents", files=[_pdf()], headers=h)
        doc_id = resp.json()["document_id"]

        # Simulate worker completing processing
        import uuid as uuid_mod

        db = TestingSessionLocal()
        try:
            doc = (
                db.query(Document).filter(Document.id == uuid_mod.UUID(doc_id)).first()
            )
            doc.status = DocumentStatus.READY
            doc.page_count = 3
            db.commit()
        finally:
            db.close()

        docs = client.get("/documents", headers=h).json()
        updated = next(d for d in docs if d["document_id"] == doc_id)
        assert updated["status"] == "ready"
        assert updated["page_count"] == 3


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
        token, _ = _create_user_and_token("del_s3_user")
        h = _auth(token)

        doc_id = client.post("/documents", files=[_pdf()], headers=h).json()[
            "document_id"
        ]
        assert any(doc_id in k for k in _bucket_keys())

        client.delete(f"/documents/{doc_id}", headers=h)
        assert not any(doc_id in k for k in _bucket_keys())

    def test_delete_removes_embeddings_from_vector_db(self, client):
        """delete_embeddings must be called with the correct document_id."""
        token, _ = _create_user_and_token("del_vector_user")
        h = _auth(token)

        doc_id = client.post("/documents", files=[_pdf()], headers=h).json()[
            "document_id"
        ]
        with patch.object(vector, "delete_embeddings") as mock_delete:
            resp = client.delete(f"/documents/{doc_id}", headers=h)
            assert resp.status_code == 200
            mock_delete.assert_called_once_with(doc_id)

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

        docs = client.get("/documents", headers=_auth(token_a)).json()
        assert any(d["document_id"] == doc_id for d in docs)
