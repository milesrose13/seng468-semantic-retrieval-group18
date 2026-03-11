"""Background worker: consumes RabbitMQ jobs, parses PDFs, stores embeddings in Qdrant."""
import io
import json
import logging
import uuid

import pika
import boto3
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.document import Document, DocumentStatus

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


def process_job(job: dict, model: SentenceTransformer, qdrant: QdrantClient) -> None:
    document_id = job["document_id"]
    storage_key = job["storage_key"]
    user_id = job["user_id"]

    db: Session = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            log.warning("Document %s not found in DB, skipping", document_id)
            return

        # Download PDF from MinIO
        log.info("Downloading %s from MinIO", storage_key)
        response = _s3_client().get_object(Bucket=MINIO_BUCKET, Key=storage_key)
        pdf_bytes = response["Body"].read()

        # Parse PDF into paragraphs
        reader = PdfReader(io.BytesIO(pdf_bytes))
        page_count = len(reader.pages)
        paragraphs = []
        for page in reader.pages:
            text = page.extract_text() or ""
            for para in text.split("\n\n"):
                para = para.strip()
                if len(para) > 20:  # skip very short fragments
                    paragraphs.append(para)

        if not paragraphs:
            log.warning("No text extracted from document %s", document_id)
            doc.status = DocumentStatus.ERROR
            db.commit()
            return

        # Generate embeddings
        log.info("Embedding %d paragraphs for document %s", len(paragraphs), document_id)
        vectors = model.encode(paragraphs, show_progress_bar=False).tolist()

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
                    "text": para,
                },
            )
            for para, vector in zip(paragraphs, vectors)
        ]
        qdrant.upsert(collection_name=QDRANT_COLLECTION, points=points)

        # Update document status
        doc.status = DocumentStatus.READY
        doc.page_count = page_count
        db.commit()
        log.info("Document %s processed successfully (%d pages)", document_id, page_count)

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
        log.info("Received job: %s", job)
        process_job(job, model, qdrant)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
    log.info("Worker ready, waiting for jobs...")
    channel.start_consuming()


if __name__ == "__main__":
    main()
