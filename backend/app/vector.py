import os

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "embeddings")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def _client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


def search_embeddings(query: str, user_id: int, limit: int = 5) -> list[dict]:
    """Search for the top-k most similar embeddings for the given query.

    Returns a list of dicts with keys: text, score, document_id, filename.
    Only results belonging to user_id are returned.
    """
    client = _client()
    collections = [c.name for c in client.get_collections().collections]
    if QDRANT_COLLECTION not in collections:
        return []

    vector = _get_model().encode(query).tolist()

    results = client.search(
        collection_name=QDRANT_COLLECTION,
        query_vector=vector,
        query_filter={
            "must": [{"key": "user_id", "match": {"value": user_id}}]
        },
        limit=limit,
        with_payload=True,
    )

    return [
        {
            "text": hit.payload.get("text", ""),
            "score": hit.score,
            "document_id": hit.payload.get("document_id", ""),
            "filename": hit.payload.get("filename", ""),
        }
        for hit in results
    ]


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
