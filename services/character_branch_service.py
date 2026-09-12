"""Persistence and isolation rules for character side-story branches."""

from __future__ import annotations

import copy
import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.character_branches import CharacterBranch, CharacterBranchChapter
from models.characters import CharacterArc, CharacterCard, CharacterRelationship
from models.novel import Chapter, Job, Novel
from services.character_card_service import get_state_at_chapter
from services.character_constants import (
    CHARACTER_BRANCH_ANCHOR_CONTEXT_MAX_CHARS,
    CHARACTER_BRANCH_AUTO_DISCOVERY_ENABLED_DEFAULT,
    CHARACTER_BRANCH_AUTO_DISCOVERY_MAX_CANDIDATES,
    CHARACTER_BRANCH_AUTO_DISCOVERY_MIN_INACTIVE_CHAPTERS,
    CHARACTER_BRANCH_CHAPTER_STATUS_DRAFT,
    CHARACTER_BRANCH_CHAPTER_STATUS_GENERATING,
    CHARACTER_BRANCH_DEFAULT_CHAPTER_COUNT,
    CHARACTER_BRANCH_DEFAULT_SOURCE_REF_TEMPLATE,
    CHARACTER_BRANCH_DEFAULT_TITLE_TEMPLATE,
    CHARACTER_BRANCH_MAX_CHAPTER_COUNT,
    CHARACTER_BRANCH_MAX_TITLE_LENGTH,
    CHARACTER_BRANCH_STATUS_ARCHIVED,
    CHARACTER_BRANCH_STATUS_DRAFT,
    CHARACTER_BRANCH_STATUS_FAILED,
    CHARACTER_BRANCH_STATUS_GENERATING,
    CHARACTER_BRANCH_STATUS_PENDING,
    CHARACTER_BRANCH_STATUS_READY,
    CHARACTER_BRANCH_STATUSES,
    CHARACTER_BRANCH_STORYLINE_PREFIX,
    )
from services.character_branch_vector_service import discard_pending_branch_vectors
from services.novel_constants import JOB_TYPE_CHARACTER_BRANCH
from services.pipeline_types import JobStatus


_ACTIVE_BRANCH_STATUSES = (
    CHARACTER_BRANCH_STATUS_PENDING,
    CHARACTER_BRANCH_STATUS_GENERATING,
    CHARACTER_BRANCH_STATUS_DRAFT,
)

DEFAULT_CHARACTER_BRANCH_PAGE_SIZE = 200
MAX_CHARACTER_BRANCH_PAGE_SIZE = 500


def _apply_page(statement, limit: int | None, offset: int):
    if limit is None:
        return statement
    bounded_limit = min(max(int(limit), 1), MAX_CHARACTER_BRANCH_PAGE_SIZE)
    bounded_offset = max(int(offset), 0)
    return statement.limit(bounded_limit).offset(bounded_offset)


async def get_branch_discovery_setting(
    db: AsyncSession, project_id
) -> bool | None:
    """Return the project setting, or ``None`` when the project is missing."""
    novel = (await db.execute(select(Novel).where(Novel.id == project_id))).scalar_one_or_none()
    if novel is None:
        return None
    return bool(
        getattr(
            novel,
            "character_branch_auto_discovery_enabled",
            CHARACTER_BRANCH_AUTO_DISCOVERY_ENABLED_DEFAULT,
        )
    )


async def update_branch_discovery_setting(
    db: AsyncSession, project_id, enabled: bool
) -> bool | None:
    """Update the project setting without committing the caller's transaction."""
    novel = (
        await db.execute(select(Novel).where(Novel.id == project_id).with_for_update())
    ).scalar_one_or_none()
    if novel is None:
        return None
    novel.character_branch_auto_discovery_enabled = enabled
    return bool(novel.character_branch_auto_discovery_enabled)


def _bounded_json(value: Any, max_chars: int = CHARACTER_BRANCH_ANCHOR_CONTEXT_MAX_CHARS) -> Any:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) <= max_chars:
        return value
    return {"truncated": True, "content": encoded[:max_chars]}


