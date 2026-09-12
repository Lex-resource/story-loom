"""运行清单与快照:manifest.json、git 元数据、provider 快照。"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

from services.experiment_recorder._context import current
from services.experiment_recorder._io import (
    _await_io_work,
    _flush_pending_writes,
    _io_executor,
    _safe_json,
    _sha256,
    _submit_write,
    _write_json_file,
)


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
