"""Background worker: consumes RabbitMQ jobs, parses PDFs, stores embeddings in Qdrant."""

import base64
import io
import json
import logging
import uuid

import boto3
import pika
from app.config import settings
from app.database import SessionLocal
from app.models.document import Document, DocumentStatus
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# --- Config ---
RABBITMQ_URL = settings.RABBITMQ_URL
QUEUE_NAME = settings.QUEUE_NAME

MINIO_ENDPOINT = settings.MINIO_ENDPOINT
MINIO_ACCESS_KEY = settings.MINIO_ACCESS_KEY
MINIO_SECRET_KEY = settings.MINIO_SECRET_KEY
MINIO_BUCKET = settings.MINIO_BUCKET

QDRANT_URL = settings.QDRANT_URL
QDRANT_COLLECTION = settings.QDRANT_COLLECTION
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

VECTOR_SIZE = 384  # all-MiniLM-L6-v2 output dimension

# Chunking config
MAX_CHUNK_CHARS = 1000
CHUNK_OVERLAP_CHARS = 200


def _s3_client():
    kwargs = {
        "aws_access_key_id": MINIO_ACCESS_KEY,
        "aws_secret_access_key": MINIO_SECRET_KEY,
        "region_name": "us-east-1",
    }
    if MINIO_ENDPOINT:
        kwargs["endpoint_url"] = MINIO_ENDPOINT
    return boto3.client("s3", **kwargs)


def _ensure_collection(client: QdrantClient) -> None:
    collections = [c.name for c in client.get_collections().collections]
    if QDRANT_COLLECTION not in collections:
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


def chunk_text(text: str) -> list[str]:
    """Split text into chunks with overlap for better search on large documents.

    Strategy:
    1. Split on double newlines to get natural paragraphs.
    2. Merge short paragraphs together until hitting MAX_CHUNK_CHARS.
    3. If a single paragraph exceeds MAX_CHUNK_CHARS, split it with overlap.
    """
    raw_paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    current = ""

    for para in raw_paragraphs:
        # If adding this paragraph would exceed the limit, flush current chunk
        if current and len(current) + len(para) + 1 > MAX_CHUNK_CHARS:
            if len(current) > 20:
                chunks.append(current)
            current = (
                current[-CHUNK_OVERLAP_CHARS:]
                if len(current) > CHUNK_OVERLAP_CHARS
                else current
            )

        if current:
            current += "\n\n" + para
        else:
            current = para

        # If current chunk is way too long (single huge paragraph), split it
        while len(current) > MAX_CHUNK_CHARS:
            # Find a sentence boundary near MAX_CHUNK_CHARS
            split_at = MAX_CHUNK_CHARS
            for sep in [". ", ".\n", "? ", "! "]:
                idx = current.rfind(sep, 0, MAX_CHUNK_CHARS)
                if idx > MAX_CHUNK_CHARS // 2:
                    split_at = idx + len(sep)
                    break

            chunk = current[:split_at].strip()
            if len(chunk) > 20:
                chunks.append(chunk)
            current = current[split_at - CHUNK_OVERLAP_CHARS :].strip()

    # Flush remaining
    if current and len(current) > 20:
        chunks.append(current)

    return chunks


def process_job(job: dict, model: SentenceTransformer, qdrant: QdrantClient) -> None:
    document_id = job["document_id"]
    storage_key = job["storage_key"]
    user_id = job["user_id"]

    db: Session = SessionLocal()
    doc = None
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            log.warning("Document %s not found in DB, skipping", document_id)
            return

        # Get PDF bytes: either from the message or from MinIO
        if "file_b64" in job:
            pdf_bytes = base64.b64decode(job["file_b64"])
            # Upload to MinIO (offloaded from API)
            log.info("Uploading %s to MinIO", storage_key)
            _s3_client().put_object(
                Bucket=MINIO_BUCKET,
                Key=storage_key,
                Body=pdf_bytes,
                ContentType="application/pdf",
            )
        else:
            # Backwards compatible: download from MinIO if already uploaded
            log.info("Downloading %s from MinIO", storage_key)
            response = _s3_client().get_object(Bucket=MINIO_BUCKET, Key=storage_key)
            pdf_bytes = response["Body"].read()

        # Re-check document still exists (could have been deleted mid-processing)
        db.expire_all()
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            log.warning(
                "Document %s was deleted during processing, cleaning up", document_id
            )
            _s3_client().delete_object(Bucket=MINIO_BUCKET, Key=storage_key)
            return

        # Parse PDF
        reader = PdfReader(io.BytesIO(pdf_bytes))
        page_count = len(reader.pages)

        full_text = ""
        for page in reader.pages:
            page_text = page.extract_text() or ""
            full_text += page_text + "\n\n"

        # Chunk the text
        chunks = chunk_text(full_text)

        if not chunks:
            log.warning("No text extracted from document %s", document_id)
            doc.status = DocumentStatus.ERROR
            db.commit()
            return

        log.info(
            "Embedding %d chunks for document %s (%d pages)",
            len(chunks),
            document_id,
            page_count,
        )
        vectors = model.encode(chunks, show_progress_bar=False).tolist()

        # Store in Qdrant
        _ensure_collection(qdrant)
        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "document_id": document_id,
                    "filename": doc.filename,
                    "user_id": user_id,
                    "text": chunk,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        qdrant.upsert(collection_name=QDRANT_COLLECTION, points=points)

        # Update document status
        doc.status = DocumentStatus.READY
        doc.page_count = page_count
        db.commit()
        log.info(
            "Document %s processed successfully (%d pages, %d chunks)",
            document_id,
            page_count,
            len(chunks),
        )

    except Exception:
        log.exception("Failed to process document %s", document_id)
        if doc:
            doc.status = DocumentStatus.ERROR
            db.commit()
    finally:
        db.close()


def main():
    log.info("Loading embedding model %s ...", EMBEDDING_MODEL)
    model = SentenceTransformer(EMBEDDING_MODEL)
    qdrant = QdrantClient(url=QDRANT_URL)

    log.info("Connecting to RabbitMQ at %s", RABBITMQ_URL)
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.basic_qos(prefetch_count=1)

    def callback(ch, method, properties, body):
        job = json.loads(body)
        log.info("Received job: %s", {k: v for k, v in job.items() if k != "file_b64"})
        process_job(job, model, qdrant)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
    log.info("Worker ready, waiting for jobs...")
    channel.start_consuming()


if __name__ == "__main__":
    main()
