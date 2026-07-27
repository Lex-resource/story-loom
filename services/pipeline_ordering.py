"""Pipeline ordering and scoped runtime order state."""
from __future__ import annotations

import contextlib
import contextvars
from typing import Iterator, Optional

from agents.constants import (
    AGENT_EDITOR,
    AGENT_EXTRACTOR,
    AGENT_PLANNER,
    AGENT_VALIDATOR,
    AGENT_WRITER,
)


def pipeline_order_from_nodes(nodes: list[str], pipeline_step_cls) -> list:
    """Derive a PipelineStep ordering from a PipelineConfig.nodes list."""
    job_step_to_pipeline_step = {
        AGENT_PLANNER: pipeline_step_cls.OUTLINE,
        AGENT_WRITER: pipeline_step_cls.WRITING,
        AGENT_EDITOR: pipeline_step_cls.EDITING,
        AGENT_VALIDATOR: pipeline_step_cls.VALIDATING,
        AGENT_EXTRACTOR: pipeline_step_cls.EXTRACTING,
    }
    order = []
    for node_name in nodes:
        step = job_step_to_pipeline_step.get(node_name)
        if step is None:
            print(
                f"[pipeline_state WARN] node '{node_name}' has no PipelineStep mapping; skipping in pipeline_order"
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
