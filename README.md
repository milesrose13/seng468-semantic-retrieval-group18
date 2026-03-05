# SENG 468 – Distributed Semantic Retrieval System

Scalable semantic search engine for user-uploaded PDFs.
Supports concurrent uploads and searches with asynchronous processing and Dockerized deployment.

## Core Features

User authentication (JWT-based)

PDF upload (async processing)

Background PDF parsing + embedding generation

Vector similarity search (top 5 paragraphs)

User isolation (no cross-user access)

Docker Compose deployment (docker-compose up)

## High-Level Architecture

API (Port 8080)

Stateless REST service

Handles auth, document metadata, search requests

Worker Service

Consumes queue jobs

Parses PDFs → chunks → generates embeddings → stores vectors

Relational DB (PostgreSQL)

Users

Documents (metadata, status, ownership)

Object Storage (MinIO or equivalent)

Stores raw PDFs (no local disk usage in API)

Vector DB (e.g., Qdrant / Chroma / pgvector)

Stores paragraph embeddings

Performs cosine similarity search

Message Queue (RabbitMQ / Redis Queue)

Decouples upload from processing

All services containerized via Docker Compose.

## Required API Endpoints (Port 8080)

### Authentication

#### POST /auth/signup

{ "username": "alice", "password": "securepassword123" }

200 → user created

409 → username exists

#### POST /auth/login

{ "username": "alice", "password": "securepassword123" }

200 → { token, user_id }

401 → invalid credentials

Use:
Authorization: Bearer <token>

### Documents

#### POST /documents (multipart/form-data, field: file)

Returns 202 Accepted immediately

Enqueues background job

Response:

{
  "message": "PDF uploaded, processing started",
  "document_id": "uuid",
  "status": "processing"
}

#### GET /documents
Returns user’s documents with:

document_id

filename

upload_date

status (processing | ready)

page_count

#### DELETE /documents/{id}

Removes PDF from object storage

Deletes embeddings from vector DB

Deletes metadata from DB

### Search

#### GET /search?q=<query>

Returns:

[
  {
    "text": "...",
    "score": 0.94,
    "document_id": "uuid",
    "filename": "file.pdf"
  }
]

## Constraints:

Exactly 5 results (or fewer if not available)

Sorted by score (descending)

Scores ∈ [0, 1]

Only search user-owned documents

Background Processing Pipeline

Upload → store PDF in object storage

Insert DB record (status = processing)

Publish job to queue

Worker:

Download PDF

Extract text

Chunk into paragraphs (or fixed token size)

Generate embeddings (local model only)

Insert into vector DB

Update DB (status = ready, page_count)

## Local Development Setup

### 1. Environment

```bash
cp .env.example .env
```

### 2. Start Postgres

```bash
docker compose -f dockercompose.yml up -d postgres
```

Wait until it's healthy:

```bash
docker compose -f dockercompose.yml ps
# STATUS column should show: Up (healthy)
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run migrations

Apply all migrations to the database:

```bash
alembic upgrade head
```

Check current migration state:

```bash
alembic current
```

### 5. Creating a new migration

After modifying models in `backend/app/models/__init__.py`, autogenerate a migration:

```bash
alembic revision --autogenerate -m "describe your change"
alembic upgrade head
```

Always commit the generated file in `alembic/versions/` to version control.

### 6. Run tests

```bash
pytest
```

Tests use SQLite in-memory — no Postgres required.

### 7. Stop Postgres

```bash
docker compose -f dockercompose.yml down
```

---

## Docker Requirements

Must work with:

cp .env.example .env
docker-compose up --build

Services:

api

worker

postgres

vector-db

object-storage

message-queue

No hardcoded paths. No local-only dependencies.