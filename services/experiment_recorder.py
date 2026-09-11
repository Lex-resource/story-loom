"""Local, opt-in artifacts for reproducible generation experiments.

The recorder deliberately stays outside the business database. A generation
job opts in through ``job.params.experiment``; ordinary production runs incur
no file writes. Prompt and response snapshots are local research artifacts
and never contain provider secrets.

本模块只负责**运行记录**。版本/变体分派曾经也在这里，现已移到
``research/prompt_versions/version_order.py``——生产冻结在 A28/V43，分派判据
只对研究运行有意义。生产代码不应再需要"当前是哪个版本"这个问题的答案。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import hashlib
import json
import logging
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import settings

logger = logging.getLogger(__name__)


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
_publication_record_lock = threading.Lock()

# 实验记录的文件写盘在 async 上下文里走这个单线程 executor：一次调用可能落盘
# 几十 MB 的 prompt/response 快照，在事件循环里同步写会把 worker 卡住数秒。
# 单线程保持写入顺序；读-改-写路径读文件前、以及实验上下文结束时（deactivate）
# 都会 flush 屏障，保证既有同步语义（读完才算写完、上下文结束数据必落盘）。
# 入口分两族：同步版 deactivate/record_published_chapter（测试与研究脚本用，
# 原地等待屏障）；async 版 adeactivate/arecord_published_chapter（生产调用链用，
# 把"等 flush"下放 executor 线程，事件循环只 await 不冻结）。
# 同步调用者（测试、研究脚本）不经过事件循环，_submit_write 直接原地写。
_io_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="experiment-recorder"
)
_pending_writes: set[concurrent.futures.Future] = set()
_pending_writes_lock = threading.Lock()


def _submit_write(fn, *args) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        fn(*args)  # 同步上下文：保持原有的同步写语义
        return
    future = _io_executor.submit(fn, *args)
    with _pending_writes_lock:
        _pending_writes.add(future)

    def _on_done(fut: concurrent.futures.Future) -> None:
        with _pending_writes_lock:
            _pending_writes.discard(fut)
        exc = fut.exception()
        if exc is not None:
            logger.error("experiment_recorder_write_failed", exc_info=exc)

    future.add_done_callback(_on_done)


def _flush_pending_writes() -> None:
    """同步等待排队的写盘完成（读-改-写路径读文件前调用）。"""
    with _pending_writes_lock:
        pending = tuple(_pending_writes)
    outstanding = [f for f in pending if not f.done()]
    if outstanding:
        concurrent.futures.wait(outstanding)


# io executor 上的等待统一带上界:实验记录是可降级的科研数据,一次挂死的磁盘
# 写把单线程 executor 占住时,等待方最多挂这个上限就放行(发布照常、收尾照常),
# 后台写不因超时被丢弃。30s 远大于本地磁盘几十 MB 快照的正常写盘耗时。
_IO_AWAIT_TIMEOUT_SECONDS = 30.0


async def _await_io_work(work: Any) -> Any:
    """等待 io executor 上的写盘工作:超时放行 + shield 防取消丢弃。

    - wait_for:超时后调用方继续走(记 warning),不再无限排队;
    - shield:双重取消风暴(rewrite 的 cancel × register 换任务)打断等待时,
      排队中/进行中的写不被取消,延迟到 executor 空闲后照常落盘
      (executor 线程非 daemon,进程退出时 atexit 也会 join 补落)。
    """
    try:
        return await asyncio.wait_for(asyncio.shield(work), timeout=_IO_AWAIT_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning(
            "experiment_recorder_io_stalled timeout_seconds=%s "
            "impact=等待方放行,本次实验事件延迟落盘",
            _IO_AWAIT_TIMEOUT_SECONDS,
        )
        return None


def _write_json_file(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_event_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _safe_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _safe_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_json(v) for v in value]
    return str(value)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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




def _write_event(context: ExperimentContext, event: str, payload: dict[str, Any]) -> None:
    event_dir = context.run_dir / "events"
    event_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": time.time(),
        "event": event,
        "run_id": context.run_id,
        "prompt_version": context.prompt_version,
        "variant": context.variant,
        "project_id": context.project_id,
        "chapter_index": context.chapter_index,
        **_safe_json(payload),
    }
    _submit_write(
        _append_event_line,
        event_dir / "events.jsonl",
        json.dumps(record, ensure_ascii=False),
    )


def record_event(event: str, payload: dict[str, Any]) -> None:
    context = current()
    if context is not None:
        _write_event(context, event, payload)


async def arecord_run_manifest(payload: dict[str, Any]) -> None:
    """record_run_manifest 的 async 版：整个函数下放到单线程 io executor。

    单线程 FIFO 保证读-改-写看到全部先前写盘（内部 flush 屏障在 executor
    线程上自然为空转），事件循环零阻塞。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        record_run_manifest(payload)
        return
    await _await_io_work(
        asyncio.get_running_loop().run_in_executor(
            _io_executor, lambda: record_run_manifest(payload)
        )
    )


def record_run_manifest(payload: dict[str, Any]) -> None:
    context = current()
    if context is None:
        return
    context.run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = context.run_dir / "manifest.json"
    _flush_pending_writes()
    manifest = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
    manifest.update(
        {
            "run_id": context.run_id,
            "prompt_version": context.prompt_version,
            "variant": context.variant,
            "project_id": context.project_id,
            **_safe_json(payload),
        }
    )
    _submit_write(_write_json_file, manifest_path, manifest)


