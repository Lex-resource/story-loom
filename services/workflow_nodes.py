"""工作流节点库。

一个节点 = **角色 + 提示词 + 名称**。角色决定跑哪个适配器
（`worker_support/chapter_steps`），适配器调用哪个 agent 的哪个方法是写死的 Python ——
所以「执行器」由角色推导，不是用户输入（见 `services/chapter_graph.ROLE_AGENT`）。

节点能做到、也只能做到三件事：换名字、换提示词、换 `always_run` 之类的门控开关。
**凭空造出一种新的程序行为需要写 Python** —— 前端无法绕过这一点，因为五个执行器各有
自己的输出 schema，而主循环按固定语义消费它们的裁决（编辑的评分决定是否打回、
校验的 passed 决定是否强制修正）。界面上要把这句话说清楚，而不是假装可配。

配合图引擎（`services/chapter_graph`），节点可以任意重排、重复、分支：建三个不同提示词
的审稿节点、各自回边给 Writer 且预算不同，是真实可达的组合。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agents.constants import (
    PROMPT_EDITOR_DESTYLE,
    PROMPT_EDITOR_FORCE_REVISE,
    PROMPT_EDITOR_REVIEW,
    PROMPT_EXTRACTOR_EXTRACT_CHANGES,
    PROMPT_PLANNER_GENERATE_CHAPTER_OUTLINE,
    PROMPT_VALIDATOR_VALIDATE_CONTENT,
    PROMPT_WRITER,
)
from services.chapter_graph import GRAPH_ROLES, ROLE_AGENT, SYSTEM_ROLES
from services.pipeline_stages import (
    ROLE_DRAFT,
    ROLE_FINAL,
    ROLE_FORCE_REVISE,
    ROLE_OUTLINE,
    ROLE_POST_EDIT,
    ROLE_POSTPROCESS,
    ROLE_PRE_EDITOR,
    ROLE_REVIEW,
    ROLE_STYLE_REPAIR,
)

logger = logging.getLogger(__name__)

# 角色 -> 该角色的**主**提示词名。节点的 `prompt_name` 覆盖的就是它。
#
# 三个 validator 角色共用 `validator_validate_content`，但覆盖是**逐步骤**生效的
# （见 `services/prompt_scope`），所以只给 post_edit 换提示词不会影响 pre_editor 与终审。
#
# `outline` 只登记分章大纲这一个：策划步骤内部还会按需调用骨架优化、节奏审查等其他
# 提示词，那些不属于「这一步的主提示词」，不在覆盖范围内。
# 系统角色（context_refresh / publish）没有提示词，不在表里。
ROLE_PRIMARY_PROMPT: dict[str, str] = {
    ROLE_OUTLINE: PROMPT_PLANNER_GENERATE_CHAPTER_OUTLINE,
    ROLE_DRAFT: PROMPT_WRITER,
    ROLE_PRE_EDITOR: PROMPT_VALIDATOR_VALIDATE_CONTENT,
    ROLE_REVIEW: PROMPT_EDITOR_REVIEW,
    ROLE_FORCE_REVISE: PROMPT_EDITOR_FORCE_REVISE,
    ROLE_POST_EDIT: PROMPT_VALIDATOR_VALIDATE_CONTENT,
    ROLE_STYLE_REPAIR: PROMPT_EDITOR_DESTYLE,
    ROLE_FINAL: PROMPT_VALIDATOR_VALIDATE_CONTENT,
    ROLE_POSTPROCESS: PROMPT_EXTRACTOR_EXTRACT_CHANGES,
}

# 界面上给每个角色的说明。放在后端而不是前端，让 `GET /roles` 成为唯一来源 ——
# 角色词表变了前端自动跟上，不必两处同步。
ROLE_LABELS: dict[str, tuple[str, str]] = {
    ROLE_OUTLINE: ("大纲策划", "生成或复用本章分章大纲"),
    "context_refresh": ("上下文刷新", "系统步骤：循环顶部重新加载记忆，并判断本轮是否重写初稿"),
    ROLE_DRAFT: ("初稿撰写", "写本章正文"),
    ROLE_PRE_EDITOR: ("编辑前置校验", "编辑之前先校验一次，把硬伤交给编辑"),
    ROLE_REVIEW: ("编辑审阅", "按质量维度打分，可判定打回重写"),
    ROLE_FORCE_REVISE: ("强制修正", "重写预算耗尽后直接修正。只能从重写边到达"),
    ROLE_POST_EDIT: ("编辑后校验", "校验润色稿，可要求再走一轮"),
    ROLE_STYLE_REPAIR: ("文风修复", "去 AI 腔等纯文本变换，不改剧情"),
    ROLE_FINAL: ("终审与字数", "发布前的最终校验"),
    "publish": ("落定校验结论", "系统步骤：把校验结论写入章节"),
    ROLE_POSTPROCESS: ("沉淀记忆并发布", "提取设定、写入分层记忆并发布"),
}


@dataclass(frozen=True)
class WorkflowNode:
    id: str
    name_zh: str
    role: str
    prompt_name: str | None = None
    options: dict[str, Any] | None = None
    description: str | None = None
    builtin: bool = False

    @property
    def agent(self) -> str | None:
        """执行它的 agent。由角色推导，只读。"""
        return ROLE_AGENT.get(self.role)

    @property
    def effective_prompt(self) -> str | None:
        return self.prompt_name or ROLE_PRIMARY_PROMPT.get(self.role)

    def option(self, key: str, default: Any = None) -> Any:
        if not isinstance(self.options, dict):
            return default
        return self.options.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name_zh": self.name_zh,
            "role": self.role,
            "agent": self.agent,
            "prompt_name": self.prompt_name,
            "effective_prompt": self.effective_prompt,
            "options": self.options or {},
            "description": self.description,
            "builtin": self.builtin,
            "is_system": self.role in SYSTEM_ROLES,
        }


def builtin_node_id(role: str) -> str:
    """该角色的内置节点 id，与迁移里种子的 id 一致。"""
    agent = ROLE_AGENT.get(role) or "system"
    return f"{agent}.{role}"


def node_from_model(model: Any) -> WorkflowNode:
    return WorkflowNode(
        id=model.id,
        name_zh=model.name_zh,
        role=model.role,
        prompt_name=model.prompt_name,
        options=model.options if isinstance(model.options, dict) else None,
        description=model.description,
        builtin=bool(model.builtin),
    )


def validate_node_payload(
    payload: dict[str, Any], *, existing: WorkflowNode | None = None
) -> list[str]:
    """校验节点的写入载荷，返回错误列表。"""
    errors: list[str] = []

    role = payload.get("role", existing.role if existing else None)
    if not role:
        errors.append("必须指定角色 role")
    elif role not in GRAPH_ROLES:
        errors.append(f"未知角色 {role!r}；可用角色：{'、'.join(sorted(GRAPH_ROLES))}")
    elif role in SYSTEM_ROLES:
        errors.append(
            f"{role!r} 是系统角色，没有提示词也没有可配置项，不能新建自定义节点"
        )

    if existing is not None and existing.builtin:
        if "role" in payload and payload["role"] != existing.role:
            errors.append("内置节点的角色不可修改 —— 角色决定跑哪段 Python")

    name_zh = payload.get("name_zh", existing.name_zh if existing else None)
    if not (name_zh or "").strip():
        errors.append("必须填写节点名称 name_zh")

    options = payload.get("options")
    if options is not None and not isinstance(options, dict):
        errors.append("options 必须是对象")

    prompt_name = payload.get("prompt_name")
    if prompt_name is not None and not isinstance(prompt_name, str):
        errors.append("prompt_name 必须是字符串")

    return errors


# ---------------------------------------------------------------------------
# 提示词覆盖表
# ---------------------------------------------------------------------------

def prompt_overrides_for(node: WorkflowNode | None) -> dict[str, str]:
    """该节点在执行时要生效的 `内置提示词名 -> 覆盖名` 映射。

    节点没有自定义提示词时返回空表 —— 于是 `services/prompt_scope` 的作用域为空，
    提示词解析路径与改造前完全一致。
    """
    if node is None or not node.prompt_name:
        return {}
    builtin = ROLE_PRIMARY_PROMPT.get(node.role)
    if not builtin:
        return {}
    if builtin == node.prompt_name:
        return {}
    return {builtin: node.prompt_name}


def default_catalog() -> dict[str, WorkflowNode]:
    """代码兜底的内置节点库。

    数据库读取失败或表还没种子时使用 —— 图引用的节点 id 查不到会让整张图被判非法，
    而节点库是纯派生数据，没有理由让它成为单点故障。
    """
    catalog: dict[str, WorkflowNode] = {}
    for role in sorted(GRAPH_ROLES):
        node_id = builtin_node_id(role)
        label, description = ROLE_LABELS.get(role, (role, ""))
        catalog[node_id] = WorkflowNode(
            id=node_id,
            name_zh=label,
            role=role,
            description=description,
            builtin=True,
        )
    return catalog


async def load_catalog(db) -> dict[str, WorkflowNode]:
    """节点库全表。库里的行覆盖/扩展代码兜底，所以种子缺失也不会让图跑不起来。"""
    from sqlalchemy import select

    from models.novel import WorkflowNodeDict

    catalog = default_catalog()
    try:
        rows = (await db.execute(select(WorkflowNodeDict))).scalars().all()
    except Exception:
        logger.exception("workflow_node_catalog_load_failed")
        return catalog

    for row in rows:
        catalog[row.id] = node_from_model(row)
    return catalog


def resolve_node(
    node_id: str | None, role: str, catalog: dict[str, WorkflowNode] | None
) -> WorkflowNode | None:
    """把图步骤上的节点 id 解析成节点。

    id 为空表示用该角色的内置节点。id 查不到时回落到内置节点并记一条 warning ——
    删掉一个仍被某工作流引用的节点不该让那个工作流的生成任务直接失败（API 已经拒绝
    这种删除，这里兜的是手工改库）。
    """
    lookup = catalog if catalog is not None else default_catalog()
    if node_id:
        node = lookup.get(node_id)
        if node is not None:
            return node
        logger.warning(
            "workflow_node_missing node_id=%s role=%s using_builtin", node_id, role
        )
    return lookup.get(builtin_node_id(role))
