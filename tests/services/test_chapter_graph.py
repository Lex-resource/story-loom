"""图模型的解析与校验测试。

golden trace 证明的是「默认图与原硬编码循环等价」。它证明不了**用户造出来的图**会
被正确拒掉 —— 而图一旦可从前端编辑，无守卫的环就是一条真实的、会烧掉无限 token 的
路径。本文件补的就是这一块。
"""
from __future__ import annotations

import pytest

from services.chapter_graph import (
    BUDGET_ATTEMPT,
    BUDGET_REWRITE,
    DEFAULT_BUDGETS,
    Edge,
    Step,
    ChapterGraph,
    default_graph,
    graph_for_config,
    parse_graph,
    validate_graph,
)
from services.pipeline_stages import (
    ROLE_CONTEXT_REFRESH,
    ROLE_DRAFT,
    ROLE_FINAL,
    ROLE_FORCE_REVISE,
    ROLE_OUTLINE,
    ROLE_POST_EDIT,
    ROLE_POSTPROCESS,
    ROLE_PRE_EDITOR,
    ROLE_PUBLISH,
    ROLE_REVIEW,
    ROLE_STYLE_REPAIR,
    VERDICT_BLOCKED,
    VERDICT_EMPTY,
    VERDICT_FAIL,
    VERDICT_REWRITE,
    VERDICT_SKIPPED,
)


def _minimal_steps(**overrides) -> dict[str, Step]:
    """一张最小的合法图：draft -> final -> publish -> post。"""
    steps = {
        "draft": Step("draft", ROLE_DRAFT, next=Edge("final_check")),
        "final_check": Step(
            "final_check",
            ROLE_FINAL,
            next=Edge("publish"),
            on={
                VERDICT_BLOCKED: Edge("@pause:validator"),
                VERDICT_FAIL: Edge(
                    "@retry_chapter", budget=BUDGET_ATTEMPT, on_exhausted="@pause:validator"
                ),
            },
        ),
        "publish": Step(
            "publish",
            ROLE_PUBLISH,
            next=Edge("post"),
            on={VERDICT_BLOCKED: Edge("@pause:validator")},
        ),
        "post": Step("post", ROLE_POSTPROCESS, next=Edge("@done")),
    }
    steps.update(overrides)
    return steps


def _graph(steps: dict[str, Step], entry: str = "draft") -> ChapterGraph:
    return ChapterGraph(entry=entry, steps=steps, budgets=dict(DEFAULT_BUDGETS))


# ---------------------------------------------------------------------------
# 默认图
# ---------------------------------------------------------------------------


def test_default_graph_is_valid_for_every_flag_combination():
    """开关的 8 种组合都必须产出合法图 —— 用户改开关不该造出坏拓扑。"""
    for has_editor in (True, False):
        for has_style_repair in (True, False):
            for pre_validate in (True, False):
                graph = default_graph(
                    has_editor=has_editor,
                    has_style_repair=has_style_repair,
                    validation_before_editor=pre_validate,
                )
                errors = validate_graph(graph)
                assert errors == [], (
                    f"has_editor={has_editor} has_style_repair={has_style_repair} "
                    f"pre_validate={pre_validate} 产出了非法图: {errors}"
                )


def test_default_graph_matches_production_long_form_topology():
    """长篇生产配置（前置校验开）的拓扑逐边钉住。"""
    graph = default_graph(
        has_editor=True, has_style_repair=True, validation_before_editor=True
    )
    assert graph.entry == "plan"
    assert list(graph.steps) == [
        "plan",
        "loop_head",
        "draft",
        "pre_check",
        "review",
        "force_fix",
        "post_check",
        "polish",
        "final_check",
        "publish",
        "post",
    ]
    # 入口边带 rewrite 预算：skip_write_edit 时整簇跳到 polish
    assert graph.step("plan").next.budget == BUDGET_REWRITE
    assert graph.step("plan").next.on_exhausted == "polish"
    # 入口边**不带** disabled_when：enable_editor_loop=False 只禁回边，初稿照写
    assert graph.step("plan").next.disabled_when is None
    # 重写回边带 disabled_when，用尽后走强制修正
    rewrite_edge = graph.step("review").on[VERDICT_REWRITE]
    assert rewrite_edge.goto == "loop_head"
    assert rewrite_edge.disabled_when == "enable_editor_loop"
    assert rewrite_edge.on_exhausted == "force_fix"
    # force_fix 只能从重写边到达，不在线性链上
    assert graph.step("pre_check").next.goto == "review"
    assert graph.step("review").next.goto == "post_check"


