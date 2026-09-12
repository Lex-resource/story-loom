"""章节完结记录:发布路径的读-改-写幂等收尾。

幂等判断要读到排队的写盘:flush 后重放 events,已 completed 则跳过。
带全局锁,多 worker 同时发布同一章不会重复追加 chapter_finished。
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any

from config import settings

from services.experiment_recorder._context import ExperimentContext, current
from services.experiment_recorder._events import _write_event, record_chapter_finished
from services.experiment_recorder._io import (
    _await_io_work,
    _flush_pending_writes,
    _io_executor,
)


_publication_record_lock = threading.Lock()


def _experiment_context_from_payload(
    experiment: dict[str, Any], project_id: Any, chapter_index: int
) -> ExperimentContext:
    return ExperimentContext(
        run_id=str(experiment.get("run_id") or "run-unknown"),
        prompt_version=str(experiment.get("prompt_version") or "V0"),
        variant=str(experiment.get("variant") or "baseline"),
        project_id=str(project_id),
        chapter_index=int(chapter_index),
        root_dir=Path(
            experiment.get("root_dir")
            or (Path(settings.DATA_DIR) / "research_runs")
        ),
    )


def _read_experiment_events(context: ExperimentContext) -> list[dict[str, Any]]:
    events_path = context.run_dir / "events" / "events.jsonl"
    if not events_path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        for line in events_path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(event, dict)
                and str(event.get("project_id")) == context.project_id
                and int(event.get("chapter_index", -1)) == context.chapter_index
            ):
                events.append(event)
    except OSError:
        return []
    return events


def _numeric_sum(events: list[dict[str, Any]], key: str) -> int:
    return sum(
        int(event[key])
        for event in events
        if isinstance(event.get(key), (int, float))
    )


def _completion_metrics(
    events: list[dict[str, Any]],
    *,
    wall_clock_seconds: float,
    segment_count: int,
    publication_source: str,
    reconciled_from_events: bool,
    wall_clock_is_lower_bound: bool,
) -> dict[str, Any]:
    attempts = [event for event in events if event.get("event") == "llm_attempt"]
    retries = [event for event in events if event.get("event") == "content_retry"]
    json_recoveries = [event for event in events if event.get("event") == "json_recovery"]
    finished = [event for event in events if event.get("event") == "chapter_finished"]
    memory_values = [
        int(event["memory_context_chars"])
        for event in attempts
        if isinstance(event.get("memory_context_chars"), (int, float))
    ]
    return {
        "status": "completed",
        "wall_clock_seconds": round(wall_clock_seconds, 3),
        "content_retry_count": len(retries),
        "rewrite_count": len(retries),
        "api_retry_count": sum(
            max(int(event.get("attempt") or 0), 0) for event in attempts
        ),
        "json_recovery_count": len(json_recoveries),
        "llm_call_count": sum(
            1 for event in attempts if int(event.get("attempt") or 0) == 0
        ),
        "llm_attempt_count": len(attempts),
        "input_tokens": _numeric_sum(attempts, "input_tokens"),
        "output_tokens": _numeric_sum(attempts, "output_tokens"),
        "memory_context_chars_min": min(memory_values) if memory_values else 0,
        "memory_context_chars_max": max(memory_values) if memory_values else 0,
        "memory_context_chars_avg": (
            round(sum(memory_values) / len(memory_values), 2)
            if memory_values
            else 0
        ),
        "publication_source": publication_source,
        "reconciled_from_events": reconciled_from_events,
        "wall_clock_is_lower_bound": wall_clock_is_lower_bound,
        "segment_count": segment_count,
        "prior_statuses": [
            str(event["status"])
            for event in finished
            if event.get("status")
        ],
    }


async def arecord_published_chapter(
    experiment: dict[str, Any] | None,
    *,
    project_id: Any,
    chapter_index: int,
    publication_source: str,
) -> bool:
    """record_published_chapter 的 async 版：整个读-改-写下放到单线程
    io executor，FIFO 保证幂等判断读到全部先前事件；事件循环零阻塞。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return record_published_chapter(
            experiment,
            project_id=project_id,
            chapter_index=chapter_index,
            publication_source=publication_source,
        )
    recorded = await _await_io_work(
        asyncio.get_running_loop().run_in_executor(
            _io_executor,
            lambda: record_published_chapter(
                experiment,
                project_id=project_id,
                chapter_index=chapter_index,
                publication_source=publication_source,
            ),
        )
    )
    # 超时放行时返回 False:"未(当场)记录"——后台写会延迟落盘,调用方按
    # best-effort 语义处理,发布流程不因实验记录卡住。
    return bool(recorded)


def record_published_chapter(
    experiment: dict[str, Any] | None,
    *,
    project_id: Any,
    chapter_index: int,
    publication_source: str,
) -> bool:
    """Close a published chapter's experiment record exactly once.

    The normal worker path can close the active context directly. A manual
    publish or a resumed Job has no original context, so this path reconciles
    all prior chapter events before appending one final ``chapter_finished``.
    """
    if not isinstance(experiment, dict):
        return False

    context = _experiment_context_from_payload(experiment, project_id, chapter_index)
    with _publication_record_lock:
        # 幂等判断要读到排队的写盘：async 上下文里 _write_event 是异步落盘的，
        # 不 flush 就可能读到旧内容，导致 chapter_finished 重复追加。
        _flush_pending_writes()
        events = _read_experiment_events(context)
        if any(
            event.get("event") == "chapter_finished"
            and event.get("status") == "completed"
            for event in events
        ):
            return False

        active = current()
        if active is not None and (
            active.project_id == context.project_id
            and active.chapter_index == context.chapter_index
            and active.run_id == context.run_id
        ):
            finished = [
                event for event in events if event.get("event") == "chapter_finished"
            ]
            if finished:
                wall_clock = sum(
                    float(event.get("wall_clock_seconds") or 0)
                    for event in finished
                    if isinstance(event.get("wall_clock_seconds"), (int, float))
                )
                payload = _completion_metrics(
                    events,
                    wall_clock_seconds=wall_clock
                    + (time.perf_counter() - active.started_at),
                    segment_count=len(finished) + 1,
                    publication_source=publication_source,
                    reconciled_from_events=True,
                    wall_clock_is_lower_bound=True,
                )
                _write_event(context, "chapter_finished", payload)
                active.chapter_finished_recorded = True
                return True
            record_chapter_finished(
                status="completed",
                rewrite_count=active.content_retry_count,
                extra={
                    "publication_source": publication_source,
                    "reconciled_from_events": False,
                    "wall_clock_is_lower_bound": False,
                },
            )
            return active.chapter_finished_recorded

        finished = [event for event in events if event.get("event") == "chapter_finished"]
        wall_clock = sum(
            float(event.get("wall_clock_seconds") or 0)
            for event in finished
            if isinstance(event.get("wall_clock_seconds"), (int, float))
        )
        payload = _completion_metrics(
            events,
            wall_clock_seconds=wall_clock,
            segment_count=len(finished),
            publication_source=publication_source,
            reconciled_from_events=True,
            wall_clock_is_lower_bound=True,
        )
        _write_event(context, "chapter_finished", payload)
        return True
