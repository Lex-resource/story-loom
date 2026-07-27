from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from agents.constants import (
    AGENT_EDITOR,
    AGENT_EXTRACTOR,
    AGENT_PLANNER,
    AGENT_VALIDATOR,
    AGENT_WRITER,
)


class AgentContext(BaseModel):
    project_id: str = ""
    target_chapter_index: int = 1
    genre: Optional[str] = None
    style: Optional[str] = None
    outline: Optional[str] = None
    background_knowledge: Optional[str] = None
    previous_chapters: Optional[str] = None


class AgentInput(BaseModel):
    context: AgentContext = Field(default_factory=AgentContext)
    payload: Dict[str, Any] = Field(default_factory=dict)


class AgentOutput(BaseModel):
    node: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    raw: Any = None


class PlannerOutput(AgentOutput):
    node: str = AGENT_PLANNER


class WriterOutput(AgentOutput):
    node: str = AGENT_WRITER
    content: str = ""


class EditorOutput(AgentOutput):
    node: str = AGENT_EDITOR


class ValidatorOutput(AgentOutput):
    node: str = AGENT_VALIDATOR
    passed: bool = True


class ExtractorOutput(AgentOutput):
    node: str = AGENT_EXTRACTOR