def code_snapshot() -> dict[str, Any]:
    """Return reproducible local Git metadata without capturing source files."""
    repo_dir = Path(__file__).resolve().parents[1]
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True, stderr=subprocess.DEVNULL,
        ).strip()
        diff = subprocess.check_output(
            ["git", "diff", "--binary"], cwd=repo_dir, stderr=subprocess.DEVNULL,
        )
        return {
            "git_sha": sha,
            "worktree_dirty": bool(diff),
            "worktree_diff_sha256": _sha256(diff.decode("utf-8", errors="replace")),
        }
    except (OSError, subprocess.CalledProcessError):
        return {"git_sha": None, "worktree_dirty": None, "worktree_diff_sha256": None}


def record_prompt_template(
    *,
    name: str,
    category: str,
    system_prompt: str,
    user_prompt_template: str,
) -> None:
    context = current()
    if context is None:
        return
    template_dir = context.run_dir / "templates" / context.prompt_version / category
    template_dir.mkdir(parents=True, exist_ok=True)
    template_path = template_dir / f"{name}.json"
    if template_path.exists():
        return
    _submit_write(
        _write_json_file,
        template_path,
        {
            "name": name,
            "category": category,
            "prompt_version": context.prompt_version,
            "system_prompt": system_prompt,
            "user_prompt_template": user_prompt_template,
        },
    )


def record_llm_attempt(
    *,
    agent_name: str,
    prompt_name: str,
    system_prompt: str,
    user_prompt: str,
    provider_name: str | None,
    model: str,
    base_url: str,
    attempt: int,
    is_fallback: bool,
    response: str | None = None,
    error: str | None = None,
    duration_ms: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    memory_context_chars: int | None = None,
    memory_context_breakdown: dict[str, int] | None = None,
) -> None:
    context = current()
    if context is None:
        return
    context.llm_attempt_count += 1
    context.llm_call_count += 1 if attempt == 0 else 0
    if attempt > 0:
        context.api_retry_count += 1
    if isinstance(input_tokens, (int, float)):
        context.input_tokens += int(input_tokens)
    if isinstance(output_tokens, (int, float)):
        context.output_tokens += int(output_tokens)
    if isinstance(memory_context_chars, (int, float)):
        context.memory_context_values.append(int(memory_context_chars))
    call_id = uuid.uuid4().hex
    prompt_dir = context.run_dir / "prompts" / f"chapter-{context.chapter_index:04d}"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "call_id": call_id,
        "agent_name": agent_name,
        "prompt_name": prompt_name,
        "attempt": attempt,
        "is_fallback": is_fallback,
        "provider_name": provider_name,
        "model": model,
        "base_url": base_url,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "system_prompt_sha256": _sha256(system_prompt),
        "user_prompt_sha256": _sha256(user_prompt),
        "response": response,
        "error": error,
        "duration_ms": duration_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "memory_context_chars": memory_context_chars,
        "memory_context_breakdown": memory_context_breakdown,
    }
    _submit_write(_write_json_file, prompt_dir / f"{call_id}.json", snapshot)
    _write_event(
        context,
        "llm_attempt",
        {
            "call_id": call_id,
            "agent_name": agent_name,
            "prompt_name": prompt_name,
            "attempt": attempt,
            "is_fallback": is_fallback,
            "provider_name": provider_name,
            "model": model,
            "input_chars": len(system_prompt) + len(user_prompt),
            "output_chars": len(response or ""),
            "duration_ms": duration_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "memory_context_chars": memory_context_chars,
            "memory_context_breakdown": memory_context_breakdown,
            "error": error,
        },
    )


def record_json_recovery(error: str) -> None:
    context = current()
    if context is None:
        return
    context.json_recovery_count += 1
    _write_event(context, "json_recovery", {"error": error[:1000]})


def record_content_retry(reason: str, instructions: str = "") -> None:
    context = current()
    if context is None:
        return
    context.content_retry_count += 1
    _write_event(
        context,
        "content_retry",
        {"reason": reason[:2000], "instructions": instructions[:4000]},
    )


def record_chapter_finished(*, status: str, rewrite_count: int, extra: dict[str, Any] | None = None) -> None:
    context = current()
    if context is None or context.chapter_finished_recorded:
        return
    payload = {
        "status": status,
        "wall_clock_seconds": round(time.perf_counter() - context.started_at, 3),
        "content_retry_count": context.content_retry_count,
        "rewrite_count": rewrite_count,
        "api_retry_count": context.api_retry_count,
        "json_recovery_count": context.json_recovery_count,
        "llm_call_count": context.llm_call_count,
        "llm_attempt_count": context.llm_attempt_count,
        "input_tokens": context.input_tokens,
        "output_tokens": context.output_tokens,
        "memory_context_chars_min": min(context.memory_context_values, default=0),
        "memory_context_chars_max": max(context.memory_context_values, default=0),
        "memory_context_chars_avg": (
            round(sum(context.memory_context_values) / len(context.memory_context_values), 2)
            if context.memory_context_values
            else 0
        ),
    }
    if extra:
        payload.update(extra)
    _write_event(context, "chapter_finished", payload)
    context.chapter_finished_recorded = True


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


def provider_snapshot(provider: dict[str, Any] | None) -> dict[str, Any]:
    provider = provider or {}
    embedding_model = provider.get("embedding_model")
    return {
        "id": provider.get("id"),
        "name": provider.get("name"),
        "model": provider.get("model"),
        "base_url": provider.get("base_url"),
        "embedding_model": embedding_model,
        "embedding_backend": "openai_provider" if embedding_model else "chroma_local",
        "has_api_key": bool(provider.get("api_key")),
    }
