"""工作流的阶段模型。

`pipeline_configs.stages` 是**有序**阶段列表，取代原先「`nodes` 集合 + 两个布尔列」的
表达方式。原先的表达有两个问题：

* `nodes` 实际只被读取 `editor`/`extractor` 两个成员的存在性 —— `planner`/`writer`/
  `validator` 写不写都会跑。它名义上是节点列表，实际是两个开关。
* 顺序无法表达。而 `PipelineConfig.to_pipeline_order()` 恰恰依赖顺序来做前向单调
  校验，前端的复选框又无法产生顺序 —— 名不副实。

**刻意保持硬编码的部分**：write→edit→validate 簇内部的重写回边、强制修正、attempt 级
递归，以及同一 agent 的多角色（editor 有 review/force_revise/style_repair，validator 有
pre_editor/post_edit/final）。理由是这套拓扑对每个工作流都相同，长短篇差异全在提示词、
策略、上下文和质量维度上，不在拓扑上；而 `_process_single_chapter` 的 resume 语义极
微妙，把回边做成可从 JSON 重连的通用图引擎只会引入无人需要的风险。

所以本模块数据化的是「哪些阶段出场、以什么线性顺序」，不是「重试拓扑怎么连」。
阶段之间的 resume 锚点仍是那 5 个 agent 级名字，与存量 `job.current_step` 取值一致，
在飞项目零迁移。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from agents.constants import (
    AGENT_EDITOR,
    AGENT_EXTRACTOR,
    AGENT_PLANNER,
    AGENT_VALIDATOR,
    AGENT_WRITER,
)

# 阶段角色。同一 agent 在不同角色下做的事不同，这是 `nodes` 无法表达而 stages 能。
ROLE_OUTLINE = "outline"
ROLE_DRAFT = "draft"
ROLE_PRE_EDITOR = "pre_editor"
ROLE_REVIEW = "review"
ROLE_POST_EDIT = "post_edit"
ROLE_STYLE_REPAIR = "style_repair"
ROLE_FINAL = "final"
ROLE_POSTPROCESS = "postprocess"

# 只在**图模型**里出现的角色（见 `services/chapter_graph`）。
#
# 它们刻意**不进** `VALID_STAGES`：`stages` 是线性阶段模型，表达不了「只能从重写边
# 到达」（force_revise）或「没有 agent、没有提示词」（context_refresh / publish）。
# 把它们塞进 `stages` 只会让前端的阶段勾选框长出三个无意义的条目。
ROLE_FORCE_REVISE = "force_revise"
ROLE_CONTEXT_REFRESH = "context_refresh"
ROLE_PUBLISH = "publish"

# ---------------------------------------------------------------------------
# 裁决词表
# ---------------------------------------------------------------------------
#
# 每个值都对应生成主循环里一处**真实存在**的分支，不是通用状态机的摆设：
#
# * `ok`      —— 走默认后继
# * `rewrite` —— Editor 打回 / 编辑后校验要求再走一轮
# * `fail`    —— 终审未通过，交给 attempt 预算
# * `blocked` —— 需要人工介入（终审 terminal_block、强制保存后待复核）
# * `empty`   —— Planner 没产出可用大纲
# * `skipped` —— 该步的确定性门控没触发（去 AI 腔未被判定需要、本轮不必重写初稿、
#                未启用强制修正）
#
# 前端**不能**扩展它：新增裁决意味着主循环要长出新的消费逻辑，那需要写 Python。
# 放在 services/ 而不是 worker_support/ 是因为图校验器（services/chapter_graph）要用，
# 而 services 不得导入 worker_support。
VERDICT_OK = "ok"
VERDICT_REWRITE = "rewrite"
VERDICT_FAIL = "fail"
VERDICT_BLOCKED = "blocked"
VERDICT_EMPTY = "empty"
VERDICT_SKIPPED = "skipped"

ALL_VERDICTS: frozenset[str] = frozenset(
    {
        VERDICT_OK,
        VERDICT_REWRITE,
        VERDICT_FAIL,
        VERDICT_BLOCKED,
        VERDICT_EMPTY,
        VERDICT_SKIPPED,
    }
)

# 章节状态推进的规范 agent 顺序。``PipelineStep`` 的顺序由它派生，与细粒度的
# 阶段编排解耦（见 ``StagePlan.agent_order`` 的说明）。
CANONICAL_AGENT_ORDER: tuple[str, ...] = (
    AGENT_PLANNER,
    AGENT_WRITER,
    AGENT_EDITOR,
    AGENT_VALIDATOR,
    AGENT_EXTRACTOR,
)

# 每个 (agent, role) 组合是否合法。未登记的组合在校验时被丢弃。
VALID_STAGES: frozenset[tuple[str, str]] = frozenset(
    {
        (AGENT_PLANNER, ROLE_OUTLINE),
        (AGENT_WRITER, ROLE_DRAFT),
        (AGENT_VALIDATOR, ROLE_PRE_EDITOR),
        (AGENT_EDITOR, ROLE_REVIEW),
        (AGENT_VALIDATOR, ROLE_POST_EDIT),
        (AGENT_EDITOR, ROLE_STYLE_REPAIR),
        (AGENT_VALIDATOR, ROLE_FINAL),
        (AGENT_EXTRACTOR, ROLE_POSTPROCESS),
    }
)

# 不可移除的阶段：今天的生成主循环无条件执行它们，把它们做成可选会直接产出空章节。
REQUIRED_STAGES: frozenset[tuple[str, str]] = frozenset(
    {
        (AGENT_WRITER, ROLE_DRAFT),
        (AGENT_VALIDATOR, ROLE_FINAL),
    }
)


@dataclass(frozen=True)
class Stage:
    agent: str
    role: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.agent, self.role)

    def to_dict(self) -> dict[str, str]:
        return {"agent": self.agent, "role": self.role}


def default_stages(
    nodes: Iterable[str] | None,
    *,
    validation_before_editor: bool = False,
) -> list[Stage]:
    """从存量 ``nodes`` + ``validation_before_editor`` 派生等价的阶段列表。

    ``stages`` 列为空时使用，保证存量两行（以及任何未迁移的库）行为不变。
    空 ``nodes`` 沿用既有兜底语义：视为全部节点都在。
    """
    node_set = {str(n) for n in (nodes or [])}
    everything = not node_set

    stages: list[Stage] = []
    if everything or AGENT_PLANNER in node_set:
        stages.append(Stage(AGENT_PLANNER, ROLE_OUTLINE))
    # writer 无条件执行 —— 与今天的主循环一致。
    stages.append(Stage(AGENT_WRITER, ROLE_DRAFT))
    if validation_before_editor:
        stages.append(Stage(AGENT_VALIDATOR, ROLE_PRE_EDITOR))
    if everything or AGENT_EDITOR in node_set:
        stages.append(Stage(AGENT_EDITOR, ROLE_REVIEW))
        stages.append(Stage(AGENT_VALIDATOR, ROLE_POST_EDIT))
        stages.append(Stage(AGENT_EDITOR, ROLE_STYLE_REPAIR))
    stages.append(Stage(AGENT_VALIDATOR, ROLE_FINAL))
    if everything or AGENT_EXTRACTOR in node_set:
        stages.append(Stage(AGENT_EXTRACTOR, ROLE_POSTPROCESS))
    return stages


def parse_stages(raw: Any) -> list[Stage]:
    """把 ``pipeline_configs.stages`` 的 JSON 解析成 Stage 列表。

    丢弃非法/未登记条目而不是抛异常 —— 工作流记录可由用户编辑，一条坏数据不该让
    整个生成任务失败。去重保序。
    """
    if not isinstance(raw, list):
        return []
    stages: list[Stage] = []
    seen: set[tuple[str, str]] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        agent = str(item.get("agent") or "").strip()
        role = str(item.get("role") or "").strip()
        if (agent, role) not in VALID_STAGES or (agent, role) in seen:
            continue
        seen.add((agent, role))
        stages.append(Stage(agent, role))
    return stages


def normalize_stages(stages: list[Stage]) -> list[Stage]:
    """补齐必需阶段，并移除依赖不满足的阶段。

    * ``writer/draft`` 与 ``validator/final`` 必须存在
    * ``editor/style_repair`` 与 ``validator/post_edit`` 依赖 ``editor/review``
      —— 没有 review 的 Editor 阶段在主循环里没有入口
    """
    present = {stage.key for stage in stages}
    has_review = (AGENT_EDITOR, ROLE_REVIEW) in present

    kept = [
        stage
        for stage in stages
        if has_review
        or stage.key not in {(AGENT_EDITOR, ROLE_STYLE_REPAIR), (AGENT_VALIDATOR, ROLE_POST_EDIT)}
    ]

    present = {stage.key for stage in kept}
    for required in (Stage(AGENT_WRITER, ROLE_DRAFT), Stage(AGENT_VALIDATOR, ROLE_FINAL)):
        if required.key not in present:
            kept.append(required)
    return kept


def stages_for_config(
    raw_stages: Any,
    nodes: Iterable[str] | None,
    *,
    validation_before_editor: bool = False,
) -> list[Stage]:
    """该工作流最终生效的阶段列表。``stages`` 列为空时从 ``nodes`` 派生。"""
    parsed = parse_stages(raw_stages)
    if not parsed:
        parsed = default_stages(nodes, validation_before_editor=validation_before_editor)
    return normalize_stages(parsed)


@dataclass(frozen=True)
class StagePlan:
    """阶段列表投影出的执行开关。

    生成主循环读这些布尔量，而不是自己判断 ``nodes`` 成员 —— 于是「跑哪些阶段」
    真正由数据决定。
    """

    stages: tuple[Stage, ...]
    has_planner: bool
    has_editor: bool
    has_extractor: bool
    has_style_repair: bool
    validation_before_editor: bool

    @classmethod
    def from_stages(cls, stages: list[Stage]) -> "StagePlan":
        present = {stage.key for stage in stages}
        has_editor = (AGENT_EDITOR, ROLE_REVIEW) in present
        return cls(
            stages=tuple(stages),
            has_planner=(AGENT_PLANNER, ROLE_OUTLINE) in present,
            has_editor=has_editor,
            has_extractor=(AGENT_EXTRACTOR, ROLE_POSTPROCESS) in present,
            # style_repair 需要 Editor agent 才有意义。
            has_style_repair=has_editor and (AGENT_EDITOR, ROLE_STYLE_REPAIR) in present,
            validation_before_editor=(AGENT_VALIDATOR, ROLE_PRE_EDITOR) in present,
        )

    def to_json(self) -> list[dict[str, str]]:
        return [stage.to_dict() for stage in self.stages]

    def agent_order(self) -> list[str]:
        """出场的 agent，按**规范顺序**排列，用于派生 PipelineStep 顺序。

        刻意不用「阶段列表里的首次出现顺序」：``PipelineStep`` 是章节状态的粗粒度
        推进（outline → writing → editing → validating → extracting → published），
        ``validate_pipeline_transition`` 要求它单调不回退。而阶段列表里
        ``validator/pre_editor`` 排在 ``editor/review`` 之前，若按首次出现排序就会得到
        「validating 早于 editing」，于是正常的 editor→validator 流转会被判成回退并抛
        ``PipelineStateError``。

        换言之：细粒度的阶段顺序可以自由编排，但章节状态的推进顺序是固定的。
        这也正是原先 ``nodes`` 列的语义 —— 它在库里本就是规范顺序。
        """
        present = {stage.agent for stage in self.stages}
        return [agent for agent in CANONICAL_AGENT_ORDER if agent in present]
