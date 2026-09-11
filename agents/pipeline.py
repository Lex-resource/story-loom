from __future__ import annotations

import copy
from typing import Any, Iterable, Type

from agents.constants import AGENT_PLANNER, AGENT_WRITER, AGENT_EDITOR, AGENT_VALIDATOR, AGENT_EXTRACTOR, get_default_agent
from agents.agent_io import EditorOutput, ExtractorOutput, PlannerOutput, ValidatorOutput, WriterOutput
from agents.pipeline_context import PipelineContext
from agents.pipeline_payload import bind_payload_fields, bind_truthy_payload_fields
from services.context_compaction import memory_context_breakdown


class NodeExecutionError(Exception):
    """Wraps an exception raised inside a PipelineNode so the caller knows
    *which* node failed. The original exception is available on ``original``.

    LLMJSONParsingError is NOT wrapped (callers handle it specifically for
    raw-response storage and audit-failed transitions).
    """

    def __init__(self, node_name: str, original: Exception):
        self.node_name = node_name
        self.original = original
        super().__init__(f"[Node:{node_name}] {type(original).__name__}: {original}")


# ---------------------------------------------------------------------------
# Node registry
# ---------------------------------------------------------------------------
#
# Historically this module hard-coded 5 node subclasses and callers had to
# import them by name (PlannerNode, WriterNode, ...). Adding a new node type
# required touching every call site that enumerates nodes.
#
# The registry decouples "what nodes exist" from "how to look one up":
#   * New nodes register themselves via the ``@register_node`` decorator.
#   * Callers resolve a node by its ``name`` string (which matches the
#     PipelineConfig.nodes list and the AGENT_* constants) via ``get_node``.
#
# The 5 built-in nodes are still defined below and registered at import
# time, so existing code that imports them directly continues to work.

NODE_REGISTRY: dict[str, Type["PipelineNode"]] = {}


def register_node(cls: Type["PipelineNode"]) -> Type["PipelineNode"]:
    """Class decorator that registers a PipelineNode subclass under its
    ``name`` attribute in NODE_REGISTRY.

    Re-registering the same name overwrites the previous entry (useful in
    tests that substitute a fake node). Re-registering a *different* class
    under an already-occupied name raises ValueError to catch accidental
    collisions early.
    """
    name = getattr(cls, "name", None)
    if not name:
        raise ValueError(f"PipelineNode subclass {cls.__name__} must define a non-empty 'name' attribute")
    existing = NODE_REGISTRY.get(name)
    if existing is not None and existing is not cls:
        raise ValueError(
            f"Node name '{name}' is already registered by {existing.__name__}; "
            f"cannot also register {cls.__name__}"
        )
    NODE_REGISTRY[name] = cls
    return cls


def get_node(name: str) -> Type["PipelineNode"]:
    """Look up a registered PipelineNode subclass by its name.

    Raises KeyError with a helpful message listing the known names when the
    requested name is not registered.
    """
    try:
        return NODE_REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(NODE_REGISTRY)) or "<none>"
        raise KeyError(
            f"Unknown pipeline node '{name}'. Registered nodes: {known}"
        ) from None


def iter_registered_nodes() -> Iterable[str]:
    """Return an iterator over all registered node names."""
    return iter(NODE_REGISTRY)


def make_node(name: str, **kwargs: Any) -> "PipelineNode":
    """Instantiate a registered PipelineNode by name.

    Convenience wrapper around ``get_node(name)(**kwargs)`` for callers that
    need an instance rather than the class.
    """
    return get_node(name)(**kwargs)




class PipelineNode:
    name: str

    @staticmethod
    def _bind_memory_metrics(context: PipelineContext, agent: Any) -> None:
        """Expose rendered memory size to the local experiment recorder."""
        breakdown = memory_context_breakdown(context)
        agent.last_memory_context_breakdown = breakdown
        agent.last_memory_context_chars = sum(breakdown.values())

    async def run(self, context: PipelineContext, payload: dict[str, Any]) -> Any:
        raise NotImplementedError

    async def execute(self, context: PipelineContext, payload: dict[str, Any]) -> Any:
        """Run this node, wrapping non-control-flow exceptions in
        NodeExecutionError for diagnostics.

        LLMJSONParsingError and NodeExecutionError itself are re-raised
        unchanged so callers' specific handlers still match.
        """
        try:
            return await self.run(context, payload)
        except NodeExecutionError:
            raise
        except Exception as e:
            # Lazy import to avoid circular dependency (agents.base imports
            # agents.constants which bootstraps agents.writing.* which import
            # agents.base).
            from agents.base import LLMJSONParsingError
            if isinstance(e, LLMJSONParsingError):
                raise
            raise NodeExecutionError(self.name, e) from e

    @staticmethod
    def _fork(context: PipelineContext) -> PipelineContext:
        """Return a shallow copy of *context* so node implementations can
        safely bind payload fields onto it without mutating the shared
        context object owned by the caller.

        Nodes only *rebind* fields (e.g. ``context.title = ...``); they do
        not mutate nested objects in place, so a shallow copy is sufficient.
        """
        return copy.copy(context)


