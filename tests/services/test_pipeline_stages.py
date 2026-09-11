"""阶段模型与 PipelineStep 顺序派生。

补上 golden trace 覆盖不到的那一半：`tests/worker_support/test_generation_trace.py`
把 `set_job_step` stub 掉了，所以它能验证**阶段调用顺序**，却验证不了
`validate_pipeline_transition` 依赖的**章节状态推进顺序**。

这个缺口曾经真实咬人：阶段列表里 `validator/pre_editor` 排在 `editor/review` 之前，
若按首次出现顺序派生 PipelineStep，就会得到「validating 早于 editing」，
于是正常的 editor→validator 流转被判成回退并抛 PipelineStateError —— 而 golden trace
全绿。这里把规范顺序钉住。
"""
from __future__ import annotations

import pytest

from agents.constants import (
    AGENT_EDITOR,
    AGENT_EXTRACTOR,
    AGENT_PLANNER,
    AGENT_VALIDATOR,
    AGENT_WRITER,
)
from services.pipeline_config_service import PipelineConfig
from services.pipeline_stages import (
    ROLE_DRAFT,
    ROLE_FINAL,
    ROLE_POST_EDIT,
    ROLE_PRE_EDITOR,
    ROLE_REVIEW,
    ROLE_STYLE_REPAIR,
    Stage,
    StagePlan,
    default_stages,
    normalize_stages,
    parse_stages,
    stages_for_config,
)
from services.pipeline_transitions import PipelineStateError, validate_pipeline_transition
from services.pipeline_types import PipelineStep

CANONICAL_ORDER = [
    PipelineStep.OUTLINE,
    PipelineStep.WRITING,
    PipelineStep.EDITING,
    PipelineStep.VALIDATING,
    PipelineStep.EXTRACTING,
    PipelineStep.PUBLISHED,
]

FIVE_NODES = ["planner", "writer", "editor", "validator", "extractor"]


def _config(stages_raw, nodes=None, validation_before_editor=False):
    plan = StagePlan.from_stages(
        stages_for_config(
            stages_raw,
            nodes if nodes is not None else FIVE_NODES,
            validation_before_editor=validation_before_editor,
        )
    )
    return PipelineConfig(
        nodes=nodes if nodes is not None else FIVE_NODES,
        enable_editor_loop=True,
        max_rewrite=2,
        enable_force_correction=True,
        validation_before_editor=validation_before_editor,
        stage_plan=plan,
    )


# ---------------------------------------------------------------------------
# PipelineStep 顺序必须是规范顺序，与阶段编排无关
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("validation_before_editor", [False, True])
def test_pipeline_order_is_canonical_regardless_of_stage_order(validation_before_editor):
    """pre_editor 在 review 之前，也不能让 validating 排到 editing 前面。"""
    config = _config(None, validation_before_editor=validation_before_editor)
    assert config.to_pipeline_order() == CANONICAL_ORDER


def test_editor_to_validator_transition_stays_forward():
    """这是上面那条顺序真正保护的东西：正常流转不得被判成回退。"""
    order = _config(None, validation_before_editor=True).to_pipeline_order()
    # 不抛异常即通过
    validate_pipeline_transition(
        PipelineStep.EDITING, PipelineStep.VALIDATING, pipeline_order=order
    )
    with pytest.raises(PipelineStateError):
        validate_pipeline_transition(
            PipelineStep.VALIDATING, PipelineStep.EDITING, pipeline_order=order
        )


def test_dropping_editor_shrinks_the_order():
    config = _config(None, nodes=["planner", "writer", "validator", "extractor"])
    order = config.to_pipeline_order()
    assert PipelineStep.EDITING not in order
    assert order == [
        PipelineStep.OUTLINE,
        PipelineStep.WRITING,
        PipelineStep.VALIDATING,
        PipelineStep.EXTRACTING,
        PipelineStep.PUBLISHED,
    ]


# ---------------------------------------------------------------------------
# 从 nodes 派生的默认阶段：必须复现今天的行为
# ---------------------------------------------------------------------------


def test_default_stages_reproduce_full_pipeline():
    stages = default_stages(FIVE_NODES, validation_before_editor=True)
    assert [s.key for s in stages] == [
        (AGENT_PLANNER, "outline"),
        (AGENT_WRITER, ROLE_DRAFT),
        (AGENT_VALIDATOR, ROLE_PRE_EDITOR),
        (AGENT_EDITOR, ROLE_REVIEW),
        (AGENT_VALIDATOR, ROLE_POST_EDIT),
        (AGENT_EDITOR, ROLE_STYLE_REPAIR),
        (AGENT_VALIDATOR, ROLE_FINAL),
        (AGENT_EXTRACTOR, "postprocess"),
    ]


