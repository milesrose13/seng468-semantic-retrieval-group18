import logging

from fastapi import APIRouter, Depends

from .. import cache, vector
from ..dependencies import get_current_user
from ..models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def search(
    q: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    cached = cache.get_search_results(current_user.id, q)
    if cached is not None:
        logger.info("Cache hit: user=%s query=%r", current_user.id, q)
        return cached

    logger.info("Cache miss: user=%s query=%r", current_user.id, q)
    results = vector.search_embeddings(q, current_user.id, limit=5)
    cache.set_search_results(current_user.id, q, results)
    return results
