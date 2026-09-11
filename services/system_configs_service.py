"""系统配置（Pipeline / Prompt 模板 / 可用节点与文档）CRUD 服务层。

将原本散落在 routers/system_configs.py 中的直接 ORM 访问集中到此处，
router 层仅做请求/响应转换与 service 调用。
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.prompt_templates import invalidate_prompt_cache
from models.novel import (
    PipelineConfigModel,
    PromptTemplate,
    SystemNodeDict,
)
from services.service_errors import ServiceError as HTTPException


# ---------------------------------------------------------------------------
# PipelineConfig CRUD
# ---------------------------------------------------------------------------

PIPELINE_CONFIG_FIELDS = (
    "name_zh",
    "description",
    "nodes",
    "enable_editor_loop",
    "max_rewrite",
    "enable_force_correction",
    "validation_before_editor",
    "stages",
    # 拓扑图是执行权威（见 services/chapter_graph）。
    "graph",
    "policy",
    "surface_strategy",
    "prompt_category",
)


def _validate_pipeline_update(update_data: dict[str, Any]) -> dict[str, Any]:
    """对工作流写入做语义校验。

    这个端点原先零校验：``nodes`` 是无类型 ``List[str]``、``max_rewrite`` 无下界，
    一条坏数据就能让 ``get_pipeline_config`` 之后的生成任务在 worker 里炸掉。
    工作流可从前端编辑之后，这里必须挡住明显非法的输入。

    图的校验（环守卫、悬空目标、必需角色与裁决）在 ``services/chapter_graph`` 里，
    节点引用与身份护栏在 ``services/workflow_admin_service`` 里 —— 那些需要库里的
    节点库与工作流行，所以走 ``update_pipeline_config`` 的异步路径。
    """
    from services.pipeline_stages import (
        CANONICAL_AGENT_ORDER,
        StagePlan,
        normalize_stages,
        parse_stages,
    )

    cleaned = dict(update_data)

    if "max_rewrite" in cleaned:
        try:
            value = int(cleaned["max_rewrite"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="max_rewrite 必须是整数")
        if value < 1:
            raise HTTPException(status_code=400, detail="max_rewrite 不得小于 1")
        cleaned["max_rewrite"] = value

    if "nodes" in cleaned:
        nodes = cleaned["nodes"]
        if not isinstance(nodes, list) or not all(isinstance(n, str) for n in nodes):
            raise HTTPException(status_code=400, detail="nodes 必须是字符串数组")
        unknown = [n for n in nodes if n not in CANONICAL_AGENT_ORDER]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"nodes 含未知节点: {', '.join(unknown)}",
            )

    if "stages" in cleaned and cleaned["stages"] is not None:
        raw = cleaned["stages"]
        if not isinstance(raw, list):
            raise HTTPException(status_code=400, detail="stages 必须是数组")
        parsed = parse_stages(raw)
        if raw and not parsed:
            raise HTTPException(
                status_code=400,
                detail="stages 中没有任何合法的 (agent, role) 组合",
            )
        # 归一化后回写，保证补齐必需阶段、剔除依赖不满足的阶段。
        plan = StagePlan.from_stages(normalize_stages(parsed))
        cleaned["stages"] = plan.to_json()

    return cleaned


def _pipeline_config_to_dict(c: PipelineConfigModel) -> dict[str, Any]:
    from services.chapter_graph import graph_for_config
    from services.pipeline_stages import StagePlan, stages_for_config

    plan = StagePlan.from_stages(
        stages_for_config(
            getattr(c, "stages", None),
            c.nodes,
            validation_before_editor=bool(c.validation_before_editor),
        )
    )
    stored_graph = getattr(c, "graph", None)
    return {
        "id": str(c.id),
        "name": c.name,
        "name_zh": c.name_zh,
        "description": getattr(c, "description", None),
        "nodes": c.nodes,
        "enable_editor_loop": c.enable_editor_loop,
        "max_rewrite": c.max_rewrite,
        "enable_force_correction": c.enable_force_correction,
        "validation_before_editor": c.validation_before_editor,
        "stages": getattr(c, "stages", None),
        "policy": getattr(c, "policy", None),
        "surface_strategy": getattr(c, "surface_strategy", None),
        "prompt_category": getattr(c, "prompt_category", None) or c.name,
        "quality_dims": getattr(c, "quality_dims", None),
        "builtin": bool(getattr(c, "builtin", False)),
        # 前端编辑的是**生效的图**：graph 列为空时给出由开关派生的默认图，于是
        # 「打开就能改」而不是先看到一张空白画布再自己猜默认拓扑长什么样。
        "graph": graph_for_config(
            stored_graph,
            has_editor=plan.has_editor,
            has_style_repair=plan.has_style_repair,
            validation_before_editor=plan.validation_before_editor,
            label=c.name,
        ).to_dict(),
        # 区分「用的是默认图」与「用户手写过图」—— 界面上要能显示「已自定义」。
        "graph_is_custom": bool(stored_graph),
    }


async def list_pipeline_configs(db: AsyncSession) -> list[dict[str, Any]]:
    result = await db.execute(select(PipelineConfigModel))
    configs = result.scalars().all()
    return [_pipeline_config_to_dict(c) for c in configs]


async def update_pipeline_config(
    db: AsyncSession, name: str, update_data: dict[str, Any]
) -> None:
    result = await db.execute(
        select(PipelineConfigModel).where(PipelineConfigModel.name == name)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(
            status_code=404, detail=f"Pipeline config '{name}' not found"
        )
    cleaned = _validate_pipeline_update(update_data)

    # 图与身份护栏需要库里的节点库和当前行，所以放在异步路径上。
    from services import workflow_registry
    from services.workflow_admin_service import (
        list_workflow_nodes_map,
        validate_workflow_payload,
    )

    errors = validate_workflow_payload(
        cleaned, catalog=await list_workflow_nodes_map(db), existing=config
    )
    if errors:
        raise HTTPException(
            status_code=400,
            detail="工作流配置非法：\n" + "\n".join(f"· {e}" for e in errors),
        )

    for key, value in cleaned.items():
        if key in PIPELINE_CONFIG_FIELDS:
            setattr(config, key, value)
    await db.commit()
    # 表面策略/提示词分类可能变了，进程内缓存必须跟着更新，否则同进程的内嵌 worker
    # 会继续按旧策略组装提示词。
    workflow_registry.remember(config)


# ---------------------------------------------------------------------------
# PromptTemplate CRUD
# ---------------------------------------------------------------------------

PROMPT_FIELDS = ("system_prompt", "user_prompt_template")


def _prompt_to_dict(p: PromptTemplate) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "name": p.name,
        "name_zh": p.name_zh,
        "category": p.category,
        "type": p.type,
        "system_prompt": p.system_prompt,
        "user_prompt_template": p.user_prompt_template,
        "is_default": p.is_default,
    }


async def list_prompt_templates(
    db: AsyncSession, category: Optional[str] = None
) -> list[dict[str, Any]]:
    stmt = select(PromptTemplate)
    if category:
        stmt = stmt.where(PromptTemplate.category == category)
    result = await db.execute(stmt)
    prompts = result.scalars().all()
    return [_prompt_to_dict(p) for p in prompts]


async def update_prompt_template(
    db: AsyncSession, prompt_id: str, update_data: dict[str, Any]
) -> None:
    try:
        pid = uuid.UUID(prompt_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid UUID") from exc

    result = await db.execute(select(PromptTemplate).where(PromptTemplate.id == pid))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    for key, value in update_data.items():
        if key in PROMPT_FIELDS:
            setattr(prompt, key, value)
    await db.commit()
    # 本进程缓存立即失效;其他进程(独立 worker)由表版本戳在下一个 agent
    # 步骤感知变更,无需重启。TTL 300s 只在版本戳查询不可用时兜底。
    invalidate_prompt_cache(prompt.name, prompt.category)


async def create_prompt_template(
    db: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """新建一条提示词。

    自定义节点靠 ``prompt_name`` 指向一条提示词 —— 没有这个端点，节点指定的名字就
    无处创建，「自定义节点」也就只是个空壳。
    """
    name = str(payload.get("name") or "").strip()
    category = str(payload.get("category") or "").strip()
    if not name or not category:
        raise HTTPException(status_code=400, detail="name 与 category 都必填")
    if not re.match(r"^[a-z][a-z0-9_]{2,99}$", name):
        raise HTTPException(
            status_code=400,
            detail="提示词 name 必须是 3–100 个小写字母/数字/下划线，且以字母开头",
        )

    existing = (
        await db.execute(
            select(PromptTemplate.id).where(
                PromptTemplate.name == name, PromptTemplate.category == category
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=400, detail=f"分类 '{category}' 下已有名为 '{name}' 的提示词"
        )

    row = PromptTemplate(
        name=name,
        name_zh=payload.get("name_zh") or name,
        category=category,
        type=payload.get("type") or "writing",
        system_prompt=payload.get("system_prompt") or "",
        user_prompt_template=payload.get("user_prompt_template") or "",
        is_default=1,
    )
    db.add(row)
    await db.commit()
    return _prompt_to_dict(row)


async def delete_prompt_template(db: AsyncSession, prompt_id: str) -> dict[str, Any]:
    try:
        pid = uuid.UUID(prompt_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid UUID") from exc

    prompt = (
        await db.execute(select(PromptTemplate).where(PromptTemplate.id == pid))
    ).scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    # 流水线必需的模板不能删：`load_prompt_template` 查不到会直接抛，那一章的生成
    # 当场失败。REQUIRED_PROMPT_TEMPLATES 是启动时校验用的同一张清单。
    from services.prompt_loader import REQUIRED_PROMPT_TEMPLATES

    if (prompt.name, prompt.category) in set(REQUIRED_PROMPT_TEMPLATES):
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{prompt.name}' 是分类 '{prompt.category}' 的必需模板，删掉之后该"
                f"工作流的生成任务会在加载提示词时直接失败。可以清空内容但不能删除。"
            ),
        )

    # 被自定义节点引用的提示词同样不能删 —— 那些节点会静默回落到内置提示词，
    # 用户以为自己的润色节点在生效，实际上跑的是别的提示词。
    from models.novel import WorkflowNodeDict

    referencing = (
        await db.execute(
            select(WorkflowNodeDict.id).where(WorkflowNodeDict.prompt_name == prompt.name)
        )
    ).scalars().all()
    if referencing:
        raise HTTPException(
            status_code=400,
            detail=(
                f"提示词 '{prompt.name}' 还被这些节点引用：{'、'.join(referencing)}。"
                f"请先改掉那些节点的提示词。"
            ),
        )

    name, category = prompt.name, prompt.category
    await db.delete(prompt)
    await db.commit()
    invalidate_prompt_cache(name, category)
    return {"id": prompt_id, "name": name, "category": category}


# ---------------------------------------------------------------------------
# Available nodes dictionary
# ---------------------------------------------------------------------------

async def list_available_nodes(db: AsyncSession) -> list[dict[str, str]]:
    result = await db.execute(select(SystemNodeDict))
    nodes = result.scalars().all()
    return [{"id": n.id, "label": n.name_zh} for n in nodes]
