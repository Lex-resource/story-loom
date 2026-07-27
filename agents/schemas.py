"""Compatibility facade for agent schema imports.

New code should import from the cohesive modules directly:
- agents.agent_io
- agents.writing_schemas
- agents.pipeline_context
"""

from agents.agent_io import (
    AgentContext,
    AgentInput,
    AgentOutput,
    EditorOutput,
    ExtractorOutput,
    PlannerOutput,
    ValidatorOutput,
    WriterOutput,
)
from agents.pipeline_context import ContextData, NodePayload, PipelineContext
from agents.writing_schemas import (
    CharacterGraphEdge,
    CharacterGraphNode,
    CharacterGraphResponse,
    EditorDimensionScore,
    EditorEvaluations,
    EditorRawIssue,
    EditorResponse,
    PlannerChapterOutlineResponse,
    ValidatorIssue,
    ValidatorResponse,
)

__all__ = [
    "AgentContext",
    "AgentInput",
    "AgentOutput",
    "PlannerOutput",
    "WriterOutput",
    "EditorOutput",
    "ValidatorOutput",
    "ExtractorOutput",
    "EditorDimensionScore",
    "EditorEvaluations",
    "EditorRawIssue",
    "EditorResponse",
    "ValidatorIssue",
    "ValidatorResponse",
    "CharacterGraphNode",
    "CharacterGraphEdge",
    "CharacterGraphResponse",
    "PlannerChapterOutlineResponse",
    "ContextData",
    "NodePayload",
    "PipelineContext",
]
