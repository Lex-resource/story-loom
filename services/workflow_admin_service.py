"""工作流与节点库的写入服务。

「工作流」现在是可增删的一等实体：`pipeline_configs` 不再只有内置两行。本模块负责
建、克隆、删、以及节点库的增删改，并把所有语义校验集中在写入路径上 ——
运行时（`services/chapter_graph.parse_graph`）刻意宽容（坏数据回落到默认图而不是让
生成任务失败），所以严格性必须在这里兑现。

**为什么删除要设护栏**：`get_pipeline_config` 查不到工作流会抛 `ValueError`，而它在
worker 的每章生成路径上 —— 删掉一个还有项目在用的工作流，那些项目的生成任务会直接
失败且看不出原因。所以这里宁可拒绝删除并说明谁在用。
"""
from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.constants import NOVEL_FORMAT_LONG_WEBNOVEL
from models.novel import (
    Novel,
    PipelineConfigModel,
    PromptTemplate,
    WorkflowNodeDict,
)
from services import workflow_registry
from services.chapter_graph import (
    GRAPH_ROLES,
    SYSTEM_ROLES,
    default_graph,
    parse_graph,
    validate_graph,
)
from services.quality_metrics import dimensions_for
from services.workflow_nodes import (
    ROLE_LABELS,
    ROLE_PRIMARY_PROMPT,
    WorkflowNode,
    node_from_model,
    validate_node_payload,
)
from services.service_errors import ServiceError as HTTPException
from services.pipeline_stages import ALL_VERDICTS
from services.chapter_graph import (
    DEFAULT_BUDGETS,
    PAUSE_PREFIX,
    TARGET_DONE,
    TARGET_RETRY,
    VALID_ANCHORS,
)
from services.chapter_graph import (
    REQUIRED_ROLES,
    REQUIRED_VERDICT_HANDLERS,
    ROLE_AGENT,
)
from services.workflow_nodes import load_catalog

logger = logging.getLogger(__name__)

# 工作流名同时是 `Novel.novel_format` 的取值与提示词 category 的默认值，所以限制成
# 保守的 slug：不能有空格、大小写混用或标点，否则它会出现在 URL 路径与 JSON 键里。
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,49}$")
# 节点 id 额外允许点号，因为内置节点用 "<agent>.<role>" 的形式。
NODE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.]{2,63}$")

PROMPT_MODE_COPY = "copy"
PROMPT_MODE_SHARE = "share"

def _fail(detail: str, status: int = 400):
    raise HTTPException(status_code=status, detail=detail)

def _fail_all(errors: list[str], prefix: str):
    if errors:
        _fail(f"{prefix}：\n" + "\n".join(f"· {e}" for e in errors))

# ---------------------------------------------------------------------------
# 工作流
# ---------------------------------------------------------------------------

async def _get_workflow(db: AsyncSession, name: str) -> PipelineConfigModel:
    row = (
        await db.execute(
            select(PipelineConfigModel).where(PipelineConfigModel.name == name)
        )
    ).scalar_one_or_none()
    if row is None:
        _fail(f"工作流 '{name}' 不存在", status=404)
    return row

async def _project_count(db: AsyncSession, name: str) -> int:
    return (
        await db.execute(
            select(func.count(Novel.id)).where(Novel.novel_format == name)
        )
    ).scalar_one() or 0

def validate_graph_payload(raw: Any, *, catalog: dict[str, WorkflowNode]) -> list[str]:
    """校验图载荷。返回错误列表（空表示可用）。"""
    if raw is None:
        return []
    if not isinstance(raw, dict):
        return ["graph 必须是对象"]

    graph = parse_graph(raw)
    if graph is None:
        return ["graph 解析失败：至少要有一个带合法 role 的 steps 条目"]

    errors = validate_graph(graph)

    # 节点引用必须存在。运行时会静默回落到内置节点，但写入时要说清楚。
    for step in graph.steps.values():
        if step.node and step.node not in catalog:
            errors.append(f"步骤 {step.id!r} 引用了不存在的节点 {step.node!r}")
        elif step.node:
            node = catalog[step.node]
            if node.role != step.role:
                errors.append(
                    f"步骤 {step.id!r} 的角色是 {step.role!r}，但节点 {step.node!r} "
                    f"的角色是 {node.role!r} —— 角色决定跑哪段 Python，必须一致"
                )
    return errors

