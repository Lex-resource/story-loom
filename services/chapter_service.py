import uuid
from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.novel import Novel, Chapter
from services.chapter_deletion import (
    delete_related_chapter_rows,
    renumber_chapters_after_deletion,
    update_novel_stats_after_delete,
)
from services.chapter_outline_editing import update_chapter_outline_data
from services.chapter_publish import (
    has_extractor_high_risk_review,
    mark_chapter_force_published,
    publish_reviewed_extractor_chapter,
    schedule_post_processing,
)
from services.chapter_editing import validate_and_apply_chapter_edit
from services.chapter_review import ChapterReviewError, apply_review_json
from services.chapter_views import chapter_detail, chapter_list_item
from services.ids import parse_project_id

from services.pipeline_transitions import set_chapter_pipeline_step
from services.pipeline_types import ChapterStatus, PipelineStep
from services.novel_constants import (
    API_STATUS_DELETED,
)



class EditChapterRequest(BaseModel):
    title: str
    content: str


async def edit_chapter(
    project_id: str,
    chapter_index: int,
    data: EditChapterRequest,
    db: AsyncSession = Depends(get_db)
):
    pid = parse_project_id(project_id)
    # Find chapter
    result = await db.execute(
        select(Chapter).where(
            Chapter.novel_id == pid,
            Chapter.chapter_index == chapter_index,
        )
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
        
    # Find novel to get configuration
    result_novel = await db.execute(select(Novel).where(Novel.id == pid))
    novel = result_novel.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404, detail="Project not found")

    val_res = await validate_and_apply_chapter_edit(
        db,
        novel,
        chapter,
        chapter_index,
        data.title,
        data.content,
    )
    
    return {
        "status": chapter.status,
        "validator_result": val_res,
        "errors": val_res["errors"]
    }


async def publish_chapter(project_id: str, chapter_index: int, db: AsyncSession = Depends(get_db)):
    pid = parse_project_id(project_id)
    result = await db.execute(
        select(Chapter).where(
            Chapter.novel_id == pid,
            Chapter.chapter_index == chapter_index,
        )
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    if chapter.status not in [ChapterStatus.PENDING_REVIEW, ChapterStatus.VALIDATED, ChapterStatus.AUDIT_FAILED]:
        raise HTTPException(status_code=400, detail=f"Chapter status is {chapter.status}, not pending_review/validated/audit_failed")

    result_novel = await db.execute(select(Novel).where(Novel.id == pid))
    novel = result_novel.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404, detail="Project not found")

    if chapter.status == ChapterStatus.PENDING_REVIEW and has_extractor_high_risk_review(chapter):
        await publish_reviewed_extractor_chapter(db, novel, chapter)
        await db.commit()
        return {"status": ChapterStatus.PUBLISHED}

    mark_chapter_force_published(chapter)
    
    await db.commit()

    schedule_post_processing(pid, chapter_index)
    return {"status": ChapterStatus.POST_PROCESSING}


class ReviewJsonRequest(BaseModel):
    step: str
    corrected_json: dict


async def review_json(
    project_id: str,
    chapter_index: int,
    data: ReviewJsonRequest,
    db: AsyncSession = Depends(get_db)
):
    pid = parse_project_id(project_id)
    result = await db.execute(
        select(Chapter).where(
            Chapter.novel_id == pid,
            Chapter.chapter_index == chapter_index,
        )
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
        
    result_novel = await db.execute(select(Novel).where(Novel.id == pid))
    novel = result_novel.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return await apply_review_json(db, novel, chapter, data.step, data.corrected_json)
    except ChapterReviewError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


async def get_chapters(project_id: str, db: AsyncSession = Depends(get_db)):
    pid = parse_project_id(project_id)
    result = await db.execute(
        select(Chapter).where(Chapter.novel_id == pid).order_by(Chapter.chapter_index)
    )
    chapters = result.scalars().all()
    return [chapter_list_item(chapter) for chapter in chapters]


async def get_chapter(project_id: str, chapter_index: int, db: AsyncSession = Depends(get_db)):
    pid = parse_project_id(project_id)
    result = await db.execute(
        select(Chapter).where(
            Chapter.novel_id == pid,
            Chapter.chapter_index == chapter_index,
        )
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter_detail(chapter)


async def delete_chapter(project_id: str, chapter_index: int, db: AsyncSession = Depends(get_db)):
    pid = parse_project_id(project_id)

    # 1. Find and delete the target chapter
    result = await db.execute(
        select(Chapter).where(Chapter.novel_id == pid, Chapter.chapter_index == chapter_index)
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    await db.delete(chapter)

    # 2. Delete + renumber related indexed entities (outline, doc versions, issues, usage, outbox)
    await delete_related_chapter_rows(db, pid, chapter_index)

    # 3. Renumber subsequent chapters (chapter row already deleted via ORM)
    await renumber_chapters_after_deletion(db, pid, chapter_index)
    await db.flush()

    # 4. Update Novel stats from actual chapter count
    result_novel = await db.execute(select(Novel).where(Novel.id == pid))
    novel = result_novel.scalar_one_or_none()
    written_count = 0
    if novel:
        written_count = await update_novel_stats_after_delete(db, pid, novel)

    # 5. Single atomic commit for all deletions + renumbering
    await db.commit()

    # 6. Refresh issue summaries (non-critical, best-effort)
    try:
        from services.issues import update_project_issue_summaries
        await update_project_issue_summaries(db, pid)
        await db.commit()
    except Exception as ie:
        print(f"[Router ERROR] Background issue summaries update failed after delete: {ie}")

    return {
        "status": API_STATUS_DELETED,
        "current_chapter": written_count,
        "written_count": written_count,
        "total_chars": novel.total_chars if novel else 0,
    }



class UpdateOutlineRequest(BaseModel):
    outline: dict


async def update_chapter_outline(
    project_id: str,
    chapter_index: int,
    data: UpdateOutlineRequest,
    db: AsyncSession = Depends(get_db)
):
    pid = parse_project_id(project_id)
    
    # Find Chapter
    result = await db.execute(
        select(Chapter).where(Chapter.novel_id == pid, Chapter.chapter_index == chapter_index)
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return await update_chapter_outline_data(db, pid, chapter, chapter_index, data.outline)


async def get_chapter_by_index(db: AsyncSession, novel_id, chapter_index: int):
    """按 (novel_id, chapter_index) 查询 Chapter，不存在返回 None。"""
    result = await db.execute(
        select(Chapter).where(
            Chapter.novel_id == novel_id,
            Chapter.chapter_index == chapter_index
        )
    )
    return result.scalar_one_or_none()


async def get_chapter_or_404(db: AsyncSession, novel_id, chapter_index: int) -> Chapter:
    """按 (novel_id, chapter_index) 查询 Chapter，不存在则抛 404。"""
    chapter = await get_chapter_by_index(db, novel_id, chapter_index)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter



