"""实验上下文:contextvar 生命周期与从 job 参数构造。

deactivate/adeactivate 的双版本语义见 _io 模块注释:同步版原地等屏障,
async 版把等待下放 executor 线程,contextvar 必须在原任务上下文里 reset。
"""

from __future__ import annotations

import asyncio
import contextvars
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import settings

from services.experiment_recorder._io import (
    _await_io_work,
    _flush_pending_writes,
    _pending_writes,
    _pending_writes_lock,
)


@dataclass
class ExperimentContext:
    run_id: str
    prompt_version: str
    variant: str
    project_id: str
    chapter_index: int
    root_dir: Path
    started_at: float = field(default_factory=time.perf_counter)
    api_retry_count: int = 0
    json_recovery_count: int = 0
    llm_call_count: int = 0
    content_retry_count: int = 0
    llm_attempt_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    memory_context_values: list[int] = field(default_factory=list)
    chapter_finished_recorded: bool = False

    @property
    def run_dir(self) -> Path:
        return self.root_dir / self.run_id


_current: contextvars.ContextVar[ExperimentContext | None] = contextvars.ContextVar(
    "novel_experiment_context",
    default=None,
)


def context_from_job(job, project_id: Any, chapter_index: int) -> ExperimentContext | None:
    params = getattr(job, "params", None)
    experiment = params.get("experiment") if isinstance(params, dict) else None
    if not isinstance(experiment, dict):
        return None
    run_id = str(experiment.get("run_id") or f"run-{uuid.uuid4().hex[:12]}")
    return ExperimentContext(
        run_id=run_id,
        prompt_version=str(experiment.get("prompt_version") or "V0"),
        variant=str(experiment.get("variant") or "baseline"),
        project_id=str(project_id),
        chapter_index=int(chapter_index),
        root_dir=Path(
            experiment.get("root_dir")
            or (Path(settings.DATA_DIR) / "research_runs")
        ),
    )


def activate(context: ExperimentContext | None):
    return _current.set(context)


def deactivate(token) -> None:
    # 屏障：实验上下文结束时所有排队写盘必须已落盘，恢复"同步写"的旧语义。
    # 同步语义版本（测试/研究脚本）；async 调用点用 adeactivate —— 几十 MB
    # 快照排队时这里的同步等待会冻结事件循环秒级（S5/S6/S7 同类残余）。
    _flush_pending_writes()
    _current.reset(token)


async def adeactivate(token) -> None:
    """deactivate 的 async 版：contextvar 必须在原任务上下文里 reset，
    flush 等待下放工作线程（S7 的"等"半边，与"写"半边同修）。"""
    _current.reset(token)
    with _pending_writes_lock:
        pending = tuple(_pending_writes)
    if not any(not f.done() for f in pending):
        return  # 快路径：无排队写盘
    await _await_io_work(asyncio.to_thread(_flush_pending_writes))


def current() -> ExperimentContext | None:
    return _current.get()



