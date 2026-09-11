"""Character side-story branch API."""

from __future__ import annotations

import copy
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from routers._common import validate_project_id
from services.character_branch_service import (
    DEFAULT_CHARACTER_BRANCH_PAGE_SIZE,
    MAX_CHARACTER_BRANCH_PAGE_SIZE,
    active_character_branch_job_ids,
    archive_character_branch,
    create_character_branch,
    discover_branch_candidates,
    get_branch_discovery_setting,
    get_branch_chapter,
    get_character_branch,
    list_branch_chapters,
    list_character_arcs,
    list_character_branches,
    transition_branch_status,
    update_branch_discovery_setting,
    update_branch_chapter_content,
)
from services.character_branch_vector_service import clear_branch_vector_namespace
from worker_support.task_registry import cancel_and_wait
from services.character_branch_types import (
    BranchCandidateResponse,
    CreateCharacterBranchRequest,
    EditCharacterBranchChapterRequest,
    GenerateCharacterBranchRequest,
    CharacterBranchSettingsRequest,
)
from services.character_constants import (
    CHARACTER_BRANCH_CHAPTER_STATUS_DRAFT,
    CHARACTER_BRANCH_STATUS_DRAFT,
    CHARACTER_BRANCH_STATUS_FAILED,
    CHARACTER_BRANCH_STATUS_GENERATING,
    CHARACTER_BRANCH_STATUS_PENDING,
    CHARACTER_BRANCH_STATUS_READY,
)


router = APIRouter()


def _project_id(value: str) -> uuid.UUID:
    return validate_project_id(value)


def _serialize_arc(arc) -> dict[str, Any]:
    return {
        "id": str(arc.id),
        "character_id": str(arc.character_id),
        "storyline_id": arc.storyline_id,
        "arc_type": arc.arc_type,
        "name": arc.name,
        "anchor_chapter": arc.anchor_chapter,
        "target_chapter": arc.target_chapter,
        "status": arc.status,
        "data": copy.deepcopy(arc.data or {}),
    }


def _serialize_chapter(chapter) -> dict[str, Any]:
    return {
        "id": str(chapter.id),
        "branch_id": str(chapter.branch_id),
        "chapter_index": chapter.chapter_index,
        "anchor_main_chapter": chapter.anchor_main_chapter,
        "title": chapter.title,
        "outline": copy.deepcopy(chapter.outline),
        "draft_content": chapter.draft_content,
        "edited_content": chapter.edited_content,
        "content": chapter.content,
        "word_count": chapter.word_count,
        "validator_result": copy.deepcopy(chapter.validator_result),
        "status": chapter.status,
        "state_data": copy.deepcopy(chapter.state_data or {}),
        "relationship_changes": copy.deepcopy(chapter.relationship_changes or []),
        "source_ref": chapter.source_ref,
        "error": chapter.error,
        "created_at": chapter.created_at.isoformat() if chapter.created_at else None,
        "updated_at": chapter.updated_at.isoformat() if chapter.updated_at else None,
    }


def _serialize_branch(branch, chapters: list | None = None) -> dict[str, Any]:
    return {
        "id": str(branch.id),
        "project_id": str(branch.project_id),
        "character_id": str(branch.character_id),
        "arc_id": str(branch.arc_id) if branch.arc_id else None,
        "title": branch.title,
        "storyline_id": branch.storyline_id,
        "anchor_main_chapter": branch.anchor_main_chapter,
        "current_chapter_index": branch.current_chapter_index,
        "target_chapters": branch.target_chapters,
        "status": branch.status,
        "user_request": branch.user_request,
        "generation_config": copy.deepcopy(branch.generation_config or {}),
        "auto_discovered": bool(branch.auto_discovered),
        "error": branch.error,
        "created_at": branch.created_at.isoformat() if branch.created_at else None,
        "updated_at": branch.updated_at.isoformat() if branch.updated_at else None,
        "chapters": [_serialize_chapter(item) for item in chapters or []],
    }