def validate_workflow_payload(
    payload: dict[str, Any],
    *,
    catalog: dict[str, WorkflowNode],
    existing: PipelineConfigModel | None = None,
) -> list[str]:
    errors: list[str] = []

    if "surface_strategy" in payload:
        strategy = payload["surface_strategy"]
        if strategy not in workflow_registry.ALL_STRATEGIES:
            errors.append(
                f"未知的表面策略 {strategy!r}；可用："
                f"{'、'.join(sorted(workflow_registry.ALL_STRATEGIES))}"
            )

    if "max_rewrite" in payload:
        try:
            if int(payload["max_rewrite"]) < 1:
                errors.append("max_rewrite 不得小于 1")
        except (TypeError, ValueError):
            errors.append("max_rewrite 必须是整数")

    if "policy" in payload and payload["policy"] is not None:
        if not isinstance(payload["policy"], dict):
            errors.append("policy 必须是对象")

    if "quality_dims" in payload:
        # 质量维度**不可自由设置**：Editor 的输出 schema 是固定的 pydantic 模型
        # （长篇七维 / 短篇七维），塞一个模型里没有的维度名，LLM 根本不会产出它，
        # 于是 quality_evaluation 永远 complete=false。接受一个静默无效的值比拒绝更糟。
        errors.append(
            "quality_dims 由表面策略派生，不能直接设置 —— Editor 的输出 schema 是"
            "固定的，自定义维度不会被 LLM 产出。请改 surface_strategy。"
        )

    if "graph" in payload:
        errors.extend(validate_graph_payload(payload["graph"], catalog=catalog))

    if existing is not None and existing.builtin:
        # 内置工作流可以改拓扑与开关（那是本次改造的目的），但不能改身份：
        # name 是 Novel.novel_format 的取值，surface_strategy 决定长篇是否仍冻结在 V43。
        if "surface_strategy" in payload and payload["surface_strategy"] != existing.surface_strategy:
            errors.append(
                f"内置工作流 '{existing.name}' 的表面策略不可修改 —— "
                f"长篇冻结在 A28/V43，短篇是一等生产工作流。要试新表面请克隆一个。"
            )

    return errors

async def list_workflow_nodes_map(db: AsyncSession) -> dict[str, WorkflowNode]:
    return await load_catalog(db)

