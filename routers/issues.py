from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from routers._common import validate_project_id
from services import issue_service
from services.issue_service import DEFAULT_ISSUE_PAGE_SIZE, MAX_ISSUE_PAGE_SIZE


router = APIRouter()


class ToggleIssueRequest(BaseModel):
    enabled: bool


@router.get("/{project_id}/raw-issues")
async def get_raw_issues(
    project_id: str,
    limit: int = Query(DEFAULT_ISSUE_PAGE_SIZE, ge=1, le=MAX_ISSUE_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await issue_service.list_raw_issues(
        db, validate_project_id(project_id), limit=limit, offset=offset
    )


@router.get("/{project_id}/issue-summaries")
async def get_issue_summaries(
    project_id: str,
    limit: int = Query(DEFAULT_ISSUE_PAGE_SIZE, ge=1, le=MAX_ISSUE_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await issue_service.list_issue_summaries(
        db, validate_project_id(project_id), limit=limit, offset=offset
    )


@router.post("/{project_id}/issue-summaries/{issue_id}/toggle")
async def toggle_issue_summary(
    project_id: str,
    issue_id: str,
    data: ToggleIssueRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await issue_service.set_issue_summary_enabled(
            db,
            validate_project_id(project_id),
            uuid.UUID(issue_id),
            data.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid issue_id") from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
