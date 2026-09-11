from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from database import get_db
from routers._common import validate_project_id
from services import novel_memory_service
from services.novel_memory_service import DEFAULT_MEMORY_PAGE_SIZE, MAX_MEMORY_PAGE_SIZE
from services.novel_memory_types import ATOM_STATUSES


router = APIRouter()


class AtomStatusRequest(BaseModel):
    status: str


@router.get("/{project_id}/memory/summary")
async def memory_summary(project_id: str, db=Depends(get_db)):
    return await novel_memory_service.memory_summary(db, validate_project_id(project_id))


@router.get("/{project_id}/memory/atoms")
async def list_memory_atoms(
    project_id: str,
    status: str | None = None,
    limit: int = Query(DEFAULT_MEMORY_PAGE_SIZE, ge=1, le=MAX_MEMORY_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
):
    return await novel_memory_service.list_memory_atoms(
        db, validate_project_id(project_id), status, limit=limit, offset=offset
    )


@router.patch("/{project_id}/memory/atoms/{atom_id}/status")
async def update_atom_status(
    project_id: str,
    atom_id: uuid.UUID,
    request: AtomStatusRequest,
    db=Depends(get_db),
):
    if request.status not in ATOM_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid atom status")
    try:
        return await novel_memory_service.set_memory_atom_status(
            db,
            validate_project_id(project_id),
            atom_id,
            request.status,
        )
    except LookupError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}/memory/scenes")
async def list_memory_scenes(
    project_id: str,
    limit: int = Query(DEFAULT_MEMORY_PAGE_SIZE, ge=1, le=MAX_MEMORY_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
):
    return await novel_memory_service.list_memory_scenes(
        db, validate_project_id(project_id), limit=limit, offset=offset
    )


@router.get("/{project_id}/memory/doctrines")
async def list_memory_doctrines(
    project_id: str,
    limit: int = Query(DEFAULT_MEMORY_PAGE_SIZE, ge=1, le=MAX_MEMORY_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
):
    return await novel_memory_service.list_memory_doctrines(
        db, validate_project_id(project_id), limit=limit, offset=offset
    )


@router.get("/{project_id}/memory/evidence")
async def list_memory_evidence(
    project_id: str,
    limit: int = Query(DEFAULT_MEMORY_PAGE_SIZE, ge=1, le=MAX_MEMORY_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
):
    return await novel_memory_service.list_memory_evidence(
        db, validate_project_id(project_id), limit=limit, offset=offset
    )
