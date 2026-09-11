"""工作流格式轴的分离约束。

`tests/test_v43_production_surface_snapshot.py` 逐字节锁定**长篇**表面。本文件锁定的是
另一半:短篇拿到的确实是短篇表面,而长篇一步都没有走进新代码路径。

没有这层约束,短篇很容易再次被长篇材料淹没 —— 这正是本次重构要修的历史问题:
`generation_hints` 等表面函数原先只按 `agent_type` 分派,于是 A28/V43 的长篇连续性栈
无条件进入短篇,实测占短篇五个 agent system prompt 的 73%。
"""
from __future__ import annotations

import json

import pytest

from agents.prompt_hints import (
    agent_context_policy,
    chapter_contract_output_requirements,
    editor_policy,
    generation_hints,
    previous_ending_for_prompt,
    validator_extra_requirements,
    validator_trailing_hint,
)
from agents.writing_schemas import EditorShortFormResponse
from services.chapter_continuity import ChapterHandoff, writer_execution_brief
from services.continuity_contract import sanitize_outline_for_contract
from services.quality_metrics import dimensions_for, quality_summary
from services.workflow_surface import (
    NO_WORKFLOW_OVERRIDE,
    STRATEGY_FROZEN_V43,
    STRATEGY_SHORT_FORM,
    registered_surfaces,
    strategy_for,
    workflow_override,
)

LONG = "long_webnovel"
SHORT = "zhihu_short"
AGENT_TYPES = ("planner", "writer", "editor", "validator", "extractor")

# 长篇专用材料的特征串。这些**绝不能**出现在短篇表面里。
# 每一条都对应一个实测过的具体冲突,不是泛泛的关键词。
LONG_FORM_MARKERS = (
    "item_state_ledger",   # 物品状态账本 —— 短篇没有账本
    "笔记本",              # V36 记录物品禁令的白名单/黑名单
    "便签",
    "回执",                # V37 设备回执语汇
    "requires_matching_ledger",
    "required_changes",    # 短篇 planner schema 里不存在的字段
    "unknown_boundary",
)


def _short_outline() -> dict:
    return {
        "chapter_index": 2,
        "title": "第2章 婚宴上的红包",
        "summary": "我在婚宴上收到前男友的红包，里面是十年前的欠条。",
        "key_events": ["前男友当众递上红包", "我打开发现是欠条", "母亲抢过欠条撕碎"],
        "emotional_arc": "尴尬 -> 愤怒 -> 悲凉",
        "related_foreshadowing": ["十年前那笔学费"],
        "characters_involved": ["我", "前男友", "母亲"],
        "character_goals": [
            {
                "character_name": "我",
                "goal": "撑住场面",
                "conflict": "母亲当众发作",
                "state_change": "认清母亲态度",
            }
        ],
        "narrative_stage": "冲突升级",
        "beats": ["敬酒到第三桌前男友出现", "红包被打开", "母亲撕碎欠条全场安静"],
    }


def _handoff() -> ChapterHandoff:
    return ChapterHandoff(
        previous_chapter=1,
        previous_title="相亲",
        exact_ending="我答应了这场婚事。",
    )


# ---------------------------------------------------------------------------
# 长篇让路:一步都不进新路径
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("novel_format", [LONG, None, "", "some_future_custom_format"])
def test_frozen_strategy_yields_on_every_registered_surface(novel_format):
    """长篇、无格式、未知格式一律让路,由调用点执行内联的 A28/V43 逻辑。

    未知格式也让路是刻意的保守设计:新增一个工作流记录时,在为它注册表面之前,
    它拿到的是久经验证的长篇行为,而不是半套东西。
    """
    assert strategy_for(novel_format) == STRATEGY_FROZEN_V43
    for _strategy, surface in registered_surfaces():
        assert workflow_override(surface, novel_format, "writer") is NO_WORKFLOW_OVERRIDE


@pytest.mark.parametrize("agent_type", AGENT_TYPES)
def test_long_form_surfaces_unchanged_by_new_parameter(agent_type):
    """不传 novel_format == 显式传长篇。这是黄金快照不动的前提。"""
    assert generation_hints(agent_type) == generation_hints(agent_type, LONG)


