"""图解释器：按 `services/chapter_graph` 的图执行一章。

取代 `_process_single_chapter` 里那段硬编码的 `while` + `if/elif` 编排。解释器本身
不知道任何具体阶段 —— 它只做四件事：查适配器、跑、按裁决选边、按目标跳转。
于是「跑哪些阶段、什么顺序、什么条件回边」真正由数据决定。

**暂停与整章重跑不在这里执行**，只作为 `GraphOutcome` 返回：暂停要动 `StateMachine`、
重跑要递归调用 `process_single_chapter`，那两件事都属于 `generate_job_runner`。
解释器保持纯粹（只碰黑板与适配器），也让它在测试里可以单独跑。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from services import prompt_scope
from services.chapter_graph import (
    MAX_STEPS_PER_CHAPTER,
    PAUSE_PREFIX,
    TARGET_DONE,
    TARGET_RETRY,
    ChapterGraph,
    ChapterGraphError,
    Edge,
)
from services.prompt_scope import PromptScope
from services.workflow_nodes import prompt_overrides_for, resolve_node
from worker_support import chapter_steps as steps
from worker_support.chapter_run_state import ChapterRunState

logger = logging.getLogger(__name__)

OUTCOME_DONE = "done"
OUTCOME_PAUSE = "pause"
OUTCOME_RETRY = "retry"


@dataclass(frozen=True)
class GraphOutcome:
    """一次图执行的结果。

    Attributes:
        kind: `done` / `pause` / `retry`。
        anchor: `pause` 时 `job.current_step` 要置成的锚点。
        steps_run: 实际执行的步数，用于诊断与日志。
    """

    kind: str
    anchor: str | None = None
    steps_run: int = 0


def _budget_exhausted(edge: Edge, graph: ChapterGraph, state: ChapterRunState) -> bool:
    """这条边的预算是否已用尽。

    `disabled_when` 指向 runtime 上的布尔开关，**为假**时视为立即用尽 —— 这是
    `enable_editor_loop=False` 直接禁掉重写回边的机制。注意它挂在边上而不是预算上：
    同一个 rewrite 预算，进入 write-edit 簇的那条边不看这个开关，否则该开关一关连初稿
    都不会写。
    """
    if edge.disabled_when and not getattr(state.runtime, edge.disabled_when, False):
        return True

    budget = graph.budgets.get(edge.budget or "")
    if budget is None:
        # 校验器会拦住未定义的预算；运行时保守处理成「没用尽」，宁可多跑一轮也不要
        # 把正常链路提前掐断。步数上限仍然兜着。
        return False

    current = getattr(state, budget.counter, 0) or 0
    if budget.limit is not None:
        limit = budget.limit
    else:
        limit = getattr(state, budget.limit_from or "", 0) or 0
    return current >= limit


def resolve_edge(edge: Edge, graph: ChapterGraph, state: ChapterRunState) -> str:
    """这条边实际要去的目标。"""
    if edge.budget or edge.disabled_when:
        if _budget_exhausted(edge, graph, state):
            return edge.on_exhausted or TARGET_DONE
    return edge.goto


async def run_chapter_graph(
    state: ChapterRunState,
    graph: ChapterGraph,
    *,
    on_step_start=None,
) -> GraphOutcome:
    """按图执行一章。

    Args:
        state: 黑板。适配器读写它。`state.runtime.nodes` 是节点库，
            `state.prompt_category` 是工作流级的提示词 category 覆盖。
        graph: 生效的图。
        on_step_start: 可选钩子 `(step, node) -> Awaitable[None]`，每步执行前调用。

    Returns:
        `GraphOutcome`：正常走完、需要暂停、或需要整章重跑。

    Raises:
        ChapterGraphError: 步数超过 `MAX_STEPS_PER_CHAPTER`。静态校验已拦下无守卫的
            环，这里兜的是预算字段写错导致的不收敛 —— 每一步都是真金白银的 LLM 调用。
    """
    step_id = graph.entry
    executed = 0
    catalog = getattr(state.runtime, "nodes", None)

    while True:
        if step_id == TARGET_DONE:
            return GraphOutcome(OUTCOME_DONE, steps_run=executed)
        if step_id == TARGET_RETRY:
            return GraphOutcome(OUTCOME_RETRY, steps_run=executed)
        if step_id.startswith(PAUSE_PREFIX):
            return GraphOutcome(
                OUTCOME_PAUSE, anchor=step_id[len(PAUSE_PREFIX):], steps_run=executed
            )

        step = graph.steps.get(step_id)
        if step is None:
            # 校验器保证不会走到这里；真发生了就当正常结束，而不是让 worker 崩掉一整章。
            logger.warning("chapter_graph_dangling_target step_id=%s", step_id)
            return GraphOutcome(OUTCOME_DONE, steps_run=executed)

        if executed >= MAX_STEPS_PER_CHAPTER:
            raise ChapterGraphError(
                f"单章执行步数超过上限 {MAX_STEPS_PER_CHAPTER}（停在 {step_id!r}）。"
                f"很可能有一条带预算的回边没有真正收敛。"
            )
        executed += 1

        node = resolve_node(step.node, step.role, catalog)

        if on_step_start is not None:
            await on_step_start(step, node)

        adapter = steps.adapter_for(step.role)
        # 提示词覆盖**逐步骤**生效：同一角色在图里出现多次时各用自己节点的提示词，
        # 而三个 validator 角色共用的内置提示词名也不会互相牵连。
        # 节点没有自定义提示词、工作流也没有 category 覆盖时作用域为空，
        # 提示词解析路径与改造前完全一致（长篇即是此例）。
        with prompt_scope.scoped(
            PromptScope(
                category=getattr(state, "prompt_category", None),
                names=prompt_overrides_for(node),
            )
        ):
            verdict = await adapter.run(state, node)

        step_id = resolve_edge(step.edge_for(verdict), graph, state)
