from fastapi import APIRouter, Depends

from .. import cache, vector
from ..dependencies import get_current_user
from ..models.user import User

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def search(
    q: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    cached = cache.get_search_results(current_user.id, q)
    if cached is not None:
        return cached

    results = vector.search_embeddings(q, current_user.id, limit=5)
    cache.set_search_results(current_user.id, q, results)
    return results
