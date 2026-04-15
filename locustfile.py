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

    @task(1) 
    def upload_pdf(self):
        """Upload a fake PDF between 1MB and 50MB."""
        if not self.token:
            return
            
        # To meet TA requirement change this to 1-50 MB
        size_mb = random.randint(1, 50)
        fake_pdf = b"%PDF-1.4 " + b"A" * (size_mb * 1024 * 1024)
        
        self.client.post(
            "/documents",
            files={"file": (f"test_{size_mb}MB.pdf", io.BytesIO(fake_pdf), "application/pdf")},
            headers=self.auth_headers(),
        )

    @task(8)
    def search(self):
        """Search across documents with dynamic queries."""
        if not self.token:
            return
            
        topics = ["machine learning", "neural network", "distributed systems", "database indexing", "software architecture"]
        actions = ["optimization", "training", "scalability", "techniques", "patterns", "performance"]
        
        query = f"{random.choice(topics)} {random.choice(actions)}"
        
        self.client.get(
            f"/search?q={query}",
            headers=self.auth_headers(),
        )

    @task(1)
    def list_documents(self):
        """List user's documents."""
        if not self.token:
            return
        self.client.get("/documents", headers=self.auth_headers())
