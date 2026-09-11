"""V10 及更早的交接包渲染，以及 V19/V20/V44/V45 的上下文预算表。

生产冻结在 A28/V43：交接包用 V30 投影，预算用 V30/V31 表。这里保存其余取值，
使这些历史版本的实验仍可复现。
"""
from __future__ import annotations

import json
from typing import Any

from services.context_compaction import (
    V10_CONTEXT_BUDGETS,
    V19_CONTEXT_BUDGETS,
    V20_CONTEXT_BUDGETS,
    V30_CONTEXT_BUDGETS,
    V31_CONTEXT_BUDGETS,
    V44_CONTEXT_BUDGETS,
    V45_CONTEXT_BUDGETS,
    compact_items,
)
from services.version_surface import NO_OVERRIDE

from research.prompt_versions.registry import register
from research.prompt_versions.version_order import prompt_version_at_least


@register("context_budget")
def context_budget(agent_type: str):
    """按版本选预算表。V30/V31（= 生产冻结点）时让路给生产。"""
    if prompt_version_at_least("V45"):
        table = V45_CONTEXT_BUDGETS
    elif prompt_version_at_least("V44"):
        table = V44_CONTEXT_BUDGETS
    elif prompt_version_at_least("V30"):
        return NO_OVERRIDE  # V30/V31 就是生产表
    elif prompt_version_at_least("V20"):
        table = V20_CONTEXT_BUDGETS
    elif prompt_version_at_least("V19"):
        table = V19_CONTEXT_BUDGETS
    else:
        table = V10_CONTEXT_BUDGETS
    return table.get(agent_type, table["writer"])


def _baseline_compact_prompt(handoff, max_chars: int) -> str:
    """V10 以下的基线渲染：直接裁剪各字段，不做角色投影。"""
    payload = {
        "previous_chapter": handoff.previous_chapter,
        "previous_title": handoff.previous_title,
        "exact_ending": handoff.exact_ending[-1800:],
        "end_scene": handoff.end_scene,
        "characters_present": handoff.characters_present,
        "state_changes": handoff.state_changes[-8:],
        "completed_event_ledger": handoff.completed_event_ledger[-8:],
        "previous_terminal_state": handoff.previous_terminal_state,
        "open_questions": handoff.open_questions[-8:],
        "foreshadowing": handoff.foreshadowing[-8:],
        "next_hook": handoff.next_hook,
        "item_state_ledger": [
            {k: v for k, v in item.items() if k not in {"transitions", "source_ref"}}
            for item in handoff.item_state_ledger
        ],
        "evidence_state_ledger": handoff.evidence_state_ledger,
        "evidence_boundaries": handoff.evidence_boundaries,
        "unknown_boundary": handoff.unknown_boundary,
    }

    def render(value: dict[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)

    rendered = render(payload)
    if len(rendered) <= max_chars:
        return rendered
    payload["exact_ending"] = handoff.exact_ending[-900:]
    payload["state_changes"] = handoff.state_changes[-4:]
    payload["open_questions"] = handoff.open_questions[-4:]
    payload["foreshadowing"] = handoff.foreshadowing[-4:]
    payload["item_state_ledger"] = payload["item_state_ledger"][:24]
    rendered = render(payload)
    if len(rendered) <= max_chars:
        return rendered
    compact_payload = {
        "previous_chapter": handoff.previous_chapter,
        "previous_title": handoff.previous_title,
        "exact_ending": handoff.exact_ending[-600:],
        "end_scene": handoff.end_scene,
        "characters_present": handoff.characters_present[:12],
        "inherited_state": compact_items(handoff.inherited_state, max_items=20, item_chars=650),
        "next_hook": handoff.next_hook,
        "item_state_ledger": payload["item_state_ledger"],
        "evidence_state_ledger": handoff.evidence_state_ledger,
        "evidence_boundaries": handoff.evidence_boundaries,
        "unknown_boundary": handoff.unknown_boundary,
    }
    return render(compact_payload)


@register("handoff_compact_prompt")
def handoff_compact_prompt(handoff, max_chars: int):
    """V30 以下的交接包渲染。V30+（含生产冻结点）让路给生产。"""
    if prompt_version_at_least("V30"):
        return NO_OVERRIDE
    if prompt_version_at_least("V10"):
        return handoff._to_v10_compact_prompt(max_chars)
    return _baseline_compact_prompt(handoff, max_chars)


@register("dramatic_turn_projection")
def dramatic_turn_projection(contract_data: dict):
    """V46 起在 Writer 执行简报里注入戏剧转折投影。生产（V43）不注入。"""
    if not prompt_version_at_least("V46"):
        return NO_OVERRIDE
    from services.continuity_contract import build_dramatic_turn_projection

    return build_dramatic_turn_projection(contract_data)