def _branch_or_404(branch):
    if branch is None:
        raise HTTPException(status_code=404, detail="Character branch not found")
    return branch


@router.get("/{project_id}/characters/{character_id}/arcs")
async def get_character_arcs(
    project_id: str,
    character_id: uuid.UUID,
    limit: int = Query(DEFAULT_CHARACTER_BRANCH_PAGE_SIZE, ge=1, le=MAX_CHARACTER_BRANCH_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    pid = _project_id(project_id)
    return {
        "arcs": [
            _serialize_arc(item)
            for item in await list_character_arcs(
                db, pid, character_id, limit=limit, offset=offset
            )
        ]
    }


@router.get("/{project_id}/characters/{character_id}/branches/candidates")
async def get_branch_candidates(project_id: str, character_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    pid = _project_id(project_id)
    enabled = await get_branch_discovery_setting(db, pid)
    if enabled is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not enabled:
        return {"enabled": False, "candidates": []}
    candidates = [item for item in await discover_branch_candidates(db, pid) if item["character_id"] == str(character_id)]
    return {"enabled": True, "candidates": [BranchCandidateResponse.model_validate(item).model_dump() for item in candidates]}


@router.get("/{project_id}/characters/{character_id}/branches")
async def get_character_branches(
    project_id: str,
    character_id: uuid.UUID,
    limit: int = Query(DEFAULT_CHARACTER_BRANCH_PAGE_SIZE, ge=1, le=MAX_CHARACTER_BRANCH_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    pid = _project_id(project_id)
    branches = await list_character_branches(
        db, pid, character_id, limit=limit, offset=offset
    )
    return {"branches": [_serialize_branch(item) for item in branches]}


@router.get("/{project_id}/character-branch-settings")
async def get_character_branch_settings(project_id: str, db: AsyncSession = Depends(get_db)):
    pid = _project_id(project_id)
    enabled = await get_branch_discovery_setting(db, pid)
    if enabled is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"auto_discovery_enabled": enabled}


@router.patch("/{project_id}/character-branch-settings")
async def patch_character_branch_settings(project_id: str, request: CharacterBranchSettingsRequest, db: AsyncSession = Depends(get_db)):
    pid = _project_id(project_id)
    enabled = await update_branch_discovery_setting(db, pid, request.auto_discovery_enabled)
    if enabled is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.commit()
    return {"auto_discovery_enabled": enabled}


@router.post("/{project_id}/characters/{character_id}/branches")
async def post_character_branch(
    project_id: str,
    character_id: uuid.UUID,
    request: CreateCharacterBranchRequest,
    db: AsyncSession = Depends(get_db),
):
    pid = _project_id(project_id)
    try:
        branch = await create_character_branch(
            db,
            pid,
            character_id,
            arc_id=uuid.UUID(request.arc_id) if request.arc_id else None,
            title=request.title,
            anchor_main_chapter=request.anchor_main_chapter,
            target_chapters=request.target_chapters,
            user_request=request.user_request,
            generation_config=request.generation_config,
            auto_discovered=request.auto_discovered,
        )
        await db.commit()
    except (LookupError, ValueError) as exc:
        await db.rollback()
        status_code = 404 if isinstance(exc, LookupError) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return _serialize_branch(branch)


@router.get("/{project_id}/characters/{character_id}/branches/{branch_id}")
async def get_character_branch_detail(
    project_id: str,
    character_id: uuid.UUID,
    branch_id: uuid.UUID,
    limit: int = Query(DEFAULT_CHARACTER_BRANCH_PAGE_SIZE, ge=1, le=MAX_CHARACTER_BRANCH_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    pid = _project_id(project_id)
    branch = _branch_or_404(await get_character_branch(db, pid, character_id, branch_id))
    return _serialize_branch(
        branch, await list_branch_chapters(db, branch.id, limit=limit, offset=offset)
    )


@router.get("/{project_id}/characters/{character_id}/branches/{branch_id}/chapters")
async def get_character_branch_chapters(
    project_id: str,
    character_id: uuid.UUID,
    branch_id: uuid.UUID,
    limit: int = Query(DEFAULT_CHARACTER_BRANCH_PAGE_SIZE, ge=1, le=MAX_CHARACTER_BRANCH_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    pid = _project_id(project_id)
    branch = _branch_or_404(await get_character_branch(db, pid, character_id, branch_id))
    return {
        "chapters": [
            _serialize_chapter(item)
            for item in await list_branch_chapters(
                db, branch.id, limit=limit, offset=offset
            )
        ]
    }


@router.get("/{project_id}/characters/{character_id}/branches/{branch_id}/chapters/{chapter_index}")
async def get_character_branch_chapter(project_id: str, character_id: uuid.UUID, branch_id: uuid.UUID, chapter_index: int, db: AsyncSession = Depends(get_db)):
    pid = _project_id(project_id)
    branch = _branch_or_404(await get_character_branch(db, pid, character_id, branch_id))
    chapter = _branch_or_404(await get_branch_chapter(db, branch.id, chapter_index))
    return _serialize_chapter(chapter)


@router.patch("/{project_id}/characters/{character_id}/branches/{branch_id}/chapters/{chapter_index}")
async def patch_character_branch_chapter(
    project_id: str,
    character_id: uuid.UUID,
    branch_id: uuid.UUID,
    chapter_index: int,
    request: EditCharacterBranchChapterRequest,
    db: AsyncSession = Depends(get_db),
):
    pid = _project_id(project_id)
    branch = _branch_or_404(await get_character_branch(db, pid, character_id, branch_id))
    try:
        chapter = await update_branch_chapter_content(
            db, branch, chapter_index, title=request.title, content=request.content
        )
        await db.commit()
    except LookupError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize_chapter(chapter)


@router.post("/{project_id}/characters/{character_id}/branches/{branch_id}/archive")
async def post_archive_character_branch(project_id: str, character_id: uuid.UUID, branch_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    pid = _project_id(project_id)
    branch = _branch_or_404(await get_character_branch(db, pid, character_id, branch_id, lock=True))
    try:
        for job_id in await active_character_branch_job_ids(db, branch):
            await cancel_and_wait(str(job_id))
        await archive_character_branch(db, branch)
        await db.commit()
        await clear_branch_vector_namespace(branch.id)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize_branch(branch)


@router.post("/{project_id}/characters/{character_id}/branches/{branch_id}/generate")
async def post_generate_character_branch(
    project_id: str,
    character_id: uuid.UUID,
    branch_id: uuid.UUID,
    request: GenerateCharacterBranchRequest,
    db: AsyncSession = Depends(get_db),
):
    pid = _project_id(project_id)
    branch = _branch_or_404(await get_character_branch(db, pid, character_id, branch_id, lock=True))
    if branch.status == CHARACTER_BRANCH_STATUS_READY and branch.current_chapter_index >= branch.target_chapters:
        raise HTTPException(status_code=400, detail="Branch has reached its target chapters")
    if branch.status == CHARACTER_BRANCH_STATUS_GENERATING:
        raise HTTPException(status_code=409, detail="Branch is already generating")
    if branch.status not in {CHARACTER_BRANCH_STATUS_PENDING, CHARACTER_BRANCH_STATUS_DRAFT, CHARACTER_BRANCH_STATUS_FAILED, CHARACTER_BRANCH_STATUS_READY}:
        raise HTTPException(status_code=400, detail="Branch cannot be generated in its current state")
    if request.user_request is not None:
        branch.user_request = request.user_request.strip()
    branch.generation_config = {
        **(branch.generation_config or {}),
        "requested_chapters": request.chapters,
        "continue_generation": request.continue_generation,
    }
    await transition_branch_status(db, branch, CHARACTER_BRANCH_STATUS_GENERATING)
    from services.character_branch_generation import enqueue_branch_generation
    job = await enqueue_branch_generation(pid, character_id, branch.id, request.chapters, db=db)
    await db.commit()
    response = _serialize_branch(branch)
    response["job_id"] = str(job.id)
    return response