def test_default_graph_without_editor_drops_the_whole_cluster():
    graph = default_graph(has_editor=False, has_style_repair=False)
    assert not graph.has_role(ROLE_REVIEW)
    assert not graph.has_role(ROLE_FORCE_REVISE)
    assert not graph.has_role(ROLE_POST_EDIT)
    assert not graph.has_role(ROLE_STYLE_REPAIR)
    # 初稿仍然写，仍然终审、仍然发布
    assert graph.has_role(ROLE_DRAFT)
    assert graph.has_role(ROLE_FINAL)
    assert graph.has_role(ROLE_PUBLISH)
    assert graph.has_role(ROLE_POSTPROCESS)
    # 没有回边 -> 循环只跑一遍，入口边的预算用尽后直落终审
    assert graph.step("plan").next.on_exhausted == "final_check"


def test_default_graph_agrees_with_stage_plan_for_every_nodes_combination():
    """图与旧阶段模型必须对同一份 ``nodes`` 得出同样的结论。

    这是两个模型之间的接缝：``worker_support/pipeline_runtime`` 现在**从图派生**
    `has_editor` / `has_style_repair` / `validation_before_editor`，而 `stages`/`nodes`
    列仍然存在并驱动 `to_pipeline_order()`（章节状态推进）。两者若不一致，就会出现
    「图里没有编辑步骤，但 PipelineStep 顺序里还有 EDITING」这种自相矛盾的运行状态。
    """
    from services.pipeline_stages import StagePlan, stages_for_config

    combos = [
        ["planner", "writer", "editor", "validator", "extractor"],
        ["planner", "writer", "validator", "extractor"],
        ["writer", "validator"],
        ["planner", "writer", "editor", "validator"],
        [],  # 空 nodes 的既有兜底语义：视为全部节点都在
    ]
    for nodes in combos:
        for pre_validate in (True, False):
            plan = StagePlan.from_stages(
                stages_for_config(None, nodes, validation_before_editor=pre_validate)
            )
            graph = default_graph(
                has_editor=plan.has_editor,
                has_style_repair=plan.has_style_repair,
                validation_before_editor=plan.validation_before_editor,
            )
            context = f"nodes={nodes} pre_validate={pre_validate}"
            assert graph.has_role(ROLE_REVIEW) is plan.has_editor, context
            assert graph.has_role(ROLE_STYLE_REPAIR) is plan.has_style_repair, context
            assert graph.has_role(ROLE_PRE_EDITOR) is plan.validation_before_editor, context
            # postprocess 永远在场：``has_extractor`` 是那一步**内部**要不要跑提取，
            # 不是「有没有这一步」—— 发布本身在里面，缺了章节永远发不出去。
            assert graph.has_role(ROLE_POSTPROCESS), context
            assert validate_graph(graph) == [], context


def test_style_repair_requires_editor():
    """去 AI 腔跑在 Editor 上，没有 Editor 就不该出现。"""
    graph = default_graph(has_editor=False, has_style_repair=True)
    assert not graph.has_role(ROLE_STYLE_REPAIR)


def test_outline_is_always_present():
    """大纲步骤无条件在场 —— 缺了 Writer 会拿到空大纲。"""
    for has_editor in (True, False):
        assert default_graph(has_editor=has_editor).has_role(ROLE_OUTLINE)


# ---------------------------------------------------------------------------
# 环守卫：本文件存在的主要理由
# ---------------------------------------------------------------------------


def test_unguarded_back_edge_is_rejected():
    """没有预算的回边 = 无限循环 = 无限烧 token，必须在写入时拒掉。"""
    steps = _minimal_steps(
        draft=Step("draft", ROLE_DRAFT, next=Edge("review")),
        review=Step(
            "review",
            ROLE_REVIEW,
            next=Edge("final_check"),
            # 回边没有 budget
            on={VERDICT_REWRITE: Edge("draft")},
        ),
    )
    errors = validate_graph(_graph(steps))
    assert any("没有预算守卫的回边" in e for e in errors), errors