async def _mainline_chapter_limit(db: AsyncSession, project_id) -> int:
    result = await db.execute(
        select(func.max(Chapter.chapter_index)).where(Chapter.novel_id == project_id)
    )
    return int(result.scalar_one() or 0)


async def _build_anchor_context(
    db: AsyncSession,
    project_id,
    card: CharacterCard,
    anchor_main_chapter: int,
    arc: CharacterArc | None,
) -> dict[str, Any]:
    state = await get_state_at_chapter(db, card.id, anchor_main_chapter)
    relationship_result = await db.execute(
        select(CharacterRelationship).where(
            CharacterRelationship.project_id == project_id,
            CharacterRelationship.valid_from_chapter <= anchor_main_chapter,
        )
    )
    relationships = [
        {
            "source_character_id": str(item.source_character_id),
            "target_character_id": str(item.target_character_id),
            "relation_type": item.relation_type,
            "status": item.status,
            "attributes": copy.deepcopy(item.attributes or {}),
            "valid_from_chapter": item.valid_from_chapter,
            "valid_to_chapter": item.valid_to_chapter,
        }
        for item in relationship_result.scalars().all()
        if item.valid_to_chapter is None or item.valid_to_chapter >= anchor_main_chapter
    ]

    chapter_result = await db.execute(
        select(Chapter)
        .where(
            Chapter.novel_id == project_id,
            Chapter.chapter_index <= anchor_main_chapter,
        )
        .order_by(Chapter.chapter_index.desc())
        .limit(20)
    )
    chapter_summaries = []
    anchor_chapter_content = ""
    for chapter in reversed(list(chapter_result.scalars().all())):
        outline = chapter.outline if isinstance(chapter.outline, dict) else {}
        chapter_summaries.append({
            "chapter_index": chapter.chapter_index,
            "title": chapter.title or "",
            "summary": outline.get("summary", ""),
            "end_state": outline.get("end_state", ""),
        })
        if chapter.chapter_index == anchor_main_chapter:
            anchor_chapter_content = (chapter.content or chapter.edited_content or chapter.draft_content or "")[-4000:]

    card_payload = {
        "character_id": str(card.id),
        "name": card.name,
        "aliases": list(card.aliases or []),
        "importance": card.importance,
        "status": card.status,
        "last_appearance": card.last_appearance,
        "card_data": copy.deepcopy(card.card_data or {}),
        "state": copy.deepcopy(state.state_data if state else card.current_state or {}),
        "state_chapter": state.chapter_index if state else None,
    }
    return _bounded_json({
        "anchor_main_chapter": anchor_main_chapter,
        "character": card_payload,
        "arc": {
            "id": str(arc.id) if arc else None,
            "name": arc.name if arc else "",
            "arc_type": arc.arc_type if arc else "",
            "data": copy.deepcopy(arc.data or {}) if arc else {},
        },
        "relationships": relationships,
        "mainline_summaries": chapter_summaries,
        "anchor_chapter_ending": anchor_chapter_content,
        "read_future_mainline": False,
    })


async def get_character_branch(
    db: AsyncSession,
    project_id,
    character_id,
    branch_id,
    *,
    lock: bool = False,
) -> CharacterBranch | None:
    statement = select(CharacterBranch).where(
        CharacterBranch.id == branch_id,
        CharacterBranch.project_id == project_id,
        CharacterBranch.character_id == character_id,
    )
    if lock:
        statement = statement.with_for_update()
    return (await db.execute(statement)).scalar_one_or_none()


