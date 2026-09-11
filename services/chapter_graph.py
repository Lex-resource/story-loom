"""单章生成拓扑的图模型。

`pipeline_configs.graph` 存的就是本模块解析的结构。**代码是默认拓扑的权威，数据库
只负责自定义** —— 与 `stages` 为空时从 `nodes` 派生同一个手法，也意味着生产那两行
可以把 `graph` 留空而依然走图引擎（`default_graph()` 复现今天的行为）。

放在 `services/` 而非 `worker_support/`：写入工作流时 router 要做语义校验，而
`services/` 不得导入 `worker_support/`（架构 AST 测试强制）。解释器在
`worker_support/chapter_graph_runner.py`。

## 为什么边上有预算而不是节点上有循环计数

今天的重写回边有两种「用尽」语义，它们**不一样**：

* 进入 write-edit 簇之前：只看 `rewrite_count >= max_rewrites`。从 validator 恢复时
  `rewrite_count` 已被顶到上限，于是整簇跳过（`skip_write_edit`）。
* Editor 判 rewrite 之后：还要看 `enable_editor_loop`。该开关为假时**第一次**打回就
  出圈，但初稿仍然写了一版。

所以 `disabled_when` 属于**边**而不是预算本身 —— 同一个 `rewrite` 预算，入口边不看
开关、回边看。早期把它放在预算上会让 `enable_editor_loop=False` 的工作流连初稿都不写。

## 目标（target）词表

* 步骤 id —— 跳到该步骤
* `@pause:<锚点>` —— 暂停任务，`job.current_step` 置为锚点（5 个 agent 名之一）
* `@retry_chapter` —— 整章重跑（attempt + 1）
* `@done` —— 正常结束
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from agents.constants import (
    AGENT_EDITOR,
    AGENT_EXTRACTOR,
    AGENT_PLANNER,
    AGENT_VALIDATOR,
    AGENT_WRITER,
)
from services.pipeline_stages import (
    ALL_VERDICTS,
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

logger = logging.getLogger(__name__)

GRAPH_VERSION = 1

# 解释器单章内允许执行的最大步数。用户可编辑的图能造出病态环，静态校验拦住无守卫的
# 回边之后这条仍要留着 —— 带预算的环也可能因为预算字段写错而不收敛，而每一步都是一次
# LLM 调用，跑飞的代价是真金白银。
MAX_STEPS_PER_CHAPTER = 200

TARGET_DONE = "@done"
TARGET_RETRY = "@retry_chapter"
PAUSE_PREFIX = "@pause:"

# 合法的暂停锚点 = 存量 `job.current_step` / `chapter.pipeline_step` 的取值域。
# 细粒度阶段怎么编排都不影响在飞项目的恢复，正是因为锚点被限制在这 5 个值里。
VALID_ANCHORS: frozenset[str] = frozenset(
    {AGENT_PLANNER, AGENT_WRITER, AGENT_EDITOR, AGENT_VALIDATOR, AGENT_EXTRACTOR}
)

# 角色 -> 执行它的 agent。**由角色推导，不是用户输入**：角色决定跑哪个适配器，
# 适配器调用哪个 agent 的哪个方法是写死的 Python。前端只读展示。
ROLE_AGENT: dict[str, str | None] = {
    ROLE_OUTLINE: AGENT_PLANNER,
    ROLE_CONTEXT_REFRESH: None,
    ROLE_DRAFT: AGENT_WRITER,
    ROLE_PRE_EDITOR: AGENT_VALIDATOR,
    ROLE_REVIEW: AGENT_EDITOR,
    ROLE_FORCE_REVISE: AGENT_EDITOR,
    ROLE_POST_EDIT: AGENT_VALIDATOR,
    ROLE_STYLE_REPAIR: AGENT_EDITOR,
    ROLE_FINAL: AGENT_VALIDATOR,
    ROLE_PUBLISH: None,
    ROLE_POSTPROCESS: AGENT_EXTRACTOR,
}

GRAPH_ROLES: frozenset[str] = frozenset(ROLE_AGENT)

# 系统角色：没有提示词，用户不得从工作流里删掉。
# `context_refresh` 是循环顶部的上下文刷新兼「本轮要不要重写」的判定；`publish` 把校验
# 结论落定。删掉前者会让重写回边拿着过期记忆跑，删掉后者章节永远发布不了。
SYSTEM_ROLES: frozenset[str] = frozenset({ROLE_CONTEXT_REFRESH, ROLE_PUBLISH})

# 必须存在的角色。缺任何一个都会产出空章节或永不发布的章节。
REQUIRED_ROLES: frozenset[str] = frozenset(
    {ROLE_DRAFT, ROLE_FINAL, ROLE_PUBLISH, ROLE_POSTPROCESS}
)

# 每个角色**必须**显式处理的裁决。未登记的裁决走默认后继，对大多数情况是安全的
# （`skipped` 落到 next 通常就是对的），但下面这些不行：Editor 判了 rewrite 却直接
# 往下走，等于把它判定不合格的稿子发出去。
REQUIRED_VERDICT_HANDLERS: dict[str, frozenset[str]] = {
    ROLE_OUTLINE: frozenset({VERDICT_EMPTY}),
    ROLE_REVIEW: frozenset({VERDICT_REWRITE}),
    ROLE_FORCE_REVISE: frozenset({VERDICT_SKIPPED}),
    ROLE_FINAL: frozenset({VERDICT_BLOCKED, VERDICT_FAIL}),
    ROLE_PUBLISH: frozenset({VERDICT_BLOCKED}),
}


class ChapterGraphError(ValueError):
    """图结构非法。API 写入时抛出；运行时不抛（改为回落到默认图）。"""


@dataclass(frozen=True)
class Edge:
    """一条出边。

    Attributes:
        goto: 目标（步骤 id 或 `@` 前缀的特殊目标）。
        budget: 预算名。有值时先判断预算是否已用尽，用尽则走 `on_exhausted`。
        disabled_when: `GenerationPipelineRuntime` 上的布尔字段名。该字段为**假**时
            本条边视为预算已用尽 —— 用于 `enable_editor_loop=False` 直接禁用回边。
        on_exhausted: 预算用尽时的目标。
    """

    goto: str
    budget: str | None = None
    disabled_when: str | None = None
    on_exhausted: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"goto": self.goto}
        if self.budget:
            data["budget"] = self.budget
        if self.disabled_when:
            data["disabled_when"] = self.disabled_when
        if self.on_exhausted:
            data["on_exhausted"] = self.on_exhausted
        return data

    def targets(self) -> tuple[str, ...]:
        return (self.goto,) if not self.on_exhausted else (self.goto, self.on_exhausted)


@dataclass(frozen=True)
class Budget:
    """一个计数上限。

    计数器由**适配器**维护（`review` 自己给 `rewrite_count` 加一并写档），引擎只做
    比较 —— 因为「第几次重写、为什么」是那一步的产出，不是边的产出。

    Attributes:
        counter: `ChapterRunState` 上的计数字段名。
        limit: 固定上限。
        limit_from: `ChapterRunState` 上的上限字段名（与 `limit` 二选一）。
    """

    counter: str
    limit: int | None = None
    limit_from: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"counter": self.counter}
        if self.limit is not None:
            data["limit"] = self.limit
        if self.limit_from:
            data["limit_from"] = self.limit_from
        return data


@dataclass(frozen=True)
class Step:
    """一个步骤。

    Attributes:
        id: 图内唯一 id。
        role: 角色，决定跑哪个适配器。
        node: `workflow_nodes.id`。`None` 表示用该角色的内置节点与内置提示词。
        next: 裁决 `ok`（以及任何未在 `on` 里登记的裁决）走的边。
        on: 裁决 -> 边。
    """

    id: str
    role: str
    node: str | None = None
    next: Edge = field(default_factory=lambda: Edge(TARGET_DONE))
    on: dict[str, Edge] = field(default_factory=dict)

    @property
    def agent(self) -> str | None:
        return ROLE_AGENT.get(self.role)

    def edge_for(self, verdict: str) -> Edge:
        return self.on.get(verdict, self.next)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"id": self.id, "role": self.role, "next": self.next.to_dict()}
        if self.node:
            data["node"] = self.node
        if self.on:
            data["on"] = {verdict: edge.to_dict() for verdict, edge in self.on.items()}
        return data


@dataclass(frozen=True)
class ChapterGraph:
    entry: str
    steps: dict[str, Step]
    budgets: dict[str, Budget]
    version: int = GRAPH_VERSION

    def step(self, step_id: str) -> Step:
        return self.steps[step_id]

    def has_role(self, role: str) -> bool:
        return any(step.role == role for step in self.steps.values())

    def roles(self) -> tuple[str, ...]:
        return tuple(step.role for step in self.steps.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "entry": self.entry,
            "budgets": {name: budget.to_dict() for name, budget in self.budgets.items()},
            "steps": [step.to_dict() for step in self.steps.values()],
        }


# ---------------------------------------------------------------------------
# 默认图：复现今天 _process_single_chapter 的拓扑
# ---------------------------------------------------------------------------

BUDGET_REWRITE = "rewrite"
BUDGET_ATTEMPT = "attempt"

DEFAULT_BUDGETS: dict[str, Budget] = {
    BUDGET_REWRITE: Budget(counter="rewrite_count", limit_from="max_rewrites"),
    # 整章重跑上限。硬编码 3 与 generate_job_runner 里原本的 `attempt < 3` 一致。
    BUDGET_ATTEMPT: Budget(counter="attempt", limit=3),
}


def default_graph(
    *,
    has_editor: bool = True,
    has_style_repair: bool = True,
    validation_before_editor: bool = False,
) -> ChapterGraph:
    """构造与今天硬编码顺序等价的图。

    `graph` 列为空时使用。golden trace（`tests/worker_support/test_generation_trace.py`
    的 20 个场景）逐项校验本函数产出的图与原硬编码循环行为一致 —— 那是「拓扑数据化
    没有改变行为」的唯一硬证据。

    注意 `plan`（大纲）**无条件在场**：今天的主循环也是无条件调用
    `prepare_chapter_outline` 的，`use_existing_outline` 才是「复用还是重新策划」的开关。
    把它做成可缺省会让 Writer 拿到空大纲。
    """
    # 线性骨架，顺序即今天的执行顺序。force_fix 不在骨架里 —— 它只能从重写边到达。
    skeleton: list[tuple[str, str, bool]] = [
        ("plan", ROLE_OUTLINE, True),
        ("loop_head", ROLE_CONTEXT_REFRESH, True),
        ("draft", ROLE_DRAFT, True),
        ("pre_check", ROLE_PRE_EDITOR, validation_before_editor),
        ("review", ROLE_REVIEW, has_editor),
        ("post_check", ROLE_POST_EDIT, has_editor),
        ("polish", ROLE_STYLE_REPAIR, has_editor and has_style_repair),
        ("final_check", ROLE_FINAL, True),
        ("publish", ROLE_PUBLISH, True),
        ("post", ROLE_POSTPROCESS, True),
    ]
    present = [(step_id, role) for step_id, role, keep in skeleton if keep]
    order = [step_id for step_id, _ in present]

    def after(step_id: str) -> str:
        """线性骨架里 step_id 之后的第一个在场步骤。"""
        index = order.index(step_id)
        return order[index + 1] if index + 1 < len(order) else TARGET_DONE

    # 循环出口 = write-edit 簇之后的第一个在场步骤。
    loop_exit = next(
        (step_id for step_id in ("polish", "final_check") if step_id in order),
        TARGET_DONE,
    )

    steps: dict[str, Step] = {}
    for step_id, role in present:
        steps[step_id] = Step(id=step_id, role=role, next=Edge(after(step_id)))

    # plan -> 循环入口。预算已用尽（skip_write_edit 把 rewrite_count 顶到上限）时整簇跳过。
    # 这条边刻意**不**带 disabled_when：enable_editor_loop=False 只禁回边，初稿照写。
    steps["plan"] = Step(
        id="plan",
        role=ROLE_OUTLINE,
        next=Edge("loop_head", budget=BUDGET_REWRITE, on_exhausted=loop_exit),
        on={VERDICT_EMPTY: Edge(f"{PAUSE_PREFIX}{AGENT_PLANNER}")},
    )

    # 循环顶部：裁决 skipped 表示本轮不必重写初稿，跳过 draft 但仍走 draft 之后的步骤
    # （前置校验在 decision 不是 rewrite 时也要跑 —— 实测如此）。
    steps["loop_head"] = Step(
        id="loop_head",
        role=ROLE_CONTEXT_REFRESH,
        next=Edge("draft"),
        on={VERDICT_SKIPPED: Edge(after("draft"))},
    )

    if has_editor:
        steps["review"] = Step(
            id="review",
            role=ROLE_REVIEW,
            next=Edge(after("review")),
            on={
                VERDICT_REWRITE: Edge(
                    "loop_head",
                    budget=BUDGET_REWRITE,
                    disabled_when="enable_editor_loop",
                    on_exhausted="force_fix",
                )
            },
        )
        steps["force_fix"] = Step(
            id="force_fix",
            role=ROLE_FORCE_REVISE,
            next=Edge(loop_exit),
            on={VERDICT_SKIPPED: Edge(f"{PAUSE_PREFIX}{AGENT_EDITOR}")},
        )
        steps["post_check"] = Step(
            id="post_check",
            role=ROLE_POST_EDIT,
            next=Edge(loop_exit),
            on={
                VERDICT_REWRITE: Edge(
                    "loop_head", budget=BUDGET_REWRITE, on_exhausted=loop_exit
                )
            },
        )

    steps["final_check"] = Step(
        id="final_check",
        role=ROLE_FINAL,
        next=Edge("publish"),
        on={
            VERDICT_BLOCKED: Edge(f"{PAUSE_PREFIX}{AGENT_VALIDATOR}"),
            # 终审不通过 -> 整章重跑；attempt 用尽后暂停，绝不把失败稿送进 publish。
            VERDICT_FAIL: Edge(
                TARGET_RETRY,
                budget=BUDGET_ATTEMPT,
                on_exhausted=f"{PAUSE_PREFIX}{AGENT_VALIDATOR}",
            ),
        },
    )
    steps["publish"] = Step(
        id="publish",
        role=ROLE_PUBLISH,
        next=Edge("post"),
        on={VERDICT_BLOCKED: Edge(f"{PAUSE_PREFIX}{AGENT_VALIDATOR}")},
    )
    steps["post"] = Step(id="post", role=ROLE_POSTPROCESS, next=Edge(TARGET_DONE))

    # 按骨架顺序重排（force_fix 紧跟 review），让序列化结果稳定可读。
    ordered_ids = []
    for step_id in order:
        ordered_ids.append(step_id)
        if step_id == "review":
            ordered_ids.append("force_fix")

    return ChapterGraph(
        entry="plan",
        steps={step_id: steps[step_id] for step_id in ordered_ids},
        budgets=dict(DEFAULT_BUDGETS),
    )


# ---------------------------------------------------------------------------
# 解析与校验
# ---------------------------------------------------------------------------

def _parse_edge(raw: Any) -> Edge | None:
    """边可以写成裸字符串（只有目标）或对象。"""
    if isinstance(raw, str):
        return Edge(raw.strip()) if raw.strip() else None
    if not isinstance(raw, dict):
        return None
    goto = str(raw.get("goto") or "").strip()
    if not goto:
        return None
    budget = raw.get("budget")
    disabled_when = raw.get("disabled_when")
    on_exhausted = raw.get("on_exhausted")
    return Edge(
        goto=goto,
        budget=str(budget).strip() or None if budget else None,
        disabled_when=str(disabled_when).strip() or None if disabled_when else None,
        on_exhausted=str(on_exhausted).strip() or None if on_exhausted else None,
    )


def _parse_budget(raw: Any) -> Budget | None:
    if not isinstance(raw, dict):
        return None
    counter = str(raw.get("counter") or "").strip()
    if not counter:
        return None
    limit = raw.get("limit")
    if not isinstance(limit, int) or isinstance(limit, bool):
        limit = None
    limit_from = raw.get("limit_from")
    limit_from = str(limit_from).strip() if limit_from else None
    if limit is None and not limit_from:
        return None
    return Budget(counter=counter, limit=limit, limit_from=limit_from)


def parse_graph(raw: Any) -> ChapterGraph | None:
    """把 `pipeline_configs.graph` 的 JSON 解析成 `ChapterGraph`。

    结构不完整时返回 `None`（调用方回落到 `default_graph`），**不抛异常** ——
    一条坏数据不该让整个生成任务失败。语义校验交给 `validate_graph`，那是写入时的事。
    """
    if not isinstance(raw, dict):
        return None
    raw_steps = raw.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        return None

    steps: dict[str, Step] = {}
    for item in raw_steps:
        if not isinstance(item, dict):
            continue
        step_id = str(item.get("id") or "").strip()
        role = str(item.get("role") or "").strip()
        if not step_id or role not in GRAPH_ROLES or step_id in steps:
            continue
        next_edge = _parse_edge(item.get("next")) or Edge(TARGET_DONE)
        on: dict[str, Edge] = {}
        raw_on = item.get("on")
        if isinstance(raw_on, dict):
            for verdict, edge_raw in raw_on.items():
                if verdict not in ALL_VERDICTS:
                    continue
                edge = _parse_edge(edge_raw)
                if edge is not None:
                    on[verdict] = edge
        node = item.get("node")
        steps[step_id] = Step(
            id=step_id,
            role=role,
            node=str(node).strip() if node else None,
            next=next_edge,
            on=on,
        )

    if not steps:
        return None

    budgets: dict[str, Budget] = {}
    raw_budgets = raw.get("budgets")
    if isinstance(raw_budgets, dict):
        for name, budget_raw in raw_budgets.items():
            budget = _parse_budget(budget_raw)
            if budget is not None:
                budgets[str(name)] = budget
    # 没写预算就用默认的两个 —— 否则带 budget 的边会因为查不到而被当成「未用尽」，
    # 于是重写回边永不收敛。
    for name, budget in DEFAULT_BUDGETS.items():
        budgets.setdefault(name, budget)

    entry = str(raw.get("entry") or "").strip()
    if entry not in steps:
        entry = next(iter(steps))

    version = raw.get("version")
    return ChapterGraph(
        entry=entry,
        steps=steps,
        budgets=budgets,
        version=version if isinstance(version, int) else GRAPH_VERSION,
    )


def _is_special(target: str) -> bool:
    return target.startswith("@")


def _iter_edges(step: Step) -> Iterable[Edge]:
    yield step.next
    yield from step.on.values()


def validate_graph(graph: ChapterGraph) -> list[str]:
    """返回所有语义错误；空列表表示可用。

    写入工作流时调用。运行时不调用 —— 运行时只解析，解析不出来就用默认图。
    """
    errors: list[str] = []

    if graph.entry not in graph.steps:
        errors.append(f"entry 指向不存在的步骤 {graph.entry!r}")

    # --- 目标可解析 ---
    for step in graph.steps.values():
        for edge in _iter_edges(step):
            for target in edge.targets():
                if _is_special(target):
                    if target in (TARGET_DONE, TARGET_RETRY):
                        continue
                    if target.startswith(PAUSE_PREFIX):
                        anchor = target[len(PAUSE_PREFIX):]
                        if anchor not in VALID_ANCHORS:
                            errors.append(
                                f"步骤 {step.id!r} 的暂停锚点 {anchor!r} 不是合法的恢复锚点"
                                f"（只能是 {'、'.join(sorted(VALID_ANCHORS))}）"
                            )
                        continue
                    errors.append(f"步骤 {step.id!r} 使用了未知的特殊目标 {target!r}")
                elif target not in graph.steps:
                    errors.append(f"步骤 {step.id!r} 指向不存在的步骤 {target!r}")
            if edge.budget and edge.budget not in graph.budgets:
                errors.append(f"步骤 {step.id!r} 引用了未定义的预算 {edge.budget!r}")
            if edge.budget and not edge.on_exhausted:
                errors.append(
                    f"步骤 {step.id!r} 的边带预算 {edge.budget!r} 但没有 on_exhausted，"
                    f"用尽后无处可去"
                )

    # --- 必需角色 ---
    roles = set(graph.roles())
    for role in sorted(REQUIRED_ROLES - roles):
        errors.append(f"缺少必需角色 {role!r}")

    # --- 必需的裁决处理 ---
    for step in graph.steps.values():
        required = REQUIRED_VERDICT_HANDLERS.get(step.role, frozenset())
        for verdict in sorted(required - set(step.on)):
            errors.append(
                f"步骤 {step.id!r}（{step.role}）没有处理裁决 {verdict!r}；"
                f"未处理的裁决会走默认后继，那意味着把不合格的稿子往下发"
            )

    # --- 环必须有预算守卫 ---
    errors.extend(_unguarded_cycles(graph))

    return errors


def _unguarded_cycles(graph: ChapterGraph) -> list[str]:
    """找出没有预算守卫的回边。

    用户可以在界面上把任意步骤连回任意步骤。没有预算的环 = 无限循环 = 无限烧
    LLM token，必须在写入时拒掉，不能等运行时的步数上限兜。

    DFS 三色标记：走到 GRAY 节点即回边。
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {step_id: WHITE for step_id in graph.steps}
    errors: list[str] = []

    def visit(step_id: str) -> None:
        color[step_id] = GRAY
        step = graph.steps[step_id]
        for edge in _iter_edges(step):
            for target in edge.targets():
                if _is_special(target) or target not in graph.steps:
                    continue
                if color[target] == GRAY:
                    if not edge.budget:
                        errors.append(
                            f"步骤 {step.id!r} -> {target!r} 是一条没有预算守卫的回边，"
                            f"会无限循环；给它加 budget 与 on_exhausted"
                        )
                elif color[target] == WHITE:
                    visit(target)
        color[step_id] = BLACK

    for step_id in graph.steps:
        if color[step_id] == WHITE:
            visit(step_id)
    return errors


def graph_for_config(
    raw_graph: Any,
    *,
    has_editor: bool = True,
    has_style_repair: bool = True,
    validation_before_editor: bool = False,
    label: str = "",
) -> ChapterGraph:
    """该工作流最终生效的图。`graph` 列为空或解析不出来时回落到默认图。"""
    parsed = parse_graph(raw_graph)
    if parsed is None:
        if raw_graph:
            logger.warning(
                "chapter_graph_unparseable workflow=%s falling_back_to_default", label
            )
        return default_graph(
            has_editor=has_editor,
            has_style_repair=has_style_repair,
            validation_before_editor=validation_before_editor,
        )
    return parsed
