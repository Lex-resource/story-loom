from fastapi import APIRouter, HTTPException
from routers._common import validate_project_id
from services.search_constants import (
    DEFAULT_SEARCH_N,
    MIN_SEARCH_N,
    MAX_SEARCH_N,
)
from services.vector_store import search_knowledge_items

router = APIRouter()


@router.get("/{project_id}/search")
async def search_knowledge(
    project_id: str, q: str, type: str = None, n: int = DEFAULT_SEARCH_N
):
    validate_project_id(project_id)
    if n < MIN_SEARCH_N or n > MAX_SEARCH_N:
        raise HTTPException(
            status_code=422,
            detail=f"n must be between {MIN_SEARCH_N} and {MAX_SEARCH_N}",
        )
    return await search_knowledge_items(project_id, q, type, n)
