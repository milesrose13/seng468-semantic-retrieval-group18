"""
Tests for auth endpoints
POST /auth/signup
Create a new user account

POST /auth/login
Authenticate and recieve token
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app import storage
from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models.user import User  # noqa: F401
from backend.tests.test_documents import engine, override_get_db

app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    with patch.object(storage, "ensure_bucket_exists"):
        with TestClient(app) as c:
            yield c
    Base.metadata.drop_all(bind=engine)


# this document was written with the help of the following documentation: https://fastapi.tiangolo.com/tutorial/testing/#using-testclient
# https://docs.pytest.org/en/stable/getting-started.html
# https://starlette.dev/testclient/
# Claude AI was also used to help me understand what differnt things mean because it is my first time doing this


class TestSignup:
    def test_successful_signup(self, client):
        resp = client.post(
            "/auth/signup", json={"username": "gamin4hope", "password": "password123"}
        )
        assert resp.status_code == 200  # 200 is OK
        data = resp.json()
        assert "message" in data
        assert "user_id" in data

    def test_duplicate_username(self, client):
        resp = client.post(
            "/auth/signup", json={"username": "gamin4hope", "password": "password123"}
        )
        assert resp.status_code == 409  # 409 is when duplicate username
        data = resp.json()
        assert data["error"] == "Username already exists"


class TestLogin:
    def test_successful_login(self, client):
        client.post(
            "/auth/signup", json={"username": "alice", "password": "password123"}
        )

        resp = client.post(
            "/auth/login", json={"username": "alice", "password": "password123"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "user_id" in data

    def test_invalid_credentials(self, client):
        resp = client.post(
            "/auth/login", json={"username": "gamin4hope", "password": "platinum3"}
        )
        assert resp.status_code == 401
        data = resp.json()
        assert data["error"] == "Invalid credentials"
