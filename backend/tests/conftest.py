from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import storage
from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models.user import User

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="module")
def client():
    """
    Static client for testing the API.
    Using 'with' ensures startup/shutdown events run.
    Creates test DB tables on setup and drops them on teardown.
    """
    Base.metadata.create_all(bind=engine)
    with patch.object(storage, "ensure_bucket_exists"):
        with TestClient(app) as c:
            yield c
    Base.metadata.drop_all(bind=engine)