def test_long_form_non_hint_surfaces_unchanged_by_new_parameter():
    assert chapter_contract_output_requirements() == chapter_contract_output_requirements(LONG)
    assert editor_policy() == editor_policy(LONG)
    assert validator_extra_requirements() == validator_extra_requirements(LONG)
    assert validator_trailing_hint() == validator_trailing_hint(LONG)
    assert editor_policy()["long_form_quality_contract"] is True
    assert editor_policy()["research_response_schema"] is True


# ---------------------------------------------------------------------------
# 短篇接管
# ---------------------------------------------------------------------------


def test_short_form_uses_short_strategy():
    assert strategy_for(SHORT) == STRATEGY_SHORT_FORM


@pytest.mark.parametrize("agent_type", AGENT_TYPES)
def test_short_hints_replace_long_stack_and_stay_compact(agent_type):
    short = generation_hints(agent_type, SHORT)
    long_form = generation_hints(agent_type, LONG)
    assert short and short != long_form
    # 短篇栈必须显著短于长篇栈 —— 否则又会压过短篇作者自己的模板。
    assert len(short) < len(long_form) / 2


@pytest.mark.parametrize("agent_type", AGENT_TYPES)
def test_short_hints_carry_no_long_form_markers(agent_type):
    short = generation_hints(agent_type, SHORT)
    for marker in LONG_FORM_MARKERS:
        assert marker not in short, f"{agent_type} 短篇栈残留长篇材料: {marker}"


def test_short_contract_requirements_match_short_planner_schema():
    """短篇契约要求只能提短篇 planner 真实产出的字段。

    这条是那次「planner 契约字段空 -> 执行简报落回长篇兜底 -> Writer 收 70% 样板」
    劣化链的源头:长篇版本要求八个短篇 schema 里不存在的字段,而模板同时命令
    「严格匹配以下结构」。
    """
    short = chapter_contract_output_requirements(SHORT)
    for field in ("emotional_arc", "beats", "character_goals", "key_events"):
        assert field in short
    for field in ("required_events", "uncertain_events", "unknown_boundary", "continuity_contract"):
        assert field not in short


def test_short_editor_policy_drops_long_form_dimensions():
    policy = editor_policy(SHORT)
    assert policy["long_form_quality_contract"] is False
    assert policy["research_response_schema"] is False
    strategy = policy["review_strategy"]
    # 短篇换成逐节可评的两维，并显式禁止跨章两维。
    # 长篇维度名允许出现在“禁止输出”句里，但不能被列进要求输出的字段清单。
    assert "hook_strength" in strategy and "emotional_landing" in strategy
    assert "禁止输出 chapter_continuity 或 foreshadowing_payoff" in strategy
    required_line = strategy.split("每个字段都是")[0]
    assert "chapter_continuity" not in required_line
    assert "foreshadowing_payoff" not in required_line


def test_short_validator_drops_item_ledger_hint():
    assert validator_trailing_hint(SHORT) == ""
    assert validator_trailing_hint(LONG) != ""


# ---------------------------------------------------------------------------
# 执行简报
# ---------------------------------------------------------------------------


def test_long_brief_keeps_all_four_boilerplate_blocks():
    handoff = _handoff()
    _outline, contract = sanitize_outline_for_contract(_short_outline(), handoff.to_dict())
    payload = json.loads(writer_execution_brief(handoff, contract, novel_format=LONG))
    assert "do_not_turn_into_a_report" in payload
    assert "interpretation_boundary" in payload
    assert "recording_boundary" in payload["chapter_execution"]
    assert "end_state_boundary" in payload["chapter_execution"]


def test_short_brief_drops_boilerplate_and_carries_section_content():
    handoff = _handoff()
    outline, contract = sanitize_outline_for_contract(_short_outline(), handoff.to_dict())
    rendered = writer_execution_brief(
        handoff, contract, novel_format=SHORT, outline=outline
    )
    payload = json.loads(rendered)
    execution = payload["chapter_execution"]

    assert "do_not_turn_into_a_report" not in payload
    assert "interpretation_boundary" not in payload
    assert "recording_boundary" not in execution
    assert "end_state_boundary" not in execution

    # 换成本节真正的执行要点。这些字段只在大纲上,契约不带它们。
    assert execution["emotional_arc"] == "尴尬 -> 愤怒 -> 悲凉"
    assert execution["beats"]
    assert execution["character_goals"]
    assert execution["short_form_rules"]

    for marker in ("笔记本", "便签", "requires_matching_ledger"):
        assert marker not in rendered