def test_guarded_back_edge_is_accepted():
    steps = _minimal_steps(
        draft=Step("draft", ROLE_DRAFT, next=Edge("review")),
        review=Step(
            "review",
            ROLE_REVIEW,
            next=Edge("final_check"),
            on={
                VERDICT_REWRITE: Edge(
                    "draft", budget=BUDGET_REWRITE, on_exhausted="final_check"
                )
            },
        ),
    )
    assert validate_graph(_graph(steps)) == []


def test_self_loop_without_budget_is_rejected():
    steps = _minimal_steps(
        polish=Step("polish", ROLE_STYLE_REPAIR, next=Edge("polish")),
    )
    steps["draft"] = Step("draft", ROLE_DRAFT, next=Edge("polish"))
    errors = validate_graph(_graph(steps))
    assert any("没有预算守卫的回边" in e for e in errors), errors


def test_long_cycle_without_budget_is_rejected():
    """三步环也要抓到，不能只查自环。"""
    steps = _minimal_steps(
        draft=Step("draft", ROLE_DRAFT, next=Edge("a")),
        a=Step("a", ROLE_STYLE_REPAIR, next=Edge("b")),
        b=Step("b", ROLE_PRE_EDITOR, next=Edge("c")),
        c=Step("c", ROLE_CONTEXT_REFRESH, next=Edge("a")),
    )
    errors = validate_graph(_graph(steps))
    assert any("没有预算守卫的回边" in e for e in errors), errors


# ---------------------------------------------------------------------------
# 其他结构错误
# ---------------------------------------------------------------------------


def test_dangling_target_is_rejected():
    steps = _minimal_steps(draft=Step("draft", ROLE_DRAFT, next=Edge("nowhere")))
    errors = validate_graph(_graph(steps))
    assert any("指向不存在的步骤 'nowhere'" in e for e in errors), errors


def test_missing_required_roles_are_rejected():
    """缺 draft / final / publish / postprocess 会产出空章节或永不发布的章节。"""
    steps = {"post": Step("post", ROLE_POSTPROCESS, next=Edge("@done"))}
    errors = validate_graph(ChapterGraph("post", steps, dict(DEFAULT_BUDGETS)))
    for role in (ROLE_DRAFT, ROLE_FINAL, ROLE_PUBLISH):
        assert any(f"缺少必需角色 {role!r}" in e for e in errors), (role, errors)


def test_unhandled_consequential_verdict_is_rejected():
    """Editor 判了 rewrite 却没有处理边，等于把不合格的稿子发出去。"""
    steps = _minimal_steps(
        draft=Step("draft", ROLE_DRAFT, next=Edge("review")),
        review=Step("review", ROLE_REVIEW, next=Edge("final_check")),
    )
    errors = validate_graph(_graph(steps))
    assert any("没有处理裁决 'rewrite'" in e for e in errors), errors


def test_force_revise_must_handle_skipped():
    """未启用强制修正时 force_revise 返回 skipped；没有处理边就会硬发布。"""
    steps = _minimal_steps(
        draft=Step("draft", ROLE_DRAFT, next=Edge("force_fix")),
        force_fix=Step("force_fix", ROLE_FORCE_REVISE, next=Edge("final_check")),
    )
    errors = validate_graph(_graph(steps))
    assert any("没有处理裁决 'skipped'" in e for e in errors), errors


def test_budget_edge_without_on_exhausted_is_rejected():
    steps = _minimal_steps(
        draft=Step("draft", ROLE_DRAFT, next=Edge("review")),
        review=Step(
            "review",
            ROLE_REVIEW,
            next=Edge("final_check"),
            on={VERDICT_REWRITE: Edge("draft", budget=BUDGET_REWRITE)},
        ),
    )
    errors = validate_graph(_graph(steps))
    assert any("没有 on_exhausted" in e for e in errors), errors