async def list_character_arcs(
    db: AsyncSession,
    project_id,
    character_id,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> list[CharacterArc]:
    result = await db.execute(
        _apply_page(
            select(CharacterArc)
            .where(CharacterArc.project_id == project_id, CharacterArc.character_id == character_id)
            .order_by(CharacterArc.arc_type, CharacterArc.created_at, CharacterArc.id),
            limit,
            offset,
        )
    )
    return list(result.scalars().all())


async def list_character_branches(
    db: AsyncSession,
    project_id,
    character_id,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> list[CharacterBranch]:
    result = await db.execute(
        _apply_page(
            select(CharacterBranch)
            .where(CharacterBranch.project_id == project_id, CharacterBranch.character_id == character_id)
            .order_by(CharacterBranch.created_at.desc(), CharacterBranch.id.asc()),
            limit,
            offset,
        )
    )
    return list(result.scalars().all())


async def list_branch_chapters(
    db: AsyncSession,
    branch_id,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> list[CharacterBranchChapter]:
    result = await db.execute(
        _apply_page(
            select(CharacterBranchChapter)
            .where(CharacterBranchChapter.branch_id == branch_id)
            .order_by(CharacterBranchChapter.chapter_index, CharacterBranchChapter.id),
            limit,
            offset,
        )
    )
    return list(result.scalars().all())


async def get_branch_chapter(db: AsyncSession, branch_id, chapter_index, *, lock: bool = False) -> CharacterBranchChapter | None:
    statement = select(CharacterBranchChapter).where(
        CharacterBranchChapter.branch_id == branch_id,
        CharacterBranchChapter.chapter_index == chapter_index,
    )
    if lock:
        statement = statement.with_for_update()
    return (await db.execute(statement)).scalar_one_or_none()


async def create_character_branch(
    db: AsyncSession,
    project_id,
    character_id,
    *,
    arc_id=None,
    title: str | None = None,
    anchor_main_chapter: int | None = None,
    target_chapters: int = CHARACTER_BRANCH_DEFAULT_CHAPTER_COUNT,
    user_request: str = "",
    generation_config: dict[str, Any] | None = None,
    auto_discovered: bool = False,
) -> CharacterBranch:
    card = (await db.execute(
        select(CharacterCard).where(
            CharacterCard.id == character_id,
            CharacterCard.project_id == project_id,
        ).with_for_update()
    )).scalar_one_or_none()
    if card is None:
        raise LookupError("Character card not found")

    current_mainline = await _mainline_chapter_limit(db, project_id)
    anchor = anchor_main_chapter if anchor_main_chapter is not None else card.last_appearance
    if anchor is None or anchor < 1:
        raise ValueError("Character has no usable mainline anchor chapter")
    if anchor > current_mainline:
        raise ValueError("Anchor chapter cannot be after the current mainline")
    if target_chapters < 1 or target_chapters > CHARACTER_BRANCH_MAX_CHAPTER_COUNT:
        raise ValueError(f"target_chapters must be between 1 and {CHARACTER_BRANCH_MAX_CHAPTER_COUNT}")

    arc = None
    if arc_id is not None:
        arc = (await db.execute(
            select(CharacterArc).where(
                CharacterArc.id == arc_id,
                CharacterArc.project_id == project_id,
                CharacterArc.character_id == character_id,
            )
        )).scalar_one_or_none()
        if arc is None:
            raise LookupError("Character arc not found")

    duplicate = (await db.execute(
        select(CharacterBranch.id).where(
            CharacterBranch.character_id == character_id,
            CharacterBranch.arc_id == arc_id,
            CharacterBranch.anchor_main_chapter == anchor,
            CharacterBranch.status.in_(_ACTIVE_BRANCH_STATUSES),
        ).limit(1)
    )).scalar_one_or_none()
    if duplicate is not None:
        raise ValueError("An active branch already exists for this character, arc, and anchor")

    clean_title = (title or CHARACTER_BRANCH_DEFAULT_TITLE_TEMPLATE.format(character_name=card.name)).strip()
    if not clean_title or len(clean_title) > CHARACTER_BRANCH_MAX_TITLE_LENGTH:
        raise ValueError("Branch title is invalid")
    branch_id = uuid.uuid4()
    storyline_id = f"{CHARACTER_BRANCH_STORYLINE_PREFIX}:{branch_id}"
    branch = CharacterBranch(
        id=branch_id,
        project_id=project_id,
        character_id=character_id,
        arc_id=arc_id,
        title=clean_title,
        storyline_id=storyline_id,
        anchor_main_chapter=anchor,
        target_chapters=target_chapters,
        user_request=(user_request or "").strip(),
        generation_config=copy.deepcopy(generation_config or {}),
        anchor_context=await _build_anchor_context(db, project_id, card, anchor, arc),
        auto_discovered=auto_discovered,
    )
    db.add(branch)
    await db.flush()
    return branch


async def create_or_get_branch_chapter(
    db: AsyncSession,
    branch: CharacterBranch,
    chapter_index: int,
) -> CharacterBranchChapter:
    if chapter_index < 1 or chapter_index > branch.target_chapters:
        raise ValueError("Branch chapter index is outside the configured target")
    chapter = await get_branch_chapter(db, branch.id, chapter_index, lock=True)
    if chapter is None:
        chapter = CharacterBranchChapter(
            branch_id=branch.id,
            chapter_index=chapter_index,
            anchor_main_chapter=branch.anchor_main_chapter,
            source_ref=CHARACTER_BRANCH_DEFAULT_SOURCE_REF_TEMPLATE.format(
                branch_id=branch.id,
                chapter_index=chapter_index,
            ),
        )
        db.add(chapter)
        await db.flush()
    return chapter


async def update_branch_chapter_content(
    db: AsyncSession,
    branch: CharacterBranch,
    chapter_index: int,
    *,
    title: str,
    content: str,
) -> CharacterBranchChapter:
    chapter = await get_branch_chapter(db, branch.id, chapter_index, lock=True)
    if chapter is None:
        raise LookupError("Branch chapter not found")
    if branch.status == CHARACTER_BRANCH_STATUS_ARCHIVED:
        raise ValueError("Archived branch cannot be edited")
    clean_title = (title or "").strip()
    clean_content = content or ""
    if not clean_title:
        raise ValueError("Branch chapter title must not be blank")
    chapter.title = clean_title
    chapter.edited_content = clean_content
    chapter.content = clean_content
    chapter.word_count = len(clean_content)
    chapter.status = CHARACTER_BRANCH_CHAPTER_STATUS_DRAFT
    branch.status = CHARACTER_BRANCH_STATUS_DRAFT
    await db.flush()
    return chapter


async def transition_branch_status(db: AsyncSession, branch: CharacterBranch, status: str) -> CharacterBranch:
    if status not in CHARACTER_BRANCH_STATUSES:
        raise ValueError("Invalid branch status")
    allowed = {
        CHARACTER_BRANCH_STATUS_PENDING: {CHARACTER_BRANCH_STATUS_GENERATING, CHARACTER_BRANCH_STATUS_ARCHIVED},
        CHARACTER_BRANCH_STATUS_GENERATING: {CHARACTER_BRANCH_STATUS_DRAFT, CHARACTER_BRANCH_STATUS_READY, CHARACTER_BRANCH_STATUS_FAILED, CHARACTER_BRANCH_STATUS_ARCHIVED},
        CHARACTER_BRANCH_STATUS_DRAFT: {CHARACTER_BRANCH_STATUS_GENERATING, CHARACTER_BRANCH_STATUS_READY, CHARACTER_BRANCH_STATUS_ARCHIVED},
        CHARACTER_BRANCH_STATUS_READY: {CHARACTER_BRANCH_STATUS_GENERATING, CHARACTER_BRANCH_STATUS_ARCHIVED},
        CHARACTER_BRANCH_STATUS_FAILED: {CHARACTER_BRANCH_STATUS_GENERATING, CHARACTER_BRANCH_STATUS_ARCHIVED},
        CHARACTER_BRANCH_STATUS_ARCHIVED: set(),
    }
    if status != branch.status and status not in allowed.get(branch.status, set()):
        raise ValueError(f"Cannot transition branch from {branch.status} to {status}")
    branch.status = status
    await db.flush()
    return branch


async def archive_character_branch(db: AsyncSession, branch: CharacterBranch) -> CharacterBranch:
    await cancel_active_character_branch_jobs(
        db, branch, reason="支线已归档，生成任务已取消"
    )
    await discard_pending_branch_vectors(db, branch.id)
    return await transition_branch_status(db, branch, CHARACTER_BRANCH_STATUS_ARCHIVED)


def _branch_id_from_job(job: Job):
    value = (job.params or {}).get("branch_id")
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


async def active_character_branch_job_ids(
    db: AsyncSession, branch: CharacterBranch
) -> list[uuid.UUID]:
    """Return active branch jobs for in-process task cancellation."""
    result = await db.execute(
        select(Job).where(
            Job.project_id == branch.project_id,
            Job.type == JOB_TYPE_CHARACTER_BRANCH,
            Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING)),
        )
    )
    return [
        job.id for job in result.scalars().all()
        if _branch_id_from_job(job) == branch.id
    ]


async def stop_character_branch_job(
    db: AsyncSession,
    job: Job,
    *,
    reason: str = "支线生成任务已取消",
) -> CharacterBranch | None:
    """Leave a cancelled/stale branch job in a resumable state."""
    branch_id = _branch_id_from_job(job)
    if branch_id is None:
        return None
    branch = (await db.execute(
        select(CharacterBranch).where(
            CharacterBranch.id == branch_id,
            CharacterBranch.project_id == job.project_id,
        ).with_for_update()
    )).scalar_one_or_none()
    if branch is None:
        return None
    if branch.status != CHARACTER_BRANCH_STATUS_ARCHIVED:
        branch.status = CHARACTER_BRANCH_STATUS_DRAFT
        branch.error = reason
        chapter = (await db.execute(
            select(CharacterBranchChapter).where(
                CharacterBranchChapter.branch_id == branch.id,
                CharacterBranchChapter.chapter_index == branch.current_chapter_index + 1,
            ).with_for_update()
        )).scalar_one_or_none()
        if chapter and chapter.status == CHARACTER_BRANCH_CHAPTER_STATUS_GENERATING:
            chapter.status = CHARACTER_BRANCH_CHAPTER_STATUS_DRAFT
            chapter.error = reason
    return branch


async def cancel_active_character_branch_jobs(
    db: AsyncSession,
    branch: CharacterBranch,
    *,
    reason: str,
) -> list[Job]:
    """Cancel queued/running jobs belonging to a branch under its row lock."""
    result = await db.execute(
        select(Job).where(
            Job.project_id == branch.project_id,
            Job.type == JOB_TYPE_CHARACTER_BRANCH,
            Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING)),
        ).with_for_update()
    )
    jobs = [
        job for job in result.scalars().all()
        if _branch_id_from_job(job) == branch.id
    ]
    for job in jobs:
        await stop_character_branch_job(db, job, reason=reason)
        job.status = JobStatus.CANCELLED
        job.error = reason
    return jobs


