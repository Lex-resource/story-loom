"""实验记录的单线程写盘 executor 与文件写助手。

一次调用可能落盘几十 MB 的 prompt/response 快照,在事件循环里同步写会把
worker 卡住数秒;单线程 executor 保持写入顺序,读-改-写路径读前 flush。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger("services.experiment_recorder")


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
