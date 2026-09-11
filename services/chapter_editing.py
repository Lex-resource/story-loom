import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel import Chapter
from services.novel_constants import DEFAULT_WORD_COUNT_PER_CHAPTER, PREVIOUS_CHAPTER_ENDING_CHARS
from services.pipeline_transitions import set_chapter_pipeline_step
from services.pipeline_types import ChapterStatus, PipelineStep
from services.chapter_progress import assert_chapter_not_frozen
from services.validator import validate_chapter


async def previous_chapter_ending(
    db: AsyncSession,
    novel_id,
    chapter_index: int,
) -> str:
    prev_result = await db.execute(
        select(Chapter).where(
            Chapter.novel_id == novel_id,
            Chapter.chapter_index == chapter_index - 1,
        )
    )
    prev_chapter = prev_result.scalar_one_or_none()
    if not prev_chapter or not prev_chapter.content:
        return ""
    return prev_chapter.content[-PREVIOUS_CHAPTER_ENDING_CHARS:]


async def validate_and_apply_chapter_edit(
    db: AsyncSession,
    novel,
    chapter,
    chapter_index: int,
    title: str,
    content: str,
) -> dict:
    assert_chapter_not_frozen(chapter)
    ending = await previous_chapter_ending(db, novel.id, chapter_index)
    validator_result = validate_chapter(
        content,
        title,
        (
            novel.word_count_per_chapter
            if novel.word_count_per_chapter is not None
            else DEFAULT_WORD_COUNT_PER_CHAPTER
        ),
        ending,
    )

    chapter.title = validator_result.get("cleaned_title", title)
    chapter.edited_content = validator_result.get("cleaned_content", content)
    chapter.content = chapter.edited_content
    chapter.validator_result = validator_result

    if validator_result["passed"]:
        chapter.status = ChapterStatus.VALIDATED
        set_chapter_pipeline_step(chapter, PipelineStep.VALIDATING)
        chapter.error = None
    else:
        chapter.status = ChapterStatus.AUDIT_FAILED
        set_chapter_pipeline_step(chapter, PipelineStep.VALIDATING, update_status=False)
        chapter.error = json.dumps(validator_result["errors"])

    await db.commit()
    return validator_result
