import os

from qdrant_client import QdrantClient

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "embeddings")


def _client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


def delete_embeddings(document_id: str) -> None:
    """Delete all embedding vectors associated with a document."""
    client = _client()
    # Only attempt deletion if the collection exists
    collections = [c.name for c in client.get_collections().collections]
    if QDRANT_COLLECTION not in collections:
        return
    client.delete(
        collection_name=QDRANT_COLLECTION,
        points_selector={
            "filter": {
                "must": [{"key": "document_id", "match": {"value": document_id}}]
            }
        },
    )
