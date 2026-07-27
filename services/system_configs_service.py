"""系统配置（Pipeline / Prompt 模板 / 可用节点与文档）CRUD 服务层。

将原本散落在 routers/system_configs.py 中的直接 ORM 访问集中到此处，
router 层仅做请求/响应转换与 service 调用。
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel import (
    PipelineConfigModel,
    PromptTemplate,
    SystemDocTypeDict,
    SystemNodeDict,
)


# ---------------------------------------------------------------------------
# PipelineConfig CRUD
# ---------------------------------------------------------------------------

PIPELINE_CONFIG_FIELDS = (
    "name_zh",
    "nodes",
    "enable_living_docs_update",
    "enable_editor_loop",
    "max_rewrite",
    "readonly_docs",
    "required_docs",
    "enable_force_correction",
    "validation_before_editor",
)


def _pipeline_config_to_dict(c: PipelineConfigModel) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "name": c.name,
        "name_zh": c.name_zh,
        "nodes": c.nodes,
        "enable_living_docs_update": c.enable_living_docs_update,
        "enable_editor_loop": c.enable_editor_loop,
        "max_rewrite": c.max_rewrite,
        "readonly_docs": c.readonly_docs,
        "required_docs": c.required_docs,
        "enable_force_correction": c.enable_force_correction,
        "validation_before_editor": c.validation_before_editor,
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
    for key, value in update_data.items():
        if key in PIPELINE_CONFIG_FIELDS:
            setattr(config, key, value)
    await db.commit()


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


# ---------------------------------------------------------------------------
# Available nodes / docs dictionaries
# ---------------------------------------------------------------------------

async def list_available_nodes(db: AsyncSession) -> list[dict[str, str]]:
    result = await db.execute(select(SystemNodeDict))
    nodes = result.scalars().all()
    return [{"id": n.id, "label": n.name_zh} for n in nodes]


async def list_available_docs(db: AsyncSession) -> list[dict[str, str]]:
    result = await db.execute(select(SystemDocTypeDict))
    docs = result.scalars().all()
    return [{"id": d.id, "label": d.name_zh} for d in docs]
