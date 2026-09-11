"""Pipeline ordering and scoped runtime order state."""
from __future__ import annotations

import contextlib
import contextvars
import logging
from typing import Iterator, Optional

logger = logging.getLogger(__name__)


def pipeline_order_from_nodes(nodes: list[str], pipeline_step_cls) -> list:
    """Derive a PipelineStep ordering from a PipelineConfig.nodes list.

    映射表的唯一来源是 ``services.pipeline_types.JOB_STEP_TO_PIPELINE_STEP``。
    这里曾经内联过一份同样内容的副本，改一处漏一处会让新节点静默地从顺序里消失，
    而且只打印一行警告 —— 工作流模块化之后节点集合会变得可配置，这个陷阱必须先拆掉。

    ``pipeline_step_cls`` 仍作为参数传入（而不是直接 import），是为了保持既有调用
    约定并避免在低层状态模块里于导入期加载 pipeline 配置。
    """
    from services.pipeline_types import JOB_STEP_TO_PIPELINE_STEP

    order = []
    for node_name in nodes:
        step = JOB_STEP_TO_PIPELINE_STEP.get(node_name)
        if step is None:
            logger.warning(
                "node '%s' has no PipelineStep mapping; skipping in pipeline_order",
                node_name,
            )
            continue
        if step not in order:
            order.append(step)
    if pipeline_step_cls.PUBLISHED not in order:
        order.append(pipeline_step_cls.PUBLISHED)
    return order


_current_pipeline_order: contextvars.ContextVar[Optional[list]] = (
    contextvars.ContextVar("_current_pipeline_order", default=None)
)


def get_pipeline_order() -> Optional[list]:
    return _current_pipeline_order.get()


def set_pipeline_order(order: Optional[list]):
    return _current_pipeline_order.set(order)


@contextlib.contextmanager
def pipeline_order_scope(order: Optional[list]) -> Iterator[None]:
    token = _current_pipeline_order.set(order)
    try:
        yield
    finally:
        _current_pipeline_order.reset(token)
