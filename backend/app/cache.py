import hashlib
import json

import redis

from .config import settings

_redis: redis.Redis | None = None

SEARCH_TTL = 300  # 5 minutes


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _search_key(user_id: int, query: str) -> str:
    normalized = query.strip().lower()
    h = hashlib.sha256(f"{user_id}:{normalized}".encode()).hexdigest()[:16]
    return f"search:{user_id}:{h}"


def get_search_results(user_id: int, query: str) -> list[dict] | None:
    if not settings.CACHE_ENABLED:
        return None
    r = _get_redis()
    key = _search_key(user_id, query)
    cached = r.get(key)
    if cached is None:
        return None
    return json.loads(cached)


def set_search_results(user_id: int, query: str, results: list[dict]) -> None:
    if not settings.CACHE_ENABLED:
        return
    r = _get_redis()
    key = _search_key(user_id, query)
    r.set(key, json.dumps(results), ex=SEARCH_TTL)


def invalidate_user_cache(user_id: int) -> None:
    """Clear all cached search results for a user (e.g. after upload or delete)."""
    if not settings.CACHE_ENABLED:
        return
    r = _get_redis()
    keys = r.keys(f"search:{user_id}:*")
    if keys:
        r.delete(*keys)
