import io
import random
import string

from locust import HttpUser, between, task


def random_username():
    return "user_" + "".join(random.choices(string.ascii_lowercase, k=8))


class SemanticRetrievalUser(HttpUser):
    wait_time = between(1, 3)
    token = None
    username = None

    def on_start(self):
        """Called when a simulated user starts - signup and login."""
        self.username = random_username()

        self.client.post(
            "/auth/signup",
            json={"username": self.username, "password": "password123"},
        )

        resp = self.client.post(
            "/auth/login",
            json={"username": self.username, "password": "password123"},
        )
        if resp.status_code == 200:
            self.token = resp.json().get("token")

    def auth_headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    @task(2)
    def upload_pdf(self):
        """Upload a fake 1MB PDF."""
        if not self.token:
            return
        fake_pdf = b"%PDF-1.4 " + b"A" * (1024 * 1024)  # ~1MB
        self.client.post(
            "/documents",
            files={"file": ("test.pdf", io.BytesIO(fake_pdf), "application/pdf")},
            headers=self.auth_headers(),
        )

    @task(3)
    def search(self):
        """Search across documents."""
        if not self.token:
            return
        queries = [
            "machine learning optimization",
            "neural network training",
            "distributed systems scalability",
            "database indexing techniques",
            "software architecture patterns",
        ]
        self.client.get(
            f"/search?q={random.choice(queries)}",
            headers=self.auth_headers(),
        )

    @task(1)
    def list_documents(self):
        """List user's documents."""
        if not self.token:
            return
        self.client.get("/documents", headers=self.auth_headers())

