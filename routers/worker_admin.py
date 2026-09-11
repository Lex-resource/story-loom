"""worker 控制端点：/api/worker/*。

分层：DB/状态查询在 services/worker_admin_service.py；task_registry 的
进程内操作直接在这里调用（routers import worker_support 合法，先例
routers/pipeline.py）。服务在 services 层不能反向 import worker_support。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services import worker_admin_service
from services.ids import parse_job_id
from worker_support.task_registry import active_count, cancel_and_wait, has_capacity

router = APIRouter()


@router.get("/status")
async def worker_status():
    """队列深度、活跃任务、暂停开关、运行模式。前端轮询渲染。"""
    status = await worker_admin_service.worker_status()
    # 进程内注册表状态：外部 worker 模式下本进程注册表为空，属预期。
    status["active_tasks"] = active_count()
    status["has_capacity"] = has_capacity()
    return status


@router.post("/pause-claim")
async def pause_claim():
    """暂停领取新任务。在跑任务继续到检查点，不是杀任务。"""
    values = await worker_admin_service.set_claim_paused(True)
    return {"status": "ok", "claim_paused": values["worker_claim_paused"]}


@router.post("/resume-claim")
async def resume_claim():
    values = await worker_admin_service.set_claim_paused(False)
    return {"status": "ok", "claim_paused": values["worker_claim_paused"]}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """取消任务：先取消进程内 asyncio 任务（外部模式为无害 no-op），再置 CANCELLED。"""
    await cancel_and_wait(job_id)
    job = await worker_admin_service.cancel_job(db, parse_job_id(job_id))
    if job is None:
        raise HTTPException(status_code=409, detail="任务不存在或已是终态（completed/failed/cancelled），无法取消")
    return {"status": "ok", "job_id": str(job.id), "job_status": str(job.status)}


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """重试任务：PAUSED/FAILED/CANCELLED → PENDING，复用 resume 的锚点复位路径。"""
    job = await worker_admin_service.retry_job(db, parse_job_id(job_id))
    if job is None:
        raise HTTPException(
            status_code=409,
            detail="任务不存在，或仍在排队/运行/已完成，无法重试",
        )
    return {"status": "ok", "job_id": str(job.id), "job_status": str(job.status)}
