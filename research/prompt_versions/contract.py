"""V44–V58 的章节契约扩展与 agent 投影。

生产冻结在 A28/V43(见 `docs/research/novel-memory-continuity/PRODUCTION.md`),
因此这些扩展全部在生产路径之外。每个 handler 的逻辑逐条对应原
`services/continuity_contract.py` 里被 `_prompt_version_at_least("V>43")` 守卫的块。
"""
from __future__ import annotations

from typing import Any

from services.context_compaction import compact_items, compact_text
from services.continuity_contract import (
    _as_list,
    _as_strings,
    _dedupe,
    _derive_character_turn,
    build_dramatic_turn_projection,
)
from services.version_surface import NO_OVERRIDE

from research.prompt_versions.registry import register
from research.prompt_versions.version_order import prompt_version_at_least


@register("derived_character_turn")
def derived_character_turn(
    character_turn: dict[str, str],
    outline: dict[str, Any],
    primary_action: dict[str, str],
):
    """V58 起用已给出的大纲证据补全 character_turn 缺项。"""
    if not prompt_version_at_least("V58"):
        return NO_OVERRIDE
    return _derive_character_turn(character_turn, outline, primary_action)


@register("contract_extensions")
def contract_extensions(
    contract: dict[str, Any],
    outline: dict[str, Any],
    handoff: dict[str, Any],
):
    """V46–V56 往契约上追加的字段与禁止项。

    返回一个只含**新增/覆盖**键的 dict；生产侧用 `contract.update()` 合并。
    低于 V46 时返回 NO_OVERRIDE，契约保持 V43 形态。
    """
    if not prompt_version_at_least("V46"):
        return NO_OVERRIDE

    extension: dict[str, Any] = {}
    forbidden = list(contract.get("forbidden_deviations", []))

    if prompt_version_at_least("V53"):
        prior_events = handoff.get("completed_event_ledger") or []
        prior_terminal = handoff.get("previous_terminal_state") or {}
        extension["previous_progress"] = {
            "completed_event_ledger": compact_items(
                prior_events, max_items=8, item_chars=360, keep="tail"
            ),
            "previous_terminal_state": prior_terminal,
        }
        forbidden = _dedupe(
            forbidden
            + [
                "不得把 completed_event_ledger 中已经完成的动作、响应或终态再次完整执行；必须产生非空 new_stage_delta。",
            ]
        )

    if prompt_version_at_least("V54"):
        forbidden = _dedupe(
            forbidden
            + [
                "同一 unique_action_ledger 操作在本章最多执行一次；后续只能观察其响应或作出新的选择。",
                "未知字段只能写成待判定、未返回或匹配结果为空，不得写成已确认属性。",
            ]
        )

    if prompt_version_at_least("V55"):
        forbidden = _dedupe(
            forbidden
            + [
                "本章只保留一个核心动作、一个可观察回应和一个角色决策/代价；不得用第二轮查询、确认或解释替代决策。",
            ]
        )

    if prompt_version_at_least("V56"):
        forbidden = _dedupe(
            forbidden
            + [
                "character_turn 只能使用角色卡、已发生状态或本章可见压力；不得凭空补写性格、背景、关系、能力或动机。",
                "primary_action 说明发生了什么，character_turn 说明角色为何在当前压力下这样选择；二者不得变成第二套重复动作。",
            ]
        )

    # V46 把角色目标、情绪弧和节拍带回契约。
    extension.update(
        {
            "character_goals": _as_list(outline.get("character_goals")),
            "emotional_arc": outline.get("emotional_arc") or "",
            "beats": _as_list(outline.get("beats")),
        }
    )

    if forbidden != contract.get("forbidden_deviations", []):
        extension["forbidden_deviations"] = forbidden
    return extension


