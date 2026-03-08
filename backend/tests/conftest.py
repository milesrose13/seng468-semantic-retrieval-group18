from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app import storage
from backend.app.main import app


@pytest.fixture(scope="module")
def client():
    """
    Minimal client for tests that don't need a database (e.g. test_main.py).
    Using 'with' ensures startup/shutdown events run.
    """
    with patch.object(storage, "ensure_bucket_exists"):
        with TestClient(app) as c:
            yield c
