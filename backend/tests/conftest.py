import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture(scope="module")
def client():
    """
    Static client for testing the API. 
    Using 'with' ensures startup/shutdown events run.
    """
    with TestClient(app) as c:
        yield c