def test_short_brief_is_materially_smaller_than_long():
    handoff = _handoff()
    outline, contract = sanitize_outline_for_contract(_short_outline(), handoff.to_dict())
    long_len = len(writer_execution_brief(handoff, contract, novel_format=LONG))
    short_len = len(
        writer_execution_brief(handoff, contract, novel_format=SHORT, outline=outline)
    )
    assert short_len < long_len


# ---------------------------------------------------------------------------
# 质量闭环
# ---------------------------------------------------------------------------


def test_quality_dimensions_are_workflow_specific():
    long_dims = dimensions_for(LONG)
    short_dims = dimensions_for(SHORT)
    assert dimensions_for(None) == long_dims
    assert "chapter_continuity" in long_dims and "foreshadowing_payoff" in long_dims
    assert "hook_strength" in short_dims and "emotional_landing" in short_dims
    # 两者对称:五维手艺 + 两维工作流专属。
    assert len(long_dims) == len(short_dims) == 7


def test_short_editor_schema_preserves_short_dimensions():
    """pydantic 会丢弃未声明的键 —— 没有短篇 schema,模型即使正确产出这两维也会被静默丢掉。"""
    response = EditorShortFormResponse(
        evaluations={
            "plot_progression": {"score": 8, "reason": "x"},
            "character_portrayal": {"score": 8, "reason": "x"},
            "world_consistency": {"score": 8, "reason": "x"},
            "writing_quality": {"score": 8, "reason": "x"},
            "logical_coherence": {"score": 8, "reason": "x"},
            "hook_strength": {"score": 9, "reason": "开场即冲突"},
            "emotional_landing": {"score": 8, "reason": "落在母亲撕欠条"},
        },
        edited_content="正文",
    )
    evaluations = response.evaluations.model_dump()
    summary = quality_summary(evaluations, SHORT)
    assert summary["complete"] is True
    assert summary["dimension_count"] == 7


def test_short_quality_summary_was_previously_incomplete_under_long_dimensions():
    """同一份短篇评分按长篇维度衡量必然 incomplete —— 这就是短篇过去没有可比指标的原因。"""
    evaluations = {
        dimension: {"score": 8, "reason": "x"} for dimension in dimensions_for(SHORT)
    }
    assert quality_summary(evaluations, SHORT)["complete"] is True
    assert quality_summary(evaluations, LONG)["complete"] is False


REVIEWER_AGENTS = ("editor", "validator", "extractor")


def test_short_form_suppresses_handoff_and_contract_for_reviewers():
    """短篇的 Editor/Validator/Extractor 不收交接包与章节契约的原始副本。

    两份 payload 是跨章物品/证据账本（`item_states`、`completed_event_ledger`、
    `state_changes`、`end_state_boundary`），短篇 planner 全都不产出 —— 投影出来是空壳
    配长篇语汇，而 Editor 与 Validator 正是决定要不要重写的两个角色。
    """
    for agent_type in REVIEWER_AGENTS:
        policy = agent_context_policy(agent_type, SHORT)
        assert policy["suppress_handoff_and_contract"] is True, agent_type


def test_long_form_reviewers_still_receive_handoff_and_contract():
    """长篇（及一切继承 frozen_v43 的自定义工作流）字节不变。"""
    for agent_type in REVIEWER_AGENTS:
        assert agent_context_policy(agent_type, LONG)["suppress_handoff_and_contract"] is False
        assert agent_context_policy(agent_type, "some-custom-workflow")[
            "suppress_handoff_and_contract"
        ] is False


def test_planner_keeps_contract_even_on_short_form():
    """Planner 走的是「产出本章契约」那条路，与三个消费方语义不同，本轮不抑制。"""
    assert agent_context_policy("planner", SHORT)["suppress_handoff_and_contract"] is False


def test_suppressed_handoff_falls_back_to_full_previous_ending():
    """抑制交接包不等于丢掉上一节结尾 —— `previous_ending_for_prompt` 会回落到完整结尾。

    交接包非空时它刻意返回空串（避免与 handoff.exact_ending 重复粘贴）；清空之后短篇
    Editor/Validator 拿到的是直白的上一节结尾，这正是短篇需要的形状。
    """
    ending = "她把欠条撕成两半。"
    assert previous_ending_for_prompt(ending, "handoff payload") == ""
    assert previous_ending_for_prompt(ending, "") == ending

