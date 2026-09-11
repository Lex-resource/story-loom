"""Non-blocking full-manuscript review for completed short stories."""

from __future__ import annotations

from sqlalchemy import select

from agents.writing.validator_agent import ValidatorAgent
from models.novel import Chapter
from services.novel_constants import SHORT_MANUSCRIPT_CONTEXT_MAX_CHARS
from services.short_story_context import build_short_manuscript_context
from services.workflow_surface import is_short_form_workflow


def should_review_completed_short_story(novel, chapter_index: int) -> bool:
    # 按表面策略而不是格式名判断：从短篇克隆出来的自定义工作流也要做完结全文审校，
    # 否则它拿到短篇提示词却永远不做终局审校 —— 静默地少一道质量闸门。
    return bool(
        is_short_form_workflow(novel.novel_format)
        and novel.target_chapters
        and chapter_index >= novel.target_chapters
    )


def append_full_story_review_flag(chapter, report: dict) -> None:
    flags = chapter.review_flags if isinstance(chapter.review_flags, list) else []
    flags = [flag for flag in flags if flag.get("type") != "short_story_full_review"]
    message = report.get("summary") or "短篇全文审校已完成。"
    chapter.review_flags = flags + [{
        "type": "short_story_full_review",
        "severity": "info" if report.get("passed", False) else "warning",
        "message": message,
        "detail": message,
        "report": report,
    }]


async def review_completed_short_story(db, novel, chapter_index: int) -> dict | None:
    if not should_review_completed_short_story(novel, chapter_index):
        return None

    result = await db.execute(
        select(Chapter)
        .where(Chapter.novel_id == novel.id, Chapter.chapter_index <= novel.target_chapters)
        .order_by(Chapter.chapter_index.asc())
    )
    chapters = result.scalars().all()
    if len(chapters) < novel.target_chapters:
        return None

    manuscript = build_short_manuscript_context(
        chapters,
        max_chars=SHORT_MANUSCRIPT_CONTEXT_MAX_CHARS,
    )
    report = await ValidatorAgent().review_full_story(
        title=novel.title,
        outline=novel.outline or {},
        manuscript=manuscript,
        category=novel.novel_format,
    )
    append_full_story_review_flag(chapters[-1], report)
    await db.commit()
    return report
