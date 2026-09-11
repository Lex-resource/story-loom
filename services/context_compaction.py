"""Deterministic prompt-context budgets for continuity experiments.

V10 treats context reduction as a data-shaping step, not an LLM summary. The
full records remain in PostgreSQL and local experiment snapshots; only the
prompt representation is compacted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PromptContextBudget:
    """Per-agent limits for prompt-only context blocks."""

    memory_chars: int
    handoff_chars: int
    contract_chars: int
    character_chars: int
    manifest_chars: int


V10_CONTEXT_BUDGETS: dict[str, PromptContextBudget] = {
    "planner": PromptContextBudget(6000, 5200, 0, 0, 6500),
    "writer": PromptContextBudget(5000, 5200, 4800, 9000, 0),
    "editor": PromptContextBudget(4500, 4500, 4200, 7000, 0),
    "validator": PromptContextBudget(5500, 5200, 5000, 7000, 0),
    "extractor": PromptContextBudget(4000, 4000, 3200, 6500, 0),
}

# V19 keeps the full handoff, memory and character records in storage and in
# experiment snapshots, but reduces repeated prompt material after V18 showed
# late-chapter contexts exceeding 100k characters.
V19_CONTEXT_BUDGETS: dict[str, PromptContextBudget] = {
    "planner": PromptContextBudget(4500, 4000, 0, 0, 5200),
    "writer": PromptContextBudget(3600, 4000, 3600, 6500, 0),
    "editor": PromptContextBudget(3200, 3500, 3400, 5200, 0),
    "validator": PromptContextBudget(4200, 4000, 4000, 5200, 0),
    "extractor": PromptContextBudget(3000, 3200, 2800, 5000, 0),
}

# V20 keeps V19's deterministic state hygiene but restores the proven V10/V12
# prompt budgets so state rules do not starve the Writer of continuity context.
V20_CONTEXT_BUDGETS = V10_CONTEXT_BUDGETS

# V30 keeps V29's generation prompts unchanged and gives the deterministic
# handoff its own smaller projection. Full handoffs remain available in the
# database and experiment snapshots for audit and replay.
V30_CONTEXT_BUDGETS: dict[str, PromptContextBudget] = {
    "planner": PromptContextBudget(4500, 3000, 0, 0, 5200),
    "writer": PromptContextBudget(5000, 3000, 4800, 9000, 0),
    "editor": PromptContextBudget(4500, 3000, 4200, 7000, 0),
    "validator": PromptContextBudget(5500, 3200, 5000, 7000, 0),
    "extractor": PromptContextBudget(4000, 2800, 3200, 6500, 0),
}

# V31 changes the execution guidance only. Keep the V30 prompt budget so the
# experiment isolates ordering/repair guidance from another context-size
# change.
V31_CONTEXT_BUDGETS = V30_CONTEXT_BUDGETS

# V44 trims the generation-facing projection after A29 showed that the
# provider rejects long structured user inputs even when the system prompt is
# accepted. Full records remain in PostgreSQL and experiment snapshots.
V44_CONTEXT_BUDGETS: dict[str, PromptContextBudget] = {
    "planner": PromptContextBudget(3000, 2200, 0, 0, 4200),
    "writer": PromptContextBudget(2800, 2200, 2400, 5200, 0),
    "editor": PromptContextBudget(2400, 1800, 2200, 4200, 0),
    "validator": PromptContextBudget(2800, 2200, 2600, 4200, 0),
    "extractor": PromptContextBudget(2200, 1800, 2200, 4200, 0),
}

# V45 keeps V44's provider-safe input surface and trims review-only context a
# little further. The full records remain available in PostgreSQL and local
# experiment snapshots; this only changes the generation projection.
V45_CONTEXT_BUDGETS: dict[str, PromptContextBudget] = {
    "planner": PromptContextBudget(3000, 2200, 0, 0, 4200),
    "writer": PromptContextBudget(2800, 2200, 2400, 5200, 0),
    "editor": PromptContextBudget(2200, 1800, 2000, 4000, 0),
    "validator": PromptContextBudget(2400, 2000, 2200, 3600, 0),
    "extractor": PromptContextBudget(2000, 1600, 1900, 3600, 0),
}


def context_budget_for(agent_type: str) -> PromptContextBudget:
    """该 agent 的 prompt 上下文预算。

    生产冻结在 A28/V43，使用 V30/V31 预算表（V31 是 V30 的别名）。V44/V45 收紧了
    预算，V19/V20/V10 是更早的取值——都由研究覆盖层提供。
    """
    from services.version_surface import NO_OVERRIDE, research_override

    override = research_override("context_budget", agent_type)
    if override is not NO_OVERRIDE:
        return override

    return V30_CONTEXT_BUDGETS.get(agent_type, V30_CONTEXT_BUDGETS["writer"])


def compact_text(value: Any, max_chars: int, *, tail_chars: int | None = None) -> str:
    """Bound text while retaining both its beginning and latest evidence."""
    text = str(value or "")
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    marker = "\n...[V10 context compacted; source retained]...\n"
    if max_chars <= len(marker) + 1:
        return text[:max_chars]
    available = max_chars - len(marker)
    if tail_chars is None:
        tail_chars = max(1, available // 3)
    tail_chars = min(tail_chars, available - 1)
    head_chars = available - tail_chars
    return text[:head_chars] + marker + text[-tail_chars:]


def compact_items(
    items: list[Any] | tuple[Any, ...] | None,
    *,
    max_items: int,
    item_chars: int,
    keep: str = "tail",
) -> list[Any]:
    """Keep a bounded list and compact string values without model calls."""
    values = list(items or [])
    if max_items <= 0:
        return []
    if len(values) > max_items:
        values = values[-max_items:] if keep == "tail" else values[:max_items]
    result: list[Any] = []
    for item in values:
        if isinstance(item, str):
            result.append(compact_text(item, item_chars))
        elif isinstance(item, dict):
            result.append(
                {
                    key: compact_text(value, item_chars)
                    if isinstance(value, str)
                    else value
                    for key, value in item.items()
                }
            )
        else:
            result.append(item)
    return result


def compact_json(value: Any, max_chars: int, *, label: str = "context") -> str:
    """Render bounded valid JSON, with a string fallback at the hard limit."""
    if max_chars <= 0:
        return ""

    def normalize(item: Any, depth: int = 0) -> Any:
        if isinstance(item, str):
            return compact_text(item, max(80, max_chars // 8))
        if isinstance(item, dict):
            return {str(key): normalize(child, depth + 1) for key, child in item.items()}
        if isinstance(item, list):
            max_items = 24 if depth < 2 else 12
            selected = item[-max_items:] if len(item) > max_items else item
            return [normalize(child, depth + 1) for child in selected]
        return item

    rendered = json.dumps(normalize(value), ensure_ascii=False, separators=(",", ":"), default=str)
    if len(rendered) <= max_chars:
        return rendered

    # Drop provenance and repeated descriptive fields before reducing the
    # executable state. These fields are still available in the source record.
    if isinstance(value, dict):
        reduced = dict(normalize(value))
        for key in (
            "sources",
            "transitions",
            "evidence_boundaries",
            "unknown_boundary",
            "open_questions",
            "foreshadowing",
            "state_changes",
        ):
            reduced.pop(key, None)
        rendered = json.dumps(reduced, ensure_ascii=False, separators=(",", ":"), default=str)
        if len(rendered) <= max_chars:
            return rendered

    # Keep the output valid JSON even for pathological records. The embedded
    # text is explicitly labelled so an agent cannot mistake it for a full
    # structured object.
    for payload_chars in range(max_chars, 0, -max(1, max_chars // 32)):
        result = json.dumps(
            {"_truncated": True, "label": label, "source_preview": compact_text(rendered, payload_chars)},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(result) <= max_chars:
            return result
    return json.dumps({"_truncated": True, "label": label}, ensure_ascii=False, separators=(",", ":"))[:max_chars]


def memory_context_breakdown(context: Any) -> dict[str, int]:
    """Return the compact memory fields actually carried by an agent context."""
    fields = (
        "novel_memory_context",
        "narrative_index_context",
        "chapter_handoff_context",
        "chapter_contract_context",
        "writer_execution_brief_context",
        "character_manifest_context",
        "character_card_context",
    )
    return {
        field: len(str(getattr(context, field, "") or ""))
        for field in fields
        if getattr(context, field, "")
    }