def test_unknown_budget_is_rejected():
    steps = _minimal_steps(
        draft=Step("draft", ROLE_DRAFT, next=Edge("review")),
        review=Step(
            "review",
            ROLE_REVIEW,
            next=Edge("final_check"),
            on={
                VERDICT_REWRITE: Edge(
                    "draft", budget="nonexistent", on_exhausted="final_check"
                )
            },
        ),
    )
    errors = validate_graph(_graph(steps))
    assert any("未定义的预算 'nonexistent'" in e for e in errors), errors


def test_invalid_pause_anchor_is_rejected():
    """暂停锚点必须是 5 个 agent 名之一 —— 存量 job.current_step 的取值域。"""
    steps = _minimal_steps(
        draft=Step("draft", ROLE_DRAFT, next=Edge("final_check")),
    )
    steps["final_check"] = Step(
        "final_check",
        ROLE_FINAL,
        next=Edge("publish"),
        on={
            VERDICT_BLOCKED: Edge("@pause:polish"),
            VERDICT_FAIL: Edge("publish"),
        },
    )
    errors = validate_graph(_graph(steps))
    assert any("不是合法的恢复锚点" in e for e in errors), errors


def test_bad_entry_is_rejected():
    errors = validate_graph(ChapterGraph("nope", _minimal_steps(), dict(DEFAULT_BUDGETS)))
    assert any("entry 指向不存在的步骤" in e for e in errors), errors


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------


def test_round_trip_preserves_default_graph():
    """序列化后再解析必须一模一样 —— 前端保存的就是这份 JSON。"""
    original = default_graph(validation_before_editor=True)
    reparsed = parse_graph(original.to_dict())
    assert reparsed is not None
    assert reparsed.to_dict() == original.to_dict()
    assert validate_graph(reparsed) == []


def test_edge_accepts_bare_string_target():
    graph = parse_graph(
        {
            "entry": "draft",
            "steps": [
                {"id": "draft", "role": ROLE_DRAFT, "next": "post"},
                {"id": "post", "role": ROLE_POSTPROCESS, "next": "@done"},
            ],
        }
    )
    assert graph is not None
    assert graph.step("draft").next.goto == "post"


def test_parse_drops_unknown_roles_and_verdicts():
    graph = parse_graph(
        {
            "entry": "draft",
            "steps": [
                {"id": "draft", "role": ROLE_DRAFT, "next": "post",
                 "on": {"teleport": "post", VERDICT_SKIPPED: "post"}},
                {"id": "bogus", "role": "does_not_exist", "next": "post"},
                {"id": "post", "role": ROLE_POSTPROCESS, "next": "@done"},
            ],
        }
    )
    assert graph is not None
    assert "bogus" not in graph.steps
    assert "teleport" not in graph.step("draft").on
    assert VERDICT_SKIPPED in graph.step("draft").on


def test_parse_supplies_default_budgets_when_missing():
    """带 budget 的边若查不到预算定义，回边就永不收敛 —— 所以默认预算必须补上。"""
    graph = parse_graph(
        {
            "entry": "draft",
            "steps": [{"id": "draft", "role": ROLE_DRAFT, "next": "@done"}],
        }
    )
    assert graph is not None
    assert BUDGET_REWRITE in graph.budgets
    assert BUDGET_ATTEMPT in graph.budgets


@pytest.mark.parametrize("raw", [None, {}, [], "graph", {"steps": []}, {"steps": "x"}])
def test_unparseable_input_returns_none(raw):
    assert parse_graph(raw) is None


def test_graph_for_config_falls_back_to_default():
    """一条坏数据不该让整个生成任务失败 —— 回落到默认图并继续。"""
    graph = graph_for_config({"steps": "garbage"}, has_editor=True, label="broken")
    assert graph.to_dict() == default_graph(has_editor=True).to_dict()


def test_graph_for_config_prefers_stored_graph():
    stored = default_graph(has_editor=False, has_style_repair=False).to_dict()
    graph = graph_for_config(stored, has_editor=True, has_style_repair=True)
    # 存的图是权威，不该被 has_editor=True 反悔
    assert not graph.has_role(ROLE_REVIEW)


def test_empty_outline_pause_edge_survives_round_trip():
    graph = parse_graph(default_graph().to_dict())
    assert graph is not None
    assert graph.step("plan").on[VERDICT_EMPTY].goto == "@pause:planner"
