import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from models.novel import Chapter


def chapter_chars_expr():
    """Prefer persisted word_count; fall back to best available body text length."""
    return func.coalesce(
        Chapter.word_count,
        func.char_length(
            func.coalesce(Chapter.content, Chapter.edited_content, Chapter.draft_content, "")
        ),
    )


def chapter_chars_from_row(chapter: Chapter) -> int:
    """Python-side counterpart of :func:`chapter_chars_expr`.

    Returns the canonical character count for a chapter loaded into memory:
    prefer the persisted ``word_count`` field, otherwise fall back to the
    first non-empty body text (content → edited_content → draft_content).

    Used by worker_support (merger / generate_job_runner) and chapter_service
    to ensure all layers compute chapter length consistently. Replaces the
    buggy ``len(chapter.content) if chapter.content else 0`` pattern that
    ignored edited_content / draft_content and double-counted word_count.
    """
    if chapter.word_count:
        return int(chapter.word_count)
    text = chapter.content or chapter.edited_content or chapter.draft_content or ""
    return len(text)


async def sum_project_chars(db: AsyncSession, novel_id: uuid.UUID) -> int:
    res = await db.execute(
        select(func.coalesce(func.sum(chapter_chars_expr()), 0)).where(
            Chapter.novel_id == novel_id
        )
    )
    return int(res.scalar() or 0)
