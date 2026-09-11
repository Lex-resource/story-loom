from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db

from services import chapter_service
from services.chapter_deletion import ChapterDeletionError
from services.chapter_progress import FrozenChapterError
from services.chapter_review import ChapterReviewError
from services.ids import parse_project_id


router = APIRouter()

class EditChapterRequest(BaseModel):
    title: str
    content: str


class ReviewJsonRequest(BaseModel):
    step: str
    corrected_json: dict


class UpdateOutlineRequest(BaseModel):
    outline: dict


def _pid(project_id: str) -> uuid.UUID:
    return parse_project_id(project_id)


@router.get("/{project_id}/chapters")
async def get_chapters(project_id: str, db: AsyncSession = Depends(get_db)):
    return await chapter_service.get_chapters(db, _pid(project_id))


@router.get("/{project_id}/chapters/{chapter_index}")
async def get_chapter(project_id: str, chapter_index: int, db: AsyncSession = Depends(get_db)):
    try:
        return await chapter_service.get_chapter(db, _pid(project_id), chapter_index)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete("/{project_id}/chapters/{chapter_index}")
async def delete_chapter(project_id: str, chapter_index: int, db: AsyncSession = Depends(get_db)):
    try:
        return await chapter_service.delete_chapter(db, _pid(project_id), chapter_index)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ChapterDeletionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{project_id}/chapters/{chapter_index}/edit")
async def edit_chapter(
    project_id: str,
    chapter_index: int,
    data: EditChapterRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await chapter_service.edit_chapter(
            db, _pid(project_id), chapter_index, data.title, data.content
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except FrozenChapterError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{project_id}/chapters/{chapter_index}/outline")
async def update_chapter_outline(
    project_id: str,
    chapter_index: int,
    data: UpdateOutlineRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await chapter_service.update_chapter_outline(
            db, _pid(project_id), chapter_index, data.outline
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except FrozenChapterError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{project_id}/chapters/{chapter_index}/review_json")
async def review_json(
    project_id: str,
    chapter_index: int,
    data: ReviewJsonRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await chapter_service.review_json(
            db, _pid(project_id), chapter_index, data.step, data.corrected_json
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except FrozenChapterError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ChapterReviewError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/{project_id}/publish/{chapter_index}")
async def publish_chapter(project_id: str, chapter_index: int, db: AsyncSession = Depends(get_db)):
    try:
        return await chapter_service.publish_chapter(db, _pid(project_id), chapter_index)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except FrozenChapterError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