@register("contract_prompt_extras")
def contract_prompt_extras(contract: dict[str, Any]):
    """V46–V56 在 `contract_prompt` 里额外投影的字段。

    返回要合并进紧凑契约的键；低于 V46 时返回 NO_OVERRIDE。
    """
    if not prompt_version_at_least("V46"):
        return NO_OVERRIDE

    extras: dict[str, Any] = {"dramatic_turn": build_dramatic_turn_projection(contract)}
    if prompt_version_at_least("V53"):
        extras["previous_progress"] = contract.get("previous_progress") or {}
    if prompt_version_at_least("V54"):
        extras["unique_action_ledger"] = compact_items(
            contract.get("unique_action_ledger"), max_items=6, item_chars=240, keep="head"
        )
    if prompt_version_at_least("V55"):
        extras["primary_action"] = contract.get("primary_action") or {}
    if prompt_version_at_least("V56"):
        extras["character_turn"] = contract.get("character_turn") or {}
    return extras


@register("outline_projection")
def outline_projection(outline: dict[str, Any], agent_type: str | None):
    """V44/V45 起把单章大纲按 agent 裁剪为执行视图。

    生产（V43）使用完整大纲，因此返回 NO_OVERRIDE。键列表逐字对应原
    `services/continuity_contract.prompt_outline_for_agent`。
    """
    if not prompt_version_at_least("V44"):
        return NO_OVERRIDE
    if agent_type not in {"editor", "validator", "extractor"}:
        return NO_OVERRIDE

    source = dict(outline)
    if prompt_version_at_least("V45"):
        execution_keys = {
            "editor": (
                "chapter_index", "title", "summary", "required_events", "end_state",
                "related_foreshadowing", "characters_involved", "beats", "new_stage_delta",
                "primary_action", "character_turn",
            ),
            "validator": (
                "chapter_index", "title", "required_events", "end_state",
                "forbidden_deviations", "related_foreshadowing", "new_stage_delta",
                "primary_action", "character_turn",
            ),
            "extractor": (
                "chapter_index", "title", "required_events", "end_state",
                "related_foreshadowing", "new_stage_delta", "primary_action", "character_turn",
            ),
        }[agent_type]
        return {key: source[key] for key in execution_keys if key in source}

    # V44：更宽的执行视图（对所有三个 agent 相同）
    execution_keys = (
        "chapter_index",
        "title",
        "summary",
        "key_events",
        "required_events",
        "state_changes",
        "end_state",
        "forbidden_deviations",
        "related_foreshadowing",
        "characters_involved",
        "character_goals",
        "beats",
        "new_stage_delta",
    )
    return {key: source[key] for key in execution_keys if key in source}


# ---------------------------------------------------------------------------
# V0–V42 整体路由
# ---------------------------------------------------------------------------
# 生产的 continuity_contract 已按 V43 内联，无法表达更低版本。低于 V43 时把整个
# 契约调用路由到 `contract_legacy`（重构前实现的冻结副本）。

_LEGACY_ENTRY_POINTS = (
    "legacy_build_chapter_contract",
    "legacy_sanitize_outline_for_contract",
    "legacy_contract_prompt",
    "legacy_prompt_outline_for_agent",
)


def _legacy_below_v43(func_name: str, *args, **kwargs):
    if prompt_version_at_least("V43"):
        return NO_OVERRIDE
    from research.prompt_versions import contract_legacy

    return getattr(contract_legacy, func_name)(*args, **kwargs)


@register("legacy_build_chapter_contract")
def legacy_build_chapter_contract(*args, **kwargs):
    return _legacy_below_v43("build_chapter_contract", *args, **kwargs)


@register("legacy_sanitize_outline_for_contract")
def legacy_sanitize_outline_for_contract(*args, **kwargs):
    return _legacy_below_v43("sanitize_outline_for_contract", *args, **kwargs)


@register("legacy_contract_prompt")
def legacy_contract_prompt(*args, **kwargs):
    return _legacy_below_v43("contract_prompt", *args, **kwargs)


@register("legacy_prompt_outline_for_agent")
def legacy_prompt_outline_for_agent(*args, **kwargs):
    return _legacy_below_v43("prompt_outline_for_agent", *args, **kwargs)
