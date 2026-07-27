from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ContextData:
    """Stable project / chapter-level inputs that do not change as the
    pipeline advances from node to node.
    """

    project_id: str
    chapter_index: int
    novel_format: str
    genre: str = ""
    style: str = ""
    global_outline: dict[str, Any] | None = None
    act_outline: dict[str, Any] | None = None
    chapter_outline: dict[str, Any] | None = None
    knowledge: dict[str, Any] | None = None
    previous_ending: str = ""
    short_term_context: str = ""
    full_manuscript_context: str = ""
    world_state: str = ""
    character_state: str = ""
    foreshadowing: str = ""
    plot_threads: str = ""
    raw_world_state: str = ""
    raw_character_state: str = ""
    raw_foreshadowing: str = ""
    raw_plot_threads: str = ""
    intervention: Optional[str] = None
    reference_style: str = ""
    total_chapters: int = 0


@dataclass
class NodePayload:
    """Mutable per-node execution fields threaded through the pipeline."""

    issue_summaries: str = ""
    word_count: int = 3000
    vector_context: str = ""
    rewrite_instructions: str = ""
    validation_errors: str = ""
    chapter_content: str = ""
    draft_content: str = ""
    title: str = ""
    enable_light_polish: bool = False


@dataclass
class PipelineContext:
    """Top-level pipeline context with compatibility flat fields."""

    project_id: str
    chapter_index: int
    novel_format: str
    genre: str = ""
    style: str = ""
    global_outline: dict[str, Any] | None = None
    act_outline: dict[str, Any] | None = None
    chapter_outline: dict[str, Any] | None = None
    knowledge: dict[str, Any] | None = None
    previous_ending: str = ""
    short_term_context: str = ""
    full_manuscript_context: str = ""
    world_state: str = ""
    character_state: str = ""
    foreshadowing: str = ""
    plot_threads: str = ""
    raw_world_state: str = ""
    raw_character_state: str = ""
    raw_foreshadowing: str = ""
    raw_plot_threads: str = ""
    intervention: Optional[str] = None

    # Pipeline specific execution fields
    issue_summaries: str = ""
    word_count: int = 3000
    reference_style: str = ""
    vector_context: str = ""
    rewrite_instructions: str = ""
    validation_errors: str = ""
    chapter_content: str = ""
    draft_content: str = ""
    title: str = ""
    enable_light_polish: bool = False
    total_chapters: int = 0

    @classmethod
    def from_memory(cls, project_id: str, chapter_index: int, memory: dict[str, Any]) -> "PipelineContext":
        return cls(
            project_id=project_id,
            chapter_index=chapter_index,
            novel_format=memory.get("novel_format", ""),
            genre=memory.get("genre", ""),
            style=memory.get("style", ""),
            global_outline=memory.get("global_outline"),
            act_outline=memory.get("act_outline"),
            chapter_outline=memory.get("chapter_outline"),
            knowledge=memory.get("knowledge"),
            previous_ending=memory.get("previous_ending", ""),
            short_term_context=memory.get("short_term_context", ""),
            full_manuscript_context=memory.get("full_manuscript_context", ""),
            world_state=memory.get("world_state", ""),
            character_state=memory.get("character_state", ""),
            foreshadowing=memory.get("foreshadowing", ""),
            plot_threads=memory.get("plot_threads", ""),
            raw_world_state=memory.get("raw_world_state", ""),
            raw_character_state=memory.get("raw_character_state", ""),
            raw_foreshadowing=memory.get("raw_foreshadowing", ""),
            raw_plot_threads=memory.get("raw_plot_threads", ""),
            intervention=memory.get("intervention"),
            reference_style=memory.get("reference_style", ""),
            vector_context=memory.get("vector_context", ""),
            rewrite_instructions=memory.get("rewrite_instructions", ""),
            validation_errors=memory.get("validation_errors", ""),
            chapter_content=memory.get("chapter_content", ""),
            draft_content=memory.get("draft_content", ""),
            title=memory.get("title", ""),
            enable_light_polish=memory.get("enable_light_polish", False),
            total_chapters=memory.get("total_chapters", 0),
        )

    def as_agent_inputs(self) -> dict[str, str]:
        return {
            "novel_format": self.novel_format,
            "genre": self.genre,
            "style": self.style,
            "world_state": self.world_state,
            "character_state": self.character_state,
            "foreshadowing": self.foreshadowing,
            "plot_threads": self.plot_threads,
            "previous_ending": self.previous_ending,
        }

    def to_context_data(self) -> ContextData:
        """Snapshot the stable project/chapter-level inputs."""
        return ContextData(
            project_id=self.project_id,
            chapter_index=self.chapter_index,
            novel_format=self.novel_format,
            genre=self.genre,
            style=self.style,
            global_outline=self.global_outline,
            act_outline=self.act_outline,
            chapter_outline=self.chapter_outline,
            knowledge=self.knowledge,
            previous_ending=self.previous_ending,
            short_term_context=self.short_term_context,
            full_manuscript_context=self.full_manuscript_context,
            world_state=self.world_state,
            character_state=self.character_state,
            foreshadowing=self.foreshadowing,
            plot_threads=self.plot_threads,
            raw_world_state=self.raw_world_state,
            raw_character_state=self.raw_character_state,
            raw_foreshadowing=self.raw_foreshadowing,
            raw_plot_threads=self.raw_plot_threads,
            intervention=self.intervention,
            reference_style=self.reference_style,
            total_chapters=self.total_chapters,
        )

    def to_node_payload(self) -> NodePayload:
        """Snapshot the per-node mutable execution fields."""
        return NodePayload(
            issue_summaries=self.issue_summaries,
            word_count=self.word_count,
            vector_context=self.vector_context,
            rewrite_instructions=self.rewrite_instructions,
            validation_errors=self.validation_errors,
            chapter_content=self.chapter_content,
            draft_content=self.draft_content,
            title=self.title,
            enable_light_polish=self.enable_light_polish,
        )

    @classmethod
    def from_parts(cls, data: "ContextData", payload: "NodePayload") -> "PipelineContext":
        """Assemble a PipelineContext from a ContextData + NodePayload pair."""
        return cls(
            project_id=data.project_id,
            chapter_index=data.chapter_index,
            novel_format=data.novel_format,
            genre=data.genre,
            style=data.style,
            global_outline=data.global_outline,
            act_outline=data.act_outline,
            chapter_outline=data.chapter_outline,
            knowledge=data.knowledge,
            previous_ending=data.previous_ending,
            short_term_context=data.short_term_context,
            full_manuscript_context=data.full_manuscript_context,
            world_state=data.world_state,
            character_state=data.character_state,
            foreshadowing=data.foreshadowing,
            plot_threads=data.plot_threads,
            raw_world_state=data.raw_world_state,
            raw_character_state=data.raw_character_state,
            raw_foreshadowing=data.raw_foreshadowing,
            raw_plot_threads=data.raw_plot_threads,
            intervention=data.intervention,
            reference_style=data.reference_style,
            total_chapters=data.total_chapters,
            issue_summaries=payload.issue_summaries,
            word_count=payload.word_count,
            vector_context=payload.vector_context,
            rewrite_instructions=payload.rewrite_instructions,
            validation_errors=payload.validation_errors,
            chapter_content=payload.chapter_content,
            draft_content=payload.draft_content,
            title=payload.title,
            enable_light_polish=payload.enable_light_polish,
        )

    def update_payload(self, payload: "NodePayload") -> None:
        """Apply a NodePayload snapshot onto this context in place."""
        self.issue_summaries = payload.issue_summaries
        self.word_count = payload.word_count
        self.vector_context = payload.vector_context
        self.rewrite_instructions = payload.rewrite_instructions
        self.validation_errors = payload.validation_errors
        self.chapter_content = payload.chapter_content
        self.draft_content = payload.draft_content
        self.title = payload.title
        self.enable_light_polish = payload.enable_light_polish
