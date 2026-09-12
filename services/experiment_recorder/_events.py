"""事件流:events.jsonl 的追加写与各 record_* 入口。"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from services.experiment_recorder._context import current
from services.experiment_recorder._io import (
    _append_event_line,
    _safe_json,
    _sha256,
    _submit_write,
    _write_json_file,
)


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
