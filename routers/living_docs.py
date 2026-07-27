from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from database import get_db
from routers._common import validate_project_id
from services import living_docs_service
from services.document_constants import ALL_DOC_TYPES

router = APIRouter()

# Whitelist of allowed doc_type values to prevent path traversal.
# Reuse the canonical ALL_DOC_TYPES tuple from services.constants so that
# adding a new doc_type only requires updating one place.
_ALLOWED_DOC_TYPES = frozenset(ALL_DOC_TYPES)


def _validate_doc_type(doc_type: str) -> str:
    if doc_type not in _ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid doc_type: {doc_type}")
    return doc_type


class UpdateLivingDocRequest(BaseModel):
    content: str = ""


class RollbackLivingDocRequest(BaseModel):
    chapter_index: int = Field(..., ge=1)


@router.get("/{project_id}/living-docs")
async def get_living_docs(project_id: str, db=Depends(get_db)):
    validate_project_id(project_id)
    return await living_docs_service.get_living_docs(project_id, db)


@router.get("/{project_id}/living-docs/versions")
async def get_living_doc_versions(project_id: str, db=Depends(get_db)):
    validate_project_id(project_id)
    return await living_docs_service.get_living_doc_versions(project_id, db)


@router.get("/{project_id}/living-docs/versions/{chapter_index}/{doc_type}")
async def get_living_doc_version_content(project_id: str, chapter_index: int, doc_type: str):
    validate_project_id(project_id)
    _validate_doc_type(doc_type)
    return await living_docs_service.get_living_doc_version_content(project_id, chapter_index, doc_type)


@router.get("/{project_id}/living-docs/{doc_type}")
async def get_living_doc(project_id: str, doc_type: str, db=Depends(get_db)):
    validate_project_id(project_id)
    _validate_doc_type(doc_type)
    return await living_docs_service.get_living_doc(project_id, doc_type, db)


@router.put("/{project_id}/living-docs/{doc_type}")
async def update_living_doc(project_id: str, doc_type: str, req: UpdateLivingDocRequest, db=Depends(get_db)):
    validate_project_id(project_id)
    _validate_doc_type(doc_type)
    try:
        return await living_docs_service.update_living_doc(project_id, doc_type, req.content, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{project_id}/living-docs/rollback")
async def rollback_living_doc(project_id: str, req: RollbackLivingDocRequest, db=Depends(get_db)):
    validate_project_id(project_id)
    return await living_docs_service.rollback_living_doc(project_id, req.chapter_index, db)


@router.post("/{project_id}/living-docs/rebuild")
async def rebuild_living_docs(project_id: str, db=Depends(get_db)):
    validate_project_id(project_id)
    return await living_docs_service.rebuild_living_docs(project_id, db)