@register_node
class PlannerNode(PipelineNode):
    name = AGENT_PLANNER

    def __init__(self, agent=None):
        self.agent = agent or get_default_agent(AGENT_PLANNER)

    async def run(self, context: PipelineContext, payload: dict[str, Any]) -> PlannerOutput:
        context = self._fork(context)
        self._bind_memory_metrics(context, self.agent)
        bind_truthy_payload_fields(
            context,
            payload,
            {
                "skeleton": "global_outline",
                "issue_summaries": "issue_summaries",
            },
        )

        result = await self.agent.generate_chapter_outline(
            context=context,
            total_chapters=context.total_chapters,
            on_chunk=payload.get("on_chunk"),
        )
        return PlannerOutput(payload={"chapter_outline": result}, raw=result)


@register_node
class WriterNode(PipelineNode):
    name = AGENT_WRITER

    def __init__(self, agent=None):
        self.agent = agent or get_default_agent(AGENT_WRITER)

    async def run(self, context: PipelineContext, payload: dict[str, Any]) -> WriterOutput:
        context = self._fork(context)
        self._bind_memory_metrics(context, self.agent)
        bind_truthy_payload_fields(
            context,
            payload,
            {
                "chapter_outline": "chapter_outline",
                "skeleton": "global_outline",
                "issue_summaries": "issue_summaries",
            },
        )
        bind_payload_fields(
            context,
            payload,
            {
                "word_count": "word_count",
                "reference_style": "reference_style",
                "vector_context": "vector_context",
                "rewrite_instructions": "rewrite_instructions",
            },
        )

        result = await self.agent.write_chapter(
            context=context,
            on_chunk=payload.get("on_chunk"),
        )
        return WriterOutput(content=result, payload={"content": result}, raw=result)


@register_node
class EditorNode(PipelineNode):
    name = AGENT_EDITOR

    def __init__(self, agent=None):
        self.agent = agent or get_default_agent(AGENT_EDITOR)

    async def run(self, context: PipelineContext, payload: dict[str, Any]) -> EditorOutput:
        context = self._fork(context)
        self._bind_memory_metrics(context, self.agent)
        bind_truthy_payload_fields(
            context,
            payload,
            {
                "chapter_outline": "chapter_outline",
                "issue_summaries": "issue_summaries",
            },
        )
        bind_payload_fields(
            context,
            payload,
            {
                "draft_content": "draft_content",
                "vector_context": "vector_context",
                "validation_errors": "validation_errors",
                "enable_light_polish": "enable_light_polish",
            },
        )

        result = await self.agent.review_chapter(
            context=context,
            on_chunk=payload.get("on_chunk"),
        )
        return EditorOutput(payload=result if isinstance(result, dict) else {"result": result}, raw=result)


@register_node
class ValidatorNode(PipelineNode):
    name = AGENT_VALIDATOR

    def __init__(self, agent=None):
        self.agent = agent or get_default_agent(AGENT_VALIDATOR)

    async def run(self, context: PipelineContext, payload: dict[str, Any]) -> ValidatorOutput:
        context = self._fork(context)
        self._bind_memory_metrics(context, self.agent)
        bind_payload_fields(
            context,
            payload,
            {
                "title": "title",
                "content": "chapter_content",
            },
        )

        result = await self.agent.validate_content(
            context=context,
            on_chunk=payload.get("on_chunk"),
        )
        # fail-closed: default to False when result is not a dict or missing "passed"
        return ValidatorOutput(passed=bool(result.get("passed", False)) if isinstance(result, dict) else False, payload=result, raw=result)


@register_node
class ExtractorNode(PipelineNode):
    name = AGENT_EXTRACTOR

    def __init__(self, agent=None):
        self.agent = agent or get_default_agent(AGENT_EXTRACTOR)

    async def run(self, context: PipelineContext, payload: dict[str, Any]) -> ExtractorOutput:
        context = self._fork(context)
        self._bind_memory_metrics(context, self.agent)
        bind_payload_fields(context, payload, {"chapter_content": "chapter_content"})
        if "chapter_content" not in payload and "content" in payload:
            context.chapter_content = payload["content"]

        result = await self.agent.extract_changes(
            context=context,
        )
        return ExtractorOutput(payload=result if isinstance(result, dict) else {"result": result}, raw=result)
