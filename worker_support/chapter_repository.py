"""Persistence helpers for chapter generation workers."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.chapter_domain import ChapterDomain
from models.character_branches import CharacterBranchChapter
from models.novel import Chapter, ChapterOutline, RawIssue
from services.pipeline_transitions import set_chapter_pipeline_step
from services.pipeline_types import PipelineStep
from core.pipeline_vocab import ChapterStatus


async def get_chapter_by_index(
    db: AsyncSession,
    novel_id: uuid.UUID,
    chapter_index: int,
    *,
    domain: ChapterDomain | None = None,
) -> Chapter | CharacterBranchChapter | None:
    if domain is not None and domain.branch_id is not None:
        result = await db.execute(
            select(CharacterBranchChapter).where(
                CharacterBranchChapter.branch_id == domain.branch_id,
                CharacterBranchChapter.chapter_index == chapter_index,
            )
        )
        return result.scalar_one_or_none()
    result = await db.execute(
        select(Chapter).where(
            Chapter.novel_id == novel_id,
            Chapter.chapter_index == chapter_index,
        )
    )
    return result.scalar_one_or_none()


async def get_or_create_chapter(
    db: AsyncSession,
    novel_id: uuid.UUID,
    chapter_index: int,
    *,
    title: str,
    outline: dict[str, Any] | None = None,
) -> Chapter:
    if domain is not None and domain.branch_id is not None:
        return await _get_or_create_branch_chapter(
            db, domain, chapter_index, title=title, outline=outline
        )
    chapter = await get_chapter_by_index(db, novel_id, chapter_index)
    if chapter:
        return chapter

    chapter = Chapter(
        novel_id=novel_id,
        chapter_index=chapter_index,
        title=title,
        outline=outline,
    )
    db.add(chapter)
    return chapter



async def _get_or_create_branch_chapter(
    db: AsyncSession,
    domain: ChapterDomain,
    chapter_index: int,
    *,
    title: str,
    outline: dict[str, Any] | None,
) -> CharacterBranchChapter:
    chapter = await get_chapter_by_index(
        db, domain.project_id, chapter_index, domain=domain
    )
    if chapter:
        return chapter
    chapter = CharacterBranchChapter(
        branch_id=domain.branch_id,
        chapter_index=chapter_index,
        anchor_main_chapter=domain.anchor_main_chapter or 0,
        title=title,
        outline=outline,
    )
    db.add(chapter)
    return chapter

async def prepare_chapter_for_step(
    db: AsyncSession,
    chapter: Chapter | None,
    novel_id: uuid.UUID,
    chapter_index: int,
    start_step: str,
    *,
    domain: ChapterDomain | None = None,
) -> Chapter:
    pipeline_step = PipelineStep.OUTLINE if start_step == "planner" else PipelineStep.WRITING

    if domain is not None and domain.branch_id is not None:
        # 支线域:章节状态走支线枚举,无 pipeline_step 概念
        from core.character_vocab import CHARACTER_BRANCH_CHAPTER_STATUS_DRAFT

        if chapter:
            chapter.status = CHARACTER_BRANCH_CHAPTER_STATUS_DRAFT
            return chapter
        chapter = CharacterBranchChapter(
            branch_id=domain.branch_id,
            chapter_index=chapter_index,
            anchor_main_chapter=domain.anchor_main_chapter or 0,
            title=f"支线第{chapter_index}章",
            status=CHARACTER_BRANCH_CHAPTER_STATUS_DRAFT,
        )
        db.add(chapter)
        return chapter

    if chapter:
        if start_step not in ["validator", "extractor"]:
            chapter.status = ChapterStatus.DRAFT
            set_chapter_pipeline_step(chapter, pipeline_step)
        return chapter

    chapter = Chapter(
        novel_id=novel_id,
        chapter_index=chapter_index,
        title=f"第{chapter_index}章",
        status="draft",
        pipeline_step=pipeline_step,
    )
    db.add(chapter)
    return chapter


async def get_succeeding_chapter_beginning(
    db: AsyncSession,
    novel_id: uuid.UUID,
    chapter_index: int,
    *,
    max_chars: int,
    domain: ChapterDomain | None = None,
) -> str:
    chapter = await get_chapter_by_index(db, novel_id, chapter_index + 1, domain=domain)
    return chapter.content[:max_chars] if chapter and chapter.content else ""


async def load_existing_outline(
    db: AsyncSession,
    novel_id: uuid.UUID,
    chapter_index: int,
    *,
    domain: ChapterDomain | None = None,
) -> dict[str, Any] | None:
    chapter = await get_chapter_by_index(db, novel_id, chapter_index, domain=domain)
    if chapter and chapter.outline:
        return chapter.outline
    if domain is not None and domain.branch_id is not None:
        return None  # 支线域无 ChapterOutline 表

    outline_rows = await _get_chapter_outline_rows(db, novel_id, chapter_index)
    if outline_rows and outline_rows[0].outline:
        return outline_rows[0].outline
    return None


async def save_planner_outline(
    db: AsyncSession,
    novel_id: uuid.UUID,
    chapter_index: int,
    outline_data: dict[str, Any],
    *,
    domain: ChapterDomain | None = None,
) -> None:
    if domain is not None and domain.branch_id is not None:
        # 支线域:大纲直接写支线章节行,无 ChapterOutline 表
        chapter = await get_chapter_by_index(
            db, domain.project_id, chapter_index, domain=domain
        )
        if chapter:
            chapter.outline = outline_data
            if outline_data and "title" in outline_data:
                chapter.title = outline_data["title"]
        return
    outline_rows = await _get_chapter_outline_rows(db, novel_id, chapter_index)
    if outline_rows:
        outline_rows[0].outline = outline_data
        for duplicate in outline_rows[1:]:
            await db.delete(duplicate)
    else:
        db.add(
            ChapterOutline(
                project_id=novel_id,
                chapter_index=chapter_index,
                outline=outline_data,
                source="planner",
            )
        )


async def sync_chapter_outline(
    db: AsyncSession,
    novel_id: uuid.UUID,
    chapter_index: int,
    outline_data: dict[str, Any],
    *,
    domain: ChapterDomain | None = None,
) -> None:
    chapter = await get_chapter_by_index(db, novel_id, chapter_index, domain=domain)
    if not chapter:
        return

    chapter.outline = outline_data
    if outline_data and "title" in outline_data:
        chapter.title = outline_data["title"]


async def save_editor_raw_issues(
    db: AsyncSession,
    novel_id: uuid.UUID,
    chapter_index: int,
    raw_issues: list[dict[str, Any]],
    *,
    domain: ChapterDomain | None = None,
) -> None:
    if domain is not None and domain.branch_id is not None:
        return  # RawIssue 是主线审核面,支线域不写
    for issue in raw_issues:
        db.add(
            RawIssue(
                project_id=novel_id,
                chapter_index=chapter_index,
                category=issue.get("category"),
                description=issue.get("description"),
                severity=issue.get("severity"),
                source="editor",
            )
        )


async def _get_chapter_outline_rows(
    db: AsyncSession,
    novel_id: uuid.UUID,
    chapter_index: int,
) -> list[ChapterOutline]:
    result = await db.execute(
        select(ChapterOutline).where(
            ChapterOutline.project_id == novel_id,
            ChapterOutline.chapter_index == chapter_index,
        )
    )
    return list(result.scalars().all())