async def create_workflow(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    """新建工作流，可从既有工作流克隆。

    `prompt_mode`：
      * `copy`（默认）—— 把来源的提示词整套复制到新 category，之后各改各的
      * `share` —— `prompt_category` 指向来源，只改拓扑与策略，提示词跟着来源变
    """
    name = str(payload.get("name") or "").strip()
    if not NAME_PATTERN.match(name):
        _fail(
            "工作流名必须是 3–50 个字符的小写字母/数字/下划线，且以字母开头"
            "（它同时是项目的 novel_format 与提示词分类）"
        )

    if (
        await db.execute(
            select(PipelineConfigModel.id).where(PipelineConfigModel.name == name)
        )
    ).scalar_one_or_none() is not None:
        _fail(f"工作流 '{name}' 已存在")

    prompt_mode = str(payload.get("prompt_mode") or PROMPT_MODE_COPY)
    if prompt_mode not in (PROMPT_MODE_COPY, PROMPT_MODE_SHARE):
        _fail(f"prompt_mode 只能是 {PROMPT_MODE_COPY} 或 {PROMPT_MODE_SHARE}")

    clone_from = payload.get("clone_from")
    source = await _get_workflow(db, str(clone_from)) if clone_from else None

    if source is not None:
        strategy = payload.get("surface_strategy") or source.surface_strategy
        row = PipelineConfigModel(
            name=name,
            name_zh=str(payload.get("name_zh") or f"{source.name_zh or source.name} 副本"),
            description=payload.get("description") or source.description,
            nodes=list(source.nodes or []),
            enable_living_docs_update=source.enable_living_docs_update,
            enable_editor_loop=source.enable_editor_loop,
            max_rewrite=source.max_rewrite,
            readonly_docs=list(source.readonly_docs or []),
            required_docs=list(source.required_docs or []),
            enable_force_correction=source.enable_force_correction,
            validation_before_editor=source.validation_before_editor,
            stages=source.stages,
            policy=dict(source.policy) if isinstance(source.policy, dict) else None,
            surface_strategy=strategy,
            graph=source.graph,
        )
    else:
        strategy = payload.get("surface_strategy") or workflow_registry.STRATEGY_FROZEN_V43
        row = PipelineConfigModel(
            name=name,
            name_zh=str(payload.get("name_zh") or name),
            description=payload.get("description"),
            nodes=["planner", "writer", "editor", "validator", "extractor"],
            enable_living_docs_update=True,
            enable_editor_loop=True,
            max_rewrite=2,
            readonly_docs=[],
            required_docs=[],
            enable_force_correction=True,
            validation_before_editor=False,
            stages=None,
            policy=None,
            surface_strategy=strategy,
            graph=None,
        )

    errors = validate_workflow_payload(
        {"surface_strategy": strategy, "graph": row.graph},
        catalog=await list_workflow_nodes_map(db),
    )
    _fail_all(errors, "工作流配置非法")

    # 质量维度由表面策略派生，不接受直接设置。
    row.quality_dims = list(dimensions_for_strategy(strategy))
    row.builtin = False

    # --- 提示词归属 ---
    copied = 0
    if source is None:
        # 从零新建：库里不存在以这个名字为 category 的提示词，留空或指向自己会让第一次
        # 生成就因为找不到模板而失败。必须指向一套已存在的提示词。
        requested = str(payload.get("prompt_category") or "").strip()
        row.prompt_category = requested or NOVEL_FORMAT_LONG_WEBNOVEL
        if not await _category_exists(db, row.prompt_category):
            _fail(
                f"提示词分类 '{row.prompt_category}' 下没有任何模板。"
                f"从零新建的工作流必须复用一套已有提示词 —— 或者改成从既有工作流克隆。"
            )
    elif prompt_mode == PROMPT_MODE_SHARE:
        # 共享来源的提示词：只改拓扑与策略，提示词跟着来源变。
        row.prompt_category = source.prompt_category or source.name
    else:
        # 独立一套：复制来源的全部模板到与工作流同名的新 category，之后各改各的。
        row.prompt_category = name
        copied = await _copy_prompts(db, source.prompt_category or source.name, name)
        if copied == 0:
            # 复制了 0 条 = 新工作流没有任何提示词，第一次生成就会在加载模板时失败。
            # 静默建出一个跑不动的工作流比直接拒绝更糟。
            _fail(
                f"来源工作流 '{source.name}' 的提示词分类 "
                f"'{source.prompt_category or source.name}' 下没有任何模板，无可复制。"
                f"改用「共享来源提示词」，或先给来源补齐模板。"
            )

    db.add(row)
    await db.commit()
    workflow_registry.remember(row)
    logger.info(
        "workflow_created name=%s clone_from=%s prompt_mode=%s prompts_copied=%d",
        name,
        clone_from,
        prompt_mode,
        copied,
    )
    return {
        "name": name,
        "prompt_category": row.prompt_category,
        "prompts_copied": copied,
    }

async def _category_exists(db: AsyncSession, category: str) -> bool:
    return (
        await db.execute(
            select(PromptTemplate.id).where(PromptTemplate.category == category).limit(1)
        )
    ).scalar_one_or_none() is not None

def dimensions_for_strategy(strategy: str) -> tuple[str, ...]:
    """该表面策略对应的质量维度。

    借道 `quality_metrics.dimensions_for` —— 它按格式轴解析，而策略与格式一一对应，
    所以这里用内置格式名反查，避免把维度表在两处各写一遍。
    """
    for fmt, mapped in workflow_registry.BUILTIN_STRATEGY.items():
        if mapped == strategy:
            return dimensions_for(fmt)
    return dimensions_for(None)

async def _copy_prompts(db: AsyncSession, source_category: str, target_category: str) -> int:
    rows = (
        await db.execute(
            select(PromptTemplate).where(PromptTemplate.category == source_category)
        )
    ).scalars().all()
    for row in rows:
        db.add(
            PromptTemplate(
                name=row.name,
                name_zh=row.name_zh,
                category=target_category,
                type=row.type,
                system_prompt=row.system_prompt,
                user_prompt_template=row.user_prompt_template,
                is_default=row.is_default,
            )
        )
    return len(rows)

async def delete_workflow(db: AsyncSession, name: str) -> dict[str, Any]:
    row = await _get_workflow(db, name)
    if row.builtin:
        _fail(
            f"'{name}' 是内置工作流，不能删除。长篇冻结在 A28/V43、短篇是一等生产"
            f"工作流，删掉任何一个都会让存量项目的生成任务查不到流程配置而失败。"
        )

    in_use = await _project_count(db, name)
    if in_use:
        _fail(
            f"还有 {in_use} 个项目在用工作流 '{name}'，不能删除 —— "
            f"删掉之后它们的生成任务会因为找不到流程配置而失败。"
            f"请先把这些项目切到别的工作流。"
        )

    own_prompts = 0
    if (row.prompt_category or row.name) == row.name:
        # 只删这个工作流自己那套提示词。share 模式指向别人的 category 时一行都不动。
        prompts = (
            await db.execute(
                select(PromptTemplate).where(PromptTemplate.category == row.name)
            )
        ).scalars().all()
        for prompt in prompts:
            await db.delete(prompt)
        own_prompts = len(prompts)

    await db.delete(row)
    await db.commit()
    workflow_registry.invalidate(name)
    logger.info("workflow_deleted name=%s prompts_deleted=%d", name, own_prompts)
    return {"name": name, "prompts_deleted": own_prompts}

# ---------------------------------------------------------------------------
# 节点库
# ---------------------------------------------------------------------------

async def list_nodes(db: AsyncSession) -> list[dict[str, Any]]:
    catalog = await list_workflow_nodes_map(db)
    return [node.to_dict() for node in catalog.values()]

async def create_node(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    node_id = str(payload.get("id") or "").strip()
    if not NODE_ID_PATTERN.match(node_id):
        _fail("节点 id 必须是 3–64 个字符的小写字母/数字/下划线/点，且以字母开头")

    if (
        await db.execute(select(WorkflowNodeDict.id).where(WorkflowNodeDict.id == node_id))
    ).scalar_one_or_none() is not None:
        _fail(f"节点 '{node_id}' 已存在")

    _fail_all(validate_node_payload(payload), "节点配置非法")

    row = WorkflowNodeDict(
        id=node_id,
        name_zh=str(payload["name_zh"]).strip(),
        role=str(payload["role"]),
        prompt_name=(payload.get("prompt_name") or None),
        options=payload.get("options") or None,
        description=payload.get("description") or None,
        builtin=False,
    )
    db.add(row)
    await db.commit()
    return node_from_model(row).to_dict()

async def update_node(
    db: AsyncSession, node_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    row = (
        await db.execute(select(WorkflowNodeDict).where(WorkflowNodeDict.id == node_id))
    ).scalar_one_or_none()
    if row is None:
        _fail(f"节点 '{node_id}' 不存在", status=404)

    existing = node_from_model(row)
    errors = validate_node_payload(payload, existing=existing)

    if existing.builtin and payload.get("prompt_name") not in (None, existing.prompt_name):
        # 改内置节点的提示词会影响**所有**引用它的工作流，包括冻结在 A28/V43 的长篇。
        errors.append(
            f"内置节点 '{node_id}' 的提示词不可改 —— 它被所有工作流共用，改了会连带"
            f"改掉冻结在 A28/V43 的长篇。请新建一个自定义节点并在工作流拓扑里替换。"
        )

    _fail_all(errors, "节点配置非法")

    for field in ("name_zh", "prompt_name", "options", "description"):
        if field in payload:
            setattr(row, field, payload[field] or None)
    if "role" in payload and not existing.builtin:
        row.role = payload["role"]
    await db.commit()
    return node_from_model(row).to_dict()

async def delete_node(db: AsyncSession, node_id: str) -> dict[str, Any]:
    row = (
        await db.execute(select(WorkflowNodeDict).where(WorkflowNodeDict.id == node_id))
    ).scalar_one_or_none()
    if row is None:
        _fail(f"节点 '{node_id}' 不存在", status=404)
    if row.builtin:
        _fail(f"'{node_id}' 是内置节点，不能删除")

    users = await _workflows_using_node(db, node_id)
    if users:
        _fail(
            f"节点 '{node_id}' 还被这些工作流的拓扑引用：{'、'.join(users)}。"
            f"请先在那些工作流里把对应步骤换成别的节点。"
        )

    await db.delete(row)
    await db.commit()
    return {"id": node_id}

async def _workflows_using_node(db: AsyncSession, node_id: str) -> list[str]:
    rows = (await db.execute(select(PipelineConfigModel))).scalars().all()
    users: list[str] = []
    for row in rows:
        graph = parse_graph(getattr(row, "graph", None))
        if graph is None:
            continue
        if any(step.node == node_id for step in graph.steps.values()):
            users.append(row.name)
    return users

# ---------------------------------------------------------------------------
# 角色词表（供前端渲染拓扑编辑器）
# ---------------------------------------------------------------------------

def list_roles() -> list[dict[str, Any]]:
    """角色词表。前端据此渲染步骤下拉与说明，不在前端重写一份。"""
    roles: list[dict[str, Any]] = []
    for role in ROLE_AGENT:
        label, description = ROLE_LABELS.get(role, (role, ""))
        roles.append(
            {
                "role": role,
                "label": label,
                "description": description,
                "agent": ROLE_AGENT.get(role),
                "is_system": role in SYSTEM_ROLES,
                "required": role in REQUIRED_ROLES,
                "primary_prompt": ROLE_PRIMARY_PROMPT.get(role),
                "must_handle": sorted(REQUIRED_VERDICT_HANDLERS.get(role, ())),
            }
        )
    return roles

def default_graph_json(
    *,
    has_editor: bool = True,
    has_style_repair: bool = True,
    validation_before_editor: bool = False,
) -> dict[str, Any]:
    """默认拓扑的 JSON。前端「重置为默认」与新建工作流时用。"""
    return default_graph(
        has_editor=has_editor,
        has_style_repair=has_style_repair,
        validation_before_editor=validation_before_editor,
    ).to_dict()

def graph_vocabulary() -> dict[str, Any]:
    """图编辑器需要的全部词表：角色、裁决、特殊目标、预算。"""
    return {
        "roles": list_roles(),
        "verdicts": sorted(ALL_VERDICTS),
        "special_targets": [TARGET_DONE, TARGET_RETRY]
        + [f"{PAUSE_PREFIX}{anchor}" for anchor in sorted(VALID_ANCHORS)],
        "budgets": {name: budget.to_dict() for name, budget in DEFAULT_BUDGETS.items()},
        "graph_roles": sorted(GRAPH_ROLES),
        "system_roles": sorted(SYSTEM_ROLES),
    }
