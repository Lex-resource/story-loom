"""工作流记录的进程内缓存。

`services/workflow_surface.strategy_for()` 在提示词组装的**同步热路径**上被调用，
没有 AsyncSession 也不该有 I/O。但表面策略的权威来源是
`pipeline_configs.surface_strategy` —— 否则从短篇克隆出来的自定义工作流会拿到短篇
提示词却走长篇的 schema、没有全文审校、按长篇合并记忆（静默错误，最难查的一类）。

解法是进程内缓存 + 静态兜底：

* 缓存由 `get_pipeline_config` 顺手填充（它每章生成都要读那一行，**零额外查询**），
  以及 API 写入后 / 进程启动时的 `refresh`。
* 缓存冷时回落到两个内置工作流的静态映射 —— 于是长篇与短篇即使缓存是空的也完全正确，
  生产行为不依赖缓存是否已预热。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agents.constants import NOVEL_FORMAT_LONG_WEBNOVEL, NOVEL_FORMAT_ZHIHU_SHORT

logger = logging.getLogger(__name__)

STRATEGY_FROZEN_V43 = "frozen_v43"
STRATEGY_SHORT_FORM = "short_form"
STRATEGY_CUSTOM = "custom"

ALL_STRATEGIES: frozenset[str] = frozenset(
    {STRATEGY_FROZEN_V43, STRATEGY_SHORT_FORM, STRATEGY_CUSTOM}
)

# 两个内置工作流的静态兜底。缓存未预热、或部署时 DB 暂时读不到时使用。
# 生产冻结在 A28/V43 的只有长篇（见 docs/research/novel-memory-continuity/PRODUCTION.md）。
BUILTIN_STRATEGY: dict[str, str] = {
    NOVEL_FORMAT_LONG_WEBNOVEL: STRATEGY_FROZEN_V43,
    NOVEL_FORMAT_ZHIHU_SHORT: STRATEGY_SHORT_FORM,
}

BUILTIN_WORKFLOWS: frozenset[str] = frozenset(BUILTIN_STRATEGY)


@dataclass(frozen=True)
class WorkflowRecord:
    """一个工作流的「表面身份」。

    只装**同步热路径**要用的那一项：`surface_strategy`。`prompt_category` 与
    `quality_dims` 也存进来是为了让 `snapshot()` 在排障时能一眼看全，但生产读取它们
    走的是 `PipelineConfig`（拿着 session 的异步路径）—— 缓存不做第二条读取路径，
    否则两条路径迟早给出不同答案。
    """

    name: str
    surface_strategy: str
    prompt_category: str
    quality_dims: tuple[str, ...] | None = None
    builtin: bool = False


_records: dict[str, WorkflowRecord] = {}


def _record_from_model(model: Any) -> WorkflowRecord:
    name = str(model.name)
    strategy = getattr(model, "surface_strategy", None) or BUILTIN_STRATEGY.get(
        name, STRATEGY_FROZEN_V43
    )
    if strategy not in ALL_STRATEGIES:
        logger.warning(
            "workflow_unknown_surface_strategy workflow=%s strategy=%s falling_back=%s",
            name,
            strategy,
            STRATEGY_FROZEN_V43,
        )
        strategy = STRATEGY_FROZEN_V43
    dims = getattr(model, "quality_dims", None)
    return WorkflowRecord(
        name=name,
        surface_strategy=strategy,
        # 为空时用 name：自定义工作流不填就自带一套同名 category，
        # 填了就是「复用别人的提示词」。
        prompt_category=str(getattr(model, "prompt_category", None) or name),
        quality_dims=tuple(str(d) for d in dims) if isinstance(dims, list) and dims else None,
        builtin=bool(getattr(model, "builtin", False)),
    )


def remember(model: Any) -> WorkflowRecord:
    """用一行已经读到的 `PipelineConfigModel` 填缓存。零额外查询。"""
    record = _record_from_model(model)
    _records[record.name] = record
    return record


def strategy_for(novel_format: str | None) -> str:
    """该工作流的表面策略。未知工作流按长篇冻结点处理（保守，不擅自改表面）。"""
    key = str(novel_format or "")
    record = _records.get(key)
    if record is not None:
        return record.surface_strategy
    return BUILTIN_STRATEGY.get(key, STRATEGY_FROZEN_V43)


def invalidate(novel_format: str | None = None) -> None:
    if novel_format is None:
        _records.clear()
    else:
        _records.pop(str(novel_format), None)


def snapshot() -> dict[str, WorkflowRecord]:
    """缓存内容的拷贝。供测试与诊断。"""
    return dict(_records)


async def refresh(db) -> int:
    """从数据库整体刷新缓存。进程启动与 API 写入后调用。

    读不到就保持原样并记一条 warning —— 静态兜底已经覆盖两个内置工作流，
    没有理由让节点库/工作流表成为启动的单点故障。
    """
    from sqlalchemy import select

    from models.novel import PipelineConfigModel

    try:
        rows = (await db.execute(select(PipelineConfigModel))).scalars().all()
    except Exception:
        logger.exception("workflow_registry_refresh_failed")
        return 0

    _records.clear()
    for row in rows:
        remember(row)
    return len(_records)
