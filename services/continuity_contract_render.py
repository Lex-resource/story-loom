"""章节契约的提示词渲染(自 services/continuity_contract.py 分离)。

契约构建(build_chapter_contract 等)与渲染(contract_prompt 等)变更节奏不同:
渲染函数输出被黄金快照逐字节锁定,单独成模块让渲染改动一眼可审。
原模块保持同名再导出,现有导入不需要改。
"""

from __future__ import annotations

import json
from typing import Any

from services.context_compaction import compact_items, compact_json, compact_text
from services.version_surface import NO_OVERRIDE, research_override


def contract_prompt(
    contract: dict[str, Any] | None,
    *,
    agent_type: str = "writer",
) -> str:
    # 低于 V43 的契约行为已冻结在 research/prompt_versions/contract_legacy.py。
    _legacy = research_override("legacy_contract_prompt", contract, agent_type=agent_type)
    if _legacy is not NO_OVERRIDE:
        return _legacy
    import json

    contract = contract or {}
    # V34 assigns each context block one owner. The handoff owns inherited
    # state and ledgers; the contract owns only current-chapter execution.
    compact_contract = {
        "required_events": compact_items(
            contract.get("required_events"), max_items=8, item_chars=420, keep="head"
        ),
        "state_changes": compact_items(
            contract.get("state_changes"), max_items=6, item_chars=420, keep="head"
        ),
        "foreshadowing_actions": compact_items(
            contract.get("foreshadowing_actions"), max_items=6, item_chars=420, keep="head"
        ),
        "end_state": compact_text(contract.get("end_state"), 700),
        "new_stage_delta": compact_items(
            contract.get("new_stage_delta"), max_items=5, item_chars=360, keep="head"
        ),
        "unique_action_ledger": [],
        "primary_action": {},
        "character_turn": {},
        "end_state_boundary": contract.get("end_state_boundary"),
        "uncertain_events": compact_items(
            contract.get("uncertain_events"), max_items=5, item_chars=360, keep="head"
        ),
        "unknown_boundary": compact_items(
            contract.get("unknown_boundary"), max_items=5, item_chars=360, keep="head"
        ),
        "forbidden_deviations": compact_items(
            contract.get("forbidden_deviations"), max_items=6, item_chars=360, keep="head"
        ),
        "execution_boundaries": [
            "上一章继承状态以交接包为准，本契约只列本章新增动作和可见后果。",
            "unknown/candidate/generated 只能写成观察、疑问或调查线索，不得写成确认事实。",
            "界面读取只改变可见信息；实体变化必须来自角色明确动作或保持未知。",
        ],
    }
    extras = research_override("contract_prompt_extras", contract)
    if extras is not NO_OVERRIDE:
        compact_contract.update(extras)
    if contract.get("recording_action_rules"):
        compact_contract["recording_action_rules"] = contract["recording_action_rules"]
    if contract.get("interpretation_boundary_rules"):
        compact_contract["interpretation_boundary_rules"] = contract["interpretation_boundary_rules"]
    return compact_json(compact_contract, 3000, label=f"chapter_contract_{agent_type}")

    contract = contract or {}
    compact_contract = {
        "required_events": compact_items(
            contract.get("required_events"),
            max_items=8,
            item_chars=420,
            keep="head",
        ),
        "continuity_from_previous": compact_items(
            contract.get("continuity_from_previous"),
            max_items=6,
            item_chars=420,
            keep="head",
        ),
        "state_changes": compact_items(
            contract.get("state_changes"),
            max_items=6,
            item_chars=420,
            keep="head",
        ),
        "foreshadowing_actions": compact_items(
            contract.get("foreshadowing_actions"),
            max_items=6,
            item_chars=420,
            keep="head",
        ),
        "end_state": compact_text(contract.get("end_state"), 700),
        "new_stage_delta": compact_items(
            contract.get("new_stage_delta"), max_items=5, item_chars=360, keep="head"
        ),
        "unknown_boundary": compact_items(
            contract.get("unknown_boundary"),
            max_items=5,
            item_chars=360,
            keep="head",
        ),
        "forbidden_deviations": compact_items(
            contract.get("forbidden_deviations"),
            max_items=6,
            item_chars=360,
            keep="head",
        ),
        "execution_boundaries": [
            "unknown/candidate/generated 只能作为观察、疑问或调查线索，不得写成确认事实。",
            "界面读取只改变可见信息；实体变化必须来自角色明确动作或保持未知。",
            "物品/证据账本以交接包为准；账本未登记的实体状态不得补全。",
        ],
        "backend_boundary": (
            "物品/证据账本、角色卡和权威等级以结构化交接包为准；"
            "本契约只规定本章要发生的叙事动作，不要求正文复述后台字段。"
        ),
    }
    extras = research_override("contract_prompt_extras", contract)
    if extras is not NO_OVERRIDE:
        compact_contract["previous_progress"] = extras.get("previous_progress") or {}
    return compact_json(compact_contract, 3600, label="chapter_contract")

    contract = contract or {}
    # The handoff is the single owner of the previous-ending evidence
    # ledgers. The chapter contract carries executable obligations only;
    # repeating the ledgers here was the largest V9 prompt multiplier.
    compact_contract = {
        "required_events": compact_items(
            contract.get("required_events"),
            max_items=12,
            item_chars=500,
            keep="head",
        ),
        "continuity_from_previous": compact_items(
            contract.get("continuity_from_previous"),
            max_items=8,
            item_chars=450,
            keep="head",
        ),
        "state_changes": compact_items(
            contract.get("state_changes"),
            max_items=8,
            item_chars=450,
            keep="head",
        ),
        "foreshadowing_actions": compact_items(
            contract.get("foreshadowing_actions"),
            max_items=8,
            item_chars=450,
            keep="head",
        ),
        "end_state": compact_text(contract.get("end_state"), 900),
        "new_stage_delta": compact_items(
            contract.get("new_stage_delta"), max_items=5, item_chars=360, keep="head"
        ),
        "uncertain_events": compact_items(
            contract.get("uncertain_events"),
            max_items=8,
            item_chars=450,
            keep="head",
        ),
        "forbidden_deviations": compact_items(
            contract.get("forbidden_deviations"),
            max_items=12,
            item_chars=450,
            keep="head",
        ),
        "boundary_reference": "物品/证据账本、未知边界和权威来源以同章结构化交接包为唯一来源。",
    }
    compact_contract["state_boundary_rules"] = compact_items(
        contract.get("state_boundary_rules"),
        max_items=5,
        item_chars=700,
        keep="head",
    )
    compact_contract["claim_boundary_rules"] = compact_items(
        contract.get("claim_boundary_rules"),
        max_items=4,
        item_chars=700,
        keep="head",
    )
    compact_contract["evidence_surface_rules"] = compact_items(
        contract.get("evidence_surface_rules"),
        max_items=3,
        item_chars=700,
        keep="head",
    )
    compact_contract["evidence_surface_claims"] = compact_items(
        contract.get("evidence_surface_claims"),
        max_items=4,
        item_chars=500,
        keep="head",
    )
    compact_contract["item_state_rules"] = compact_items(
        contract.get("item_state_rules"),
        max_items=2,
        item_chars=900,
        keep="head",
    )
    return compact_json(compact_contract, 5000, label="chapter_contract")

    return json.dumps(
        contract or {},
        ensure_ascii=False,
        indent=2,
    )


def prompt_outline_for_agent(
    outline: dict[str, Any] | None,
    *,
    agent_type: str | None = None,
) -> dict[str, Any]:
    """Remove persisted contracts and, for V35 Writer, audit-only fields."""
    # 低于 V43 的契约行为已冻结在 research/prompt_versions/contract_legacy.py。
    _legacy = research_override("legacy_prompt_outline_for_agent", outline, agent_type=agent_type)
    if _legacy is not NO_OVERRIDE:
        return _legacy
    source = dict(outline) if isinstance(outline, dict) else {}
    source.pop("continuity_contract", None)
    # V44/V45 起按 agent 把大纲裁剪为执行视图。生产（V43）用完整大纲。
    projected = research_override("outline_projection", source, agent_type)
    if projected is not NO_OVERRIDE:
        return projected
    if agent_type == "writer":
        writer_keys = (
            "chapter_index",
            "title",
            "summary",
            "key_events",
            "emotional_arc",
            "narrative_stage",
            "characters_involved",
            "character_goals",
            "beats",
            "new_stage_delta",
            "primary_action",
            "character_turn",
        )
        return {key: source[key] for key in writer_keys if key in source}
    return source

