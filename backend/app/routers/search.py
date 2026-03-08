from fastapi import APIRouter, Depends

from .. import vector
from ..dependencies import get_current_user
from ..models.user import User

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def search(
    q: str,
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    results = vector.search_embeddings(q, current_user.id, limit=5)
    return results