async def recover_character_branch_job(
    db: AsyncSession,
    job: Job,
    *,
    reason: str,
) -> CharacterBranch | None:
    """Repair branch/chapter state after a worker dies with a RUNNING job."""
    return await stop_character_branch_job(db, job, reason=reason)


async def discover_branch_candidates(db: AsyncSession, project_id) -> list[dict[str, Any]]:
    current_mainline = await _mainline_chapter_limit(db, project_id)
    if current_mainline < 1:
        return []
    result = await db.execute(
        select(CharacterCard).where(
            CharacterCard.project_id == project_id,
            CharacterCard.last_appearance.is_not(None),
        ).order_by(CharacterCard.last_appearance, CharacterCard.name)
    )
    cards = list(result.scalars().all())
    candidates: list[dict[str, Any]] = []
    for card in cards:
        if current_mainline - card.last_appearance < CHARACTER_BRANCH_AUTO_DISCOVERY_MIN_INACTIVE_CHAPTERS:
            continue
        arcs = await list_character_arcs(db, project_id, card.id)
        if not arcs:
            continue
        active = (await db.execute(
            select(CharacterBranch.id).where(
                CharacterBranch.character_id == card.id,
                CharacterBranch.status.in_(_ACTIVE_BRANCH_STATUSES),
            ).limit(1)
        )).scalar_one_or_none()
        if active is not None:
            continue
        candidates.append({
            "character_id": str(card.id),
            "character_name": card.name,
            "anchor_main_chapter": card.last_appearance,
            "arc_ids": [str(arc.id) for arc in arcs],
            "reason": "角色已连续多章未在主线登场，且存在可发展的成长路线",
        })
        if len(candidates) >= CHARACTER_BRANCH_AUTO_DISCOVERY_MAX_CANDIDATES:
            break
    return candidates
