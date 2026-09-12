from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services import pipeline_service
from services.ids import parse_project_id
from services.experiment_types import ExperimentConfig
from services.novel_constants import DEFAULT_BATCH_SIZE
from services.pipeline_types import JobStatus
from worker_support.task_registry import cancel_and_wait


router = APIRouter()

class GenerateRequest(BaseModel):
    batch_size: int = Field(default=DEFAULT_BATCH_SIZE, ge=1, le=100)
    word_count_per_chapter: int | None = Field(default=None, ge=0, le=100_000)
    experiment: ExperimentConfig | None = None


class RewriteRequest(BaseModel):
    use_existing_outline: bool = True
    custom_prompt: str | None = Field(default=None, max_length=20_000)
    chapter_index: int | None = Field(default=None, ge=1, le=10_000)


@router.post("/{project_id}/generate")
async def generate(project_id: str, data: GenerateRequest | None = None, db: AsyncSession = Depends(get_db)):
    try:
        pid = parse_project_id(project_id)
        request = data or GenerateRequest()
        return await pipeline_service.generate(
            db,
            pid,
            batch_size=request.batch_size,
            word_count_per_chapter=request.word_count_per_chapter,
            experiment=request.experiment.model_dump(exclude_none=True) if request.experiment else None,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{project_id}/pause")
async def pause(project_id: str, db: AsyncSession = Depends(get_db)):
    return await pipeline_service.pause(db, parse_project_id(project_id))


@router.post("/{project_id}/resume")
async def resume(project_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await pipeline_service.resume(db, parse_project_id(project_id))
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/{project_id}/rewrite")
async def rewrite(project_id: str, data: RewriteRequest, db: AsyncSession = Depends(get_db)):
    """rewrite 会把 RUNNING 的 generate job 复位 PENDING 供重新抢占。

    复位前先取消本进程内可能还挂着的旧任务并等它完全退出，避免同一章节
    被新旧两个 asyncio 任务并发写。外部 worker 模式下本进程注册表为空，
    这里是无害的 no-op，跨进程由 check_paused 检查点兜底。
    """
    pid = parse_project_id(project_id)
    latest_job_id = await pipeline_service.latest_generate_job_id(db, pid)
    if latest_job_id:
        await cancel_and_wait(str(latest_job_id))
    try:
        return await pipeline_service.rewrite(
            db,
            pid,
            use_existing_outline=data.use_existing_outline,
            custom_prompt=data.custom_prompt,
            chapter_index=data.chapter_index,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