def test_default_stages_omit_pre_editor_when_flag_off():
    stages = default_stages(FIVE_NODES, validation_before_editor=False)
    assert (AGENT_VALIDATOR, ROLE_PRE_EDITOR) not in {s.key for s in stages}


def test_empty_nodes_means_everything_on():
    """既有兜底语义：配置缺失时所有阶段都开，不能变成什么都不跑。"""
    plan = StagePlan.from_stages(default_stages(None))
    assert plan.has_planner and plan.has_editor and plan.has_extractor
    assert plan.has_style_repair


# ---------------------------------------------------------------------------
# StagePlan 投影出的执行开关
# ---------------------------------------------------------------------------


def test_plan_projects_execution_switches():
    plan = StagePlan.from_stages(default_stages(FIVE_NODES, validation_before_editor=True))
    assert plan.has_editor is True
    assert plan.has_extractor is True
    assert plan.has_style_repair is True
    assert plan.validation_before_editor is True


def test_style_repair_requires_editor_review():
    """只留 style_repair 而没有 review，在主循环里没有入口 —— 必须判为不可用。"""
    plan = StagePlan.from_stages(
        normalize_stages([
            Stage(AGENT_WRITER, ROLE_DRAFT),
            Stage(AGENT_EDITOR, ROLE_STYLE_REPAIR),
            Stage(AGENT_VALIDATOR, ROLE_FINAL),
        ])
    )
    assert plan.has_editor is False
    assert plan.has_style_repair is False


# ---------------------------------------------------------------------------
# 解析与校验：工作流记录可由用户编辑，坏数据不能拖垮生成
# ---------------------------------------------------------------------------


def test_parse_drops_unknown_and_malformed_entries():
    parsed = parse_stages([
        {"agent": "writer", "role": "draft"},
        {"agent": "writer", "role": "not_a_role"},   # 未登记组合
        {"agent": "bogus", "role": "draft"},          # 未知 agent
        "not a dict",
        {"agent": "writer", "role": "draft"},         # 重复
        {"agent": "validator", "role": "final"},
    ])
    assert [s.key for s in parsed] == [
        (AGENT_WRITER, ROLE_DRAFT),
        (AGENT_VALIDATOR, ROLE_FINAL),
    ]


def test_required_stages_are_restored_when_missing():
    """writer/draft 与 validator/final 缺失会直接产出空章节，必须补回。"""
    plan = StagePlan.from_stages(normalize_stages(parse_stages([
        {"agent": "planner", "role": "outline"},
    ])))
    keys = {s.key for s in plan.stages}
    assert (AGENT_WRITER, ROLE_DRAFT) in keys
    assert (AGENT_VALIDATOR, ROLE_FINAL) in keys


def test_empty_or_invalid_stages_fall_back_to_nodes():
    """stages 列为空（未迁移的库、或用户清空）时回落到 nodes 派生。"""
    for raw in (None, [], "garbage", [{"agent": "bogus", "role": "x"}]):
        stages = stages_for_config(raw, FIVE_NODES, validation_before_editor=False)
        plan = StagePlan.from_stages(stages)
        assert plan.has_editor and plan.has_extractor, raw


# ---------------------------------------------------------------------------
# 真正的数据化：改 stages 就能改执行
# ---------------------------------------------------------------------------


def test_custom_stage_list_drives_execution():
    """一个去掉 editor 与 extractor 的自定义工作流。"""
    plan = StagePlan.from_stages(stages_for_config(
        [
            {"agent": "planner", "role": "outline"},
            {"agent": "writer", "role": "draft"},
            {"agent": "validator", "role": "final"},
        ],
        FIVE_NODES,
    ))
    assert plan.has_planner is True
    assert plan.has_editor is False
    assert plan.has_style_repair is False
    assert plan.has_extractor is False
    assert plan.validation_before_editor is False


def test_stage_list_can_add_pre_editor_validation_without_touching_columns():
    """原先 validation_before_editor 是独立布尔列；现在阶段列表就能表达。"""
    plan = StagePlan.from_stages(stages_for_config(
        [
            {"agent": "writer", "role": "draft"},
            {"agent": "validator", "role": "pre_editor"},
            {"agent": "editor", "role": "review"},
            {"agent": "validator", "role": "final"},
        ],
        FIVE_NODES,
        validation_before_editor=False,   # 列是 False，阶段列表说要
    ))
    assert plan.validation_before_editor is True
