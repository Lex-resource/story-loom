"""Token-usage accounting service.

Separated from services/issue_service.py to keep that module focused on
issue management (raw issues + issue summaries). This module owns the
cost / token-usage aggregation pipeline: per-model price tables, per-row
cost computation, and multi-dimensional aggregation (model / agent /
chapter).

The single public endpoint is `get_token_stats`, which is wired to
GET /{project_id}/token-stats via routers/issues.py.
"""

import uuid
from typing import Optional

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.novel import TokenUsage
from agents.constants import AGENT_WRITER, AGENT_EDITOR, AGENT_VALIDATOR
from services.vector_constants import (
    AGENT_NAME_EMBEDDING,
    ALL_MODELS_LABEL,
    TOKENS_PER_MILLION,
)


def _build_price_table(settings_dict: dict) -> dict[str, dict[str, float]]:
    """从 settings providers 构建每模型的输入/输出/缓存命中单价表。"""
    price_table: dict[str, dict[str, float]] = {}
    for p in settings_dict.get("providers", []):
        mname = p.get("model") or ""
        if not mname:
            continue
        price_table[mname] = {
            "input_price": float(p.get("input_price", 0) or 0),
            "output_price": float(p.get("output_price", 0) or 0),
            "cache_hit_price": float(p.get("cache_hit_price", 0) or 0),
        }
    return price_table


def _compute_usage_cost(u: TokenUsage, price_table: dict[str, dict[str, float]]) -> float:
    """计算单条 TokenUsage 记录的成本（缓存命中部分按 cache_hit_price，其余按 input_price）。"""
    price = price_table.get(u.model_name or "", {})
    input_price = price.get("input_price", 0.0)
    output_price = price.get("output_price", 0.0)
    cache_hit_price = price.get("cache_hit_price", 0.0)
    chargeable_input = max(u.input_tokens - u.cache_hit_tokens, 0)
    return (
        chargeable_input * input_price
        + u.cache_hit_tokens * cache_hit_price
        + u.output_tokens * output_price
    ) / TOKENS_PER_MILLION


def _aggregate_usage(
    usages: list[TokenUsage], price_table: dict[str, dict[str, float]]
) -> dict:
    """聚合所有 TokenUsage 记录，返回总体 + 模型/agent/章节维度统计。"""
    total_input = total_output = total_hit = total_miss = total_embedding = 0
    total_cost = 0.0
    model_stats: dict[str, dict] = {}
    agent_stats: dict[str, dict] = {}
    chapter_stats: dict[int, dict] = {}

    def _ensure_model_stat(name: str):
        return model_stats.setdefault(name, {
            "model_name": name, "input_tokens": 0, "output_tokens": 0,
            "cache_hit_tokens": 0, "cost": 0.0,
        })

    def _ensure_agent_stat(name: str):
        return agent_stats.setdefault(name, {
            "agent_name": name, "input_tokens": 0, "output_tokens": 0, "cost": 0.0,
        })

    def _ensure_chapter_stat(idx: int):
        return chapter_stats.setdefault(idx, {
            "chapter_index": idx, "cost": 0.0,
            "writer_cost": 0.0, "editor_cost": 0.0, "validator_cost": 0.0,
        })

    for u in usages:
        mname = u.model_name or "unknown"
        m_lower = mname.lower()
        is_embedding = u.agent_name == AGENT_NAME_EMBEDDING or AGENT_NAME_EMBEDDING in m_lower

        if is_embedding:
            total_embedding += u.input_tokens
            continue

        total_input += u.input_tokens
        total_output += u.output_tokens
        total_hit += u.cache_hit_tokens
        total_miss += u.cache_miss_tokens

        cost = _compute_usage_cost(u, price_table)
        total_cost += cost

        ms = _ensure_model_stat(mname)
        ms["input_tokens"] += u.input_tokens
        ms["output_tokens"] += u.output_tokens
        ms["cache_hit_tokens"] += u.cache_hit_tokens
        ms["cost"] += cost

        ag_name = u.agent_name or "unknown"
        ag = _ensure_agent_stat(ag_name)
        ag["input_tokens"] += u.input_tokens
        ag["output_tokens"] += u.output_tokens
        ag["cost"] += cost

        ch = _ensure_chapter_stat(u.chapter_index if u.chapter_index is not None else 0)
        ch["cost"] += cost
        if ag_name == AGENT_WRITER:
            ch["writer_cost"] += cost
        elif ag_name == AGENT_EDITOR:
            ch["editor_cost"] += cost
        elif ag_name == AGENT_VALIDATOR:
            ch["validator_cost"] += cost

    return {
        "total_input": total_input,
        "total_output": total_output,
        "total_hit": total_hit,
        "total_miss": total_miss,
        "total_embedding": total_embedding,
        "total_cost": total_cost,
        "model_stats": model_stats,
        "agent_stats": agent_stats,
        "chapter_stats": chapter_stats,
    }


async def get_token_stats(project_id: str, model: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    pid = uuid.UUID(project_id)
    from services.project_service import get_novel_or_404
    await get_novel_or_404(db, project_id)

    # 1. Build per-model price table from settings providers
    from services.settings_store import load_settings
    settings_dict = await load_settings(db)
    price_table = _build_price_table(settings_dict)

    # 2. Fetch token usage records (optionally filtered by model)
    query = select(TokenUsage).where(TokenUsage.project_id == pid)
    if model and model != ALL_MODELS_LABEL:
        query = query.where(TokenUsage.model_name == model)
    query = query.order_by(TokenUsage.chapter_index.asc(), TokenUsage.created_at.asc())
    usages = (await db.execute(query)).scalars().all()

    # 3. Aggregate
    agg = _aggregate_usage(usages, price_table)

    # 4. Assemble response
    cache_total = agg["total_hit"] + agg["total_miss"]
    cache_hit_ratio = (agg["total_hit"] / cache_total) if cache_total > 0 else 0.0

    return {
        "total_cost": agg["total_cost"],
        "total_input_tokens": agg["total_input"],
        "total_output_tokens": agg["total_output"],
        "total_embedding_tokens": agg["total_embedding"],
        "cache_hit_ratio": cache_hit_ratio,
        "model_stats": list(agg["model_stats"].values()),
        "agent_stats": list(agg["agent_stats"].values()),
        "chapter_stats": sorted(agg["chapter_stats"].values(), key=lambda c: c["chapter_index"]),
    }
