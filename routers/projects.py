from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services import outline_service, project_service
from services.experiment_types import ExperimentConfig
from services.novel_constants import (
    DEFAULT_OPTIMIZE_INTERVAL,
    DEFAULT_TARGET_CHAPTERS,
    DEFAULT_WORD_COUNT_PER_CHAPTER,
    NOVEL_MODE_AUTO,
    NOVEL_MODE_STEP,
)
from services.project_service import DEFAULT_JOB_HISTORY_PAGE_SIZE, MAX_JOB_HISTORY_PAGE_SIZE
from services.ids import parse_project_id
from worker_support.task_registry import cancel_and_wait


router = APIRouter()

class CreateProjectRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    author: str | None = Field(default=None, max_length=200)
    novel_format: str | None = Field(default=None, max_length=100)
    creative_profile: dict | None = None
    target_chapters: int | None = Field(default=None, ge=1, le=10_000)
    word_count_per_chapter: int | None = Field(default=None, ge=1, le=100_000)
    optimize_interval: int = Field(default=DEFAULT_OPTIMIZE_INTERVAL, ge=1, le=10_000)
    mode: str = Field(default=NOVEL_MODE_STEP, pattern=f"^({NOVEL_MODE_STEP}|{NOVEL_MODE_AUTO})$")
    user_prompt: str | None = Field(default=None, max_length=100_000)
    prompt: str | None = Field(default=None, max_length=100_000)
    reference_style: str = Field(default="", max_length=100_000)
    experiment: ExperimentConfig | None = None

    @model_validator(mode="after")
    def validate_required_text(self):
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("title must not be blank")
        prompt = (self.user_prompt or self.prompt or "").strip()
        if not prompt:
            raise ValueError("user_prompt must not be blank")
        self.user_prompt = prompt
        return self


class ProjectConfigRequest(BaseModel):
    word_count_per_chapter: int = Field(ge=0, le=100_000)
    mode: str | None = Field(default=None, pattern=f"^({NOVEL_MODE_STEP}|{NOVEL_MODE_AUTO})$")
    optimize_interval: int | None = Field(default=None, ge=1, le=10_000)
    target_chapters: int | None = Field(default=None, ge=1, le=10_000)


class ManualOutlineUpdateRequest(BaseModel):
    outline: dict


class OutlineChatRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=20_000)
    current_outline: dict | None = None


@router.get("/formats")
async def get_formats(db: AsyncSession = Depends(get_db)):
    return await project_service.get_formats(db)


@router.get("/projects")
async def list_projects(db: AsyncSession = Depends(get_db)):
    return await project_service.list_projects(db)


@router.post("/project")
async def create_project(data: CreateProjectRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await project_service.create_project(db, data.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Stop local tasks before the service removes their durable Job rows."""
    pid = parse_project_id(project_id)
    job_ids = await project_service.active_project_job_ids_for_delete(db, pid)
    for job_id in job_ids:
        await cancel_and_wait(str(job_id))
    try:
        return await project_service.delete_project(db, pid)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


router.add_api_route("/project/{project_id}", delete_project, methods=["DELETE"])
@router.get("/{project_id}/status")
async def get_status(project_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await project_service.get_status(db, parse_project_id(project_id))
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error




@router.post("/{project_id}/config")
async def update_config(project_id: str, data: ProjectConfigRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await outline_service.update_config(
            db,
            parse_project_id(project_id),
            word_count_per_chapter=data.word_count_per_chapter,
            mode=data.mode,
            optimize_interval=data.optimize_interval,
            target_chapters=data.target_chapters,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/{project_id}/outline")
async def get_outline(project_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await outline_service.get_outline(db, parse_project_id(project_id))
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/{project_id}/outline")
async def update_outline(project_id: str, data: ManualOutlineUpdateRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await outline_service.update_outline(db, parse_project_id(project_id), data.outline)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/{project_id}/outline/chat")
async def chat_update_outline(project_id: str, data: OutlineChatRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await outline_service.chat_update_outline(
            db,
            parse_project_id(project_id),
            instruction=data.instruction,
            current_outline=data.current_outline,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error




@router.get("/{project_id}/chapter-outlines")
async def get_chapter_outlines(project_id: str, db: AsyncSession = Depends(get_db)):
    return await outline_service.get_chapter_outlines(db, parse_project_id(project_id))
