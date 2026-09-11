"""图解释器测试。

golden trace 走的是**默认图**。这里补的是解释器本身的语义，特别是预算解析 ——
`disabled_when` 挂在边上而不是预算上这件事，一旦搞反，`enable_editor_loop=False`
的工作流会连初稿都不写。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.chapter_graph import (
    MAX_STEPS_PER_CHAPTER,
    Budget,
    ChapterGraph,
    ChapterGraphError,
    Edge,
    Step,
    default_graph,
)
from services.pipeline_stages import (
    ROLE_DRAFT,
    ROLE_POSTPROCESS,
    ROLE_STYLE_REPAIR,
    VERDICT_OK,
    VERDICT_REWRITE,
)
from worker_support import chapter_graph_runner as gr
from worker_support import chapter_steps as steps
from worker_support.chapter_run_state import ChapterRunState


def _state(**overrides) -> ChapterRunState:
    base = dict(
        db=SimpleNamespace(),
        job=SimpleNamespace(id="job-1", current_step="planner"),
        novel=SimpleNamespace(id="n1", novel_format="long_webnovel"),
        chapter_index=3,
        attempt=1,
        runtime=SimpleNamespace(enable_editor_loop=True, enable_force_correction=True),
        events=SimpleNamespace(),
        project_id="p1",
    )
    loop = {k: overrides.pop(k) for k in list(overrides) if k in {"rewrite_count", "max_rewrites", "attempt"}}
    base.update(overrides)
    state = ChapterRunState(**base)
    for key, value in loop.items():
        setattr(state, key, value)
    return state


REWRITE_BUDGET = Budget(counter="rewrite_count", limit_from="max_rewrites")
ATTEMPT_BUDGET = Budget(counter="attempt", limit=3)
BUDGETS = {"rewrite": REWRITE_BUDGET, "attempt": ATTEMPT_BUDGET}


def _graph(steps_map, entry, budgets=None) -> ChapterGraph:
    return ChapterGraph(entry=entry, steps=steps_map, budgets=budgets or dict(BUDGETS))


# ---------------------------------------------------------------------------
# 预算解析
# ---------------------------------------------------------------------------


def test_budget_not_exhausted_takes_goto():
    state = _state(rewrite_count=0, max_rewrites=2)
    edge = Edge("loop_head", budget="rewrite", on_exhausted="polish")
    assert gr.resolve_edge(edge, _graph({}, "x"), state) == "loop_head"


def test_budget_exhausted_takes_on_exhausted():
    state = _state(rewrite_count=2, max_rewrites=2)
    edge = Edge("loop_head", budget="rewrite", on_exhausted="polish")
    assert gr.resolve_edge(edge, _graph({}, "x"), state) == "polish"


def test_disabled_when_false_flag_exhausts_immediately():
    """enable_editor_loop=False -> 回边立刻视为用尽，哪怕预算还有余额。"""
    state = _state(rewrite_count=0, max_rewrites=5)
    state.runtime.enable_editor_loop = False
    edge = Edge(
        "loop_head",
        budget="rewrite",
        disabled_when="enable_editor_loop",
        on_exhausted="force_fix",
    )
    assert gr.resolve_edge(edge, _graph({}, "x"), state) == "force_fix"


def test_entry_edge_without_disabled_when_ignores_the_flag():
    """入口边不带 disabled_when：关掉重写循环仍然要写初稿。

    这是 disabled_when 挂边而不挂预算的全部理由。搞反了 enable_editor_loop=False
    的工作流会跳过整个 write-edit 簇，一个字都不写。
    """
    state = _state(rewrite_count=0, max_rewrites=2)
    state.runtime.enable_editor_loop = False
    entry_edge = Edge("loop_head", budget="rewrite", on_exhausted="polish")
    assert gr.resolve_edge(entry_edge, _graph({}, "x"), state) == "loop_head"


def test_attempt_budget_uses_fixed_limit():
    state = _state(attempt=3)
    edge = Edge("@retry_chapter", budget="attempt", on_exhausted="publish")
    assert gr.resolve_edge(edge, _graph({}, "x"), state) == "publish"
    assert gr.resolve_edge(edge, _graph({}, "x"), _state(attempt=2)) == "@retry_chapter"


def test_unknown_budget_treated_as_not_exhausted():
    """校验器会拦住未定义的预算；运行时保守放行，别把正常链路提前掐断。"""
    state = _state(rewrite_count=99, max_rewrites=1)
    edge = Edge("loop_head", budget="ghost", on_exhausted="polish")
    assert gr.resolve_edge(edge, _graph({}, "x", budgets={}), state) == "loop_head"


def test_plain_edge_ignores_budgets():
    state = _state(rewrite_count=99, max_rewrites=1)
    assert gr.resolve_edge(Edge("polish"), _graph({}, "x"), state) == "polish"


# ---------------------------------------------------------------------------
# 执行与终止
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_adapters(monkeypatch):
    """把角色适配器换成只记录调用的桩，返回可编程的裁决序列。"""
    calls: list[str] = []
    verdicts: dict[str, list[str]] = {}

    def program(role: str, *seq: str):
        verdicts[role] = list(seq)

    async def fake_run(state, node=None, _role=None):
        calls.append(_role)
        seq = verdicts.get(_role)
        return seq.pop(0) if seq else VERDICT_OK

    def fake_adapter_for(role: str):
        async def run(state, node=None, _role=role):
            return await fake_run(state, node, _role=_role)

        return SimpleNamespace(role=role, run=run)

    monkeypatch.setattr(gr.steps, "adapter_for", fake_adapter_for)
    return SimpleNamespace(calls=calls, program=program)


def test_runs_default_graph_to_completion(stub_adapters):
    import asyncio

    graph = default_graph(validation_before_editor=True)
    outcome = asyncio.run(gr.run_chapter_graph(_state(rewrite_count=0, max_rewrites=2), graph))
    assert outcome.kind == gr.OUTCOME_DONE
    assert stub_adapters.calls == [
        "outline",
        "context_refresh",
        "draft",
        "pre_editor",
        "review",
        "post_edit",
        "style_repair",
        "final",
        "publish",
        "postprocess",
    ]


def test_pause_outcome_carries_anchor(stub_adapters):
    import asyncio

    stub_adapters.program("outline", "empty")
    graph = default_graph()
    outcome = asyncio.run(gr.run_chapter_graph(_state(rewrite_count=0, max_rewrites=2), graph))
    assert outcome.kind == gr.OUTCOME_PAUSE
    assert outcome.anchor == "planner"
    # empty 之后立刻停，一步都不许多跑
    assert stub_adapters.calls == ["outline"]


def test_retry_outcome_when_final_fails(stub_adapters):
    import asyncio

    stub_adapters.program("final", "fail")
    graph = default_graph()
    outcome = asyncio.run(gr.run_chapter_graph(_state(rewrite_count=0, max_rewrites=2), graph))
    assert outcome.kind == gr.OUTCOME_RETRY
    assert "publish" not in stub_adapters.calls


def test_retry_budget_exhausted_pauses_before_publish(stub_adapters):
    """attempt 用尽后暂停，不能把终审失败稿送进 publish。"""
    import asyncio

    stub_adapters.program("final", "fail")
    state = _state(rewrite_count=0, max_rewrites=2, attempt=3)
    outcome = asyncio.run(gr.run_chapter_graph(state, default_graph()))
    assert outcome.kind == gr.OUTCOME_PAUSE
    assert outcome.anchor == "validator"
    assert "publish" not in stub_adapters.calls
    assert "postprocess" not in stub_adapters.calls


def test_step_cap_raises_rather_than_burning_tokens(stub_adapters):
    """带预算但不收敛的环由步数上限兜住 —— 每一步都是一次真实的 LLM 调用。"""
    import asyncio

    # 预算引用了一个永远不会增长的计数器：静态校验放行，运行时不收敛。
    loop = {
        "draft": Step("draft", ROLE_DRAFT, next=Edge("polish")),
        "polish": Step(
            "polish",
            ROLE_STYLE_REPAIR,
            next=Edge("draft", budget="frozen", on_exhausted="post"),
        ),
        "post": Step("post", ROLE_POSTPROCESS, next=Edge("@done")),
    }
    graph = ChapterGraph(
        entry="draft",
        steps=loop,
        budgets={"frozen": Budget(counter="rewrite_count", limit=999)},
    )
    with pytest.raises(ChapterGraphError, match="步数超过上限"):
        asyncio.run(gr.run_chapter_graph(_state(rewrite_count=0), graph))
    assert len(stub_adapters.calls) == MAX_STEPS_PER_CHAPTER


def test_dangling_target_ends_run_instead_of_crashing(stub_adapters):
    """悬空目标由校验器拦；真漏到运行时也不能让 worker 崩掉一整章。"""
    import asyncio

    graph = ChapterGraph(
        entry="draft",
        steps={"draft": Step("draft", ROLE_DRAFT, next=Edge("gone"))},
        budgets=dict(BUDGETS),
    )
    outcome = asyncio.run(gr.run_chapter_graph(_state(), graph))
    assert outcome.kind == gr.OUTCOME_DONE


def test_unhandled_verdict_falls_through_to_next(stub_adapters):
    import asyncio

    stub_adapters.program("style_repair", VERDICT_REWRITE)
    graph = ChapterGraph(
        entry="polish",
        steps={
            "polish": Step("polish", ROLE_STYLE_REPAIR, next=Edge("post")),
            "post": Step("post", ROLE_POSTPROCESS, next=Edge("@done")),
        },
        budgets=dict(BUDGETS),
    )
    outcome = asyncio.run(gr.run_chapter_graph(_state(), graph))
    assert outcome.kind == gr.OUTCOME_DONE
    assert stub_adapters.calls == ["style_repair", "postprocess"]


def test_on_step_start_hook_sees_every_step(stub_adapters):
    """钩子每步都触发，并拿到解析后的节点。"""
    import asyncio

    seen: list[str] = []
    nodes: list[str | None] = []

    async def hook(step, node):
        seen.append(step.id)
        nodes.append(node.id if node is not None else None)

    graph = default_graph()
    asyncio.run(
        gr.run_chapter_graph(
            _state(rewrite_count=0, max_rewrites=2), graph, on_step_start=hook
        )
    )
    # 钩子收步骤 id，桩收角色名 —— 数量必须一致，且钩子在适配器之前触发。
    assert len(seen) == len(stub_adapters.calls)
    assert seen == ["plan", "loop_head", "draft", "review", "post_check", "polish",
                    "final_check", "publish", "post"]
    # 步骤没指定节点时解析到该角色的内置节点，而不是 None
    assert nodes[0] == "planner.outline"
    assert nodes[2] == "writer.draft"
    assert None not in nodes


def test_real_adapters_cover_every_graph_role():
    """图模型登记的角色必须都有适配器 —— 否则那个角色一进图就 KeyError。"""
    from services.chapter_graph import GRAPH_ROLES

    missing = sorted(GRAPH_ROLES - set(steps.registered_roles()))
    assert missing == [], f"缺少适配器的角色: {missing}"
