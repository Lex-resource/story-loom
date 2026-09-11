import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.novel import Novel, Chapter
from services.chapter_deletion import (
    ChapterDeletionError,
    assert_chapter_deletable,
    lock_project_for_chapter_deletion,
    delete_related_chapter_rows,
    renumber_chapters_after_deletion,
    update_novel_stats_after_delete,
)
from services.chapter_outline_editing import update_chapter_outline_data
from services.chapter_publish import (
    enqueue_post_processing_job,
    has_extractor_high_risk_review,
    mark_chapter_force_published,
    publish_reviewed_extractor_chapter,
)
from services.chapter_progress import FrozenChapterError, assert_chapter_not_frozen
from services.chapter_editing import validate_and_apply_chapter_edit
from services.chapter_review import ChapterReviewError, apply_review_json
from services.chapter_views import chapter_detail, chapter_list_item
from services.experiment_publication import record_published_chapter_for_project

from services.pipeline_transitions import set_chapter_pipeline_step
from services.pipeline_types import ChapterStatus, PipelineStep
from services.novel_constants import (
    API_STATUS_DELETED,
)


import logging

logger = logging.getLogger(__name__)



async def edit_chapter(
    db: AsyncSession,
    pid: uuid.UUID,
    chapter_index: int,
    title: str,
    content: str,
):
    result = await db.execute(
        select(Chapter).where(
            Chapter.novel_id == pid,
            Chapter.chapter_index == chapter_index,
        )
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise LookupError("Chapter not found")
        
    # Find novel to get configuration
    result_novel = await db.execute(select(Novel).where(Novel.id == pid))
    novel = result_novel.scalar_one_or_none()
    if not novel:
        raise LookupError("Project not found")

    try:
        val_res = await validate_and_apply_chapter_edit(
            db,
            novel,
            chapter,
            chapter_index,
            title,
            content,
        )
    except FrozenChapterError:
        raise
    
    return {
        "status": chapter.status,
        "validator_result": val_res,
        "errors": val_res["errors"],
    }


async def publish_chapter(db: AsyncSession, pid: uuid.UUID, chapter_index: int):
    result = await db.execute(
        select(Chapter).where(
            Chapter.novel_id == pid,
            Chapter.chapter_index == chapter_index,
        )
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise LookupError("Chapter not found")

    try:
        assert_chapter_not_frozen(chapter)
    except FrozenChapterError as error:
        raise error
    if chapter.status not in [ChapterStatus.PENDING_REVIEW, ChapterStatus.VALIDATED, ChapterStatus.AUDIT_FAILED]:
        raise ValueError(f"Chapter status is {chapter.status}, not pending_review/validated/audit_failed")

    result_novel = await db.execute(select(Novel).where(Novel.id == pid))
    novel = result_novel.scalar_one_or_none()
    if not novel:
        raise LookupError("Project not found")

    if chapter.status == ChapterStatus.PENDING_REVIEW and has_extractor_high_risk_review(chapter):
        await publish_reviewed_extractor_chapter(db, novel, chapter)
        await db.commit()
        await record_published_chapter_for_project(
            db,
            pid,
            chapter_index,
            publication_source="reviewed_extractor_publish",
        )
        return {"status": ChapterStatus.PUBLISHED}

    mark_chapter_force_published(chapter)
    await enqueue_post_processing_job(db, pid, chapter_index)
    await db.commit()
    return {"status": ChapterStatus.POST_PROCESSING}


async def review_json(
    db: AsyncSession,
    pid: uuid.UUID,
    chapter_index: int,
    step: str,
    corrected_json: dict,
):
    result = await db.execute(
        select(Chapter).where(
            Chapter.novel_id == pid,
            Chapter.chapter_index == chapter_index,
        )
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise LookupError("Chapter not found")
    try:
        assert_chapter_not_frozen(chapter)
    except FrozenChapterError as error:
        raise error
        
    result_novel = await db.execute(select(Novel).where(Novel.id == pid))
    novel = result_novel.scalar_one_or_none()
    if not novel:
        raise LookupError("Project not found")

    try:
        return await apply_review_json(db, novel, chapter, step, corrected_json)
    except ChapterReviewError:
        raise


async def get_chapters(db: AsyncSession, pid: uuid.UUID):
    result = await db.execute(
        select(Chapter).where(Chapter.novel_id == pid).order_by(Chapter.chapter_index)
    )
    chapters = result.scalars().all()
    return [chapter_list_item(chapter) for chapter in chapters]


async def get_chapter(db: AsyncSession, pid: uuid.UUID, chapter_index: int):
    result = await db.execute(
        select(Chapter).where(
            Chapter.novel_id == pid,
            Chapter.chapter_index == chapter_index,
        )
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise LookupError("Chapter not found")
    return chapter_detail(chapter)


async def delete_chapter(db: AsyncSession, pid: uuid.UUID, chapter_index: int):

    try:
        novel = await lock_project_for_chapter_deletion(db, pid)
        if novel is None:
            raise LookupError("Project not found")
        await assert_chapter_deletable(db, pid, chapter_index)
    except ChapterDeletionError as error:
        raise error

    # 1. Find and delete the target chapter
    result = await db.execute(
        select(Chapter).where(Chapter.novel_id == pid, Chapter.chapter_index == chapter_index)
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise LookupError("Chapter not found")
    await db.delete(chapter)

    # 2. Delete + renumber related indexed entities (outline, doc versions, issues, usage, outbox)
    await delete_related_chapter_rows(db, pid, chapter_index)

    # 3. Renumber subsequent chapters (chapter row already deleted via ORM)
    await renumber_chapters_after_deletion(db, pid, chapter_index)
    await db.flush()

    # 4. Update Novel stats from actual chapter count
    written_count = await update_novel_stats_after_delete(db, pid, novel)

    # 5. Single atomic commit for all deletions + renumbering
    await db.commit()

    if chapter_index:
        try:
            from services.vector_chroma import delete_collection_where

            await delete_collection_where(
                f"project_{pid}", {"chapter_index": chapter_index}
            )
        except Exception:
            logger.exception(
                "chapter_vector_cleanup_failed project_id=%s chapter_index=%s",
                pid,
                chapter_index,
            )

    # 6. Refresh issue summaries (non-critical, best-effort)
    try:
        from services.issues import update_project_issue_summaries
        await update_project_issue_summaries(db, pid)
        await db.commit()
    except Exception as ie:
        logger.error(f"[Router ERROR] Background issue summaries update failed after delete: {ie}")

    return {
        "status": API_STATUS_DELETED,
        "current_chapter": written_count,
        "written_count": written_count,
        "total_chars": novel.total_chars if novel else 0,
    }



async def update_chapter_outline(
    db: AsyncSession,
    pid: uuid.UUID,
    chapter_index: int,
    outline: dict,
):
    result = await db.execute(
        select(Chapter).where(Chapter.novel_id == pid, Chapter.chapter_index == chapter_index)
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise LookupError("Chapter not found")
    try:
        assert_chapter_not_frozen(chapter)
    except FrozenChapterError as error:
        raise error
    return await update_chapter_outline_data(db, pid, chapter, chapter_index, outline)


async def get_chapter_by_index(db: AsyncSession, novel_id, chapter_index: int):
    """按 (novel_id, chapter_index) 查询 Chapter，不存在返回 None。"""
    result = await db.execute(
        select(Chapter).where(
            Chapter.novel_id == novel_id,
            Chapter.chapter_index == chapter_index
        )
    )
    return result.scalar_one_or_none()


async def get_chapter_or_raise(db: AsyncSession, novel_id, chapter_index: int) -> Chapter:
    """按 (novel_id, chapter_index) 查询 Chapter，不存在则抛 LookupError。"""
    chapter = await get_chapter_by_index(db, novel_id, chapter_index)
    if not chapter:
        raise LookupError("Chapter not found")
    return chapter



