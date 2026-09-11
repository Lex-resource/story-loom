from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel import Chapter, ChapterOutline
from services.novel_constants import OUTLINE_SOURCE_EDITOR
from services.chapter_progress import assert_chapter_not_frozen


async def update_chapter_outline_data(
    db: AsyncSession,
    pid,
    chapter: Chapter,
    chapter_index: int,
    outline: dict,
) -> dict:
    assert_chapter_not_frozen(chapter)
    chapter.outline = outline
    if isinstance(outline, dict) and "title" in outline:
        chapter.title = outline["title"]

    result = await db.execute(
        select(ChapterOutline).where(
            ChapterOutline.project_id == pid,
            ChapterOutline.chapter_index == chapter_index,
        )
    )
    outlines = result.scalars().all()
    if outlines:
        primary_outline = outlines[0]
        primary_outline.outline = outline
        for duplicate in outlines[1:]:
            await db.delete(duplicate)
    else:
        db.add(
            ChapterOutline(
                project_id=pid,
                chapter_index=chapter_index,
                outline=outline,
                source=OUTLINE_SOURCE_EDITOR,
            )
        )

    await db.commit()
    return {"status": "ok", "outline": chapter.outline}
