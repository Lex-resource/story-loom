"""Structured, provenance-aware context sections for writing agents.

The bundle is an adapter around the existing flat PipelineContext fields. It
does not fetch data or call an LLM; callers can migrate prompt consumers one
section at a time while the legacy fields remain available.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ContextSource:
    """A traceable origin for one prompt context section."""

    source_ref: str
    source_chapter: int | None = None
    authority: str = ""
    version: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_ref": self.source_ref,
            "source_chapter": self.source_chapter,
            "authority": self.authority,
            "version": self.version,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ContextSection:
    """One bounded, named context surface supplied to an agent."""

    section_id: str
    title: str
    content: str
    sources: tuple[ContextSource, ...] = ()
    authority: str = ""
    source_chapter: int | None = None
    version: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "content": self.content,
            "sources": [source.to_dict() for source in self.sources],
            "authority": self.authority,
            "source_chapter": self.source_chapter,
            "version": self.version,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AgentContextBundle:
    """Role-specific context sections with a stable serialization contract."""

    agent_type: str
    project_id: str
    chapter_index: int
    sections: tuple[ContextSection, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        ids = [section.section_id for section in self.sections]
        if any(not section_id.strip() for section_id in ids):
            raise ValueError("context section id cannot be empty")
        if len(ids) != len(set(ids)):
            raise ValueError("context section ids must be unique")

    @property
    def section_ids(self) -> tuple[str, ...]:
        return tuple(section.section_id for section in self.sections)

    def get(self, section_id: str) -> ContextSection | None:
        return next(
            (section for section in self.sections if section.section_id == section_id),
            None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_type": self.agent_type,
            "project_id": self.project_id,
            "chapter_index": self.chapter_index,
            "sections": [section.to_dict() for section in self.sections],
            "metadata": dict(self.metadata),
        }

    def render(
        self,
        max_chars: int | None = None,
        *,
        include_sources: bool = False,
    ) -> str:
        """Render sections for a prompt without mutating stored content."""
        blocks: list[str] = []
        used = 0
        for section in self.sections:
            header = f"【{section.title}】"
            body = section.content.strip()
            if not body:
                continue
            if include_sources and section.sources:
                refs = ", ".join(source.source_ref for source in section.sources)
                body = f"{body}\n[来源: {refs}]"
            block = f"{header}\n{body}"
            separator = "\n\n" if blocks else ""
            remaining = None if max_chars is None else max_chars - used - len(separator)
            if remaining is not None and remaining <= 0:
                break
            if remaining is not None:
                block = _compact_text(block, remaining)
            blocks.append(separator + block)
            used += len(blocks[-1])
            if max_chars is not None and used >= max_chars:
                break
        return "".join(blocks)[: max_chars if max_chars is not None else None]


_SECTION_DEFINITIONS: dict[str, tuple[tuple[str, str, str], ...]] = {
    # Planner follows the trajectory and stable character facts. It does not
    # need the writer's full character-card payload or vector snippets.
    "planner": (
        ("global_outline", "全局总纲", "global_outline"),
        ("character_manifest", "角色人物志", "character_manifest_context"),
        ("novel_memory", "分层记忆", "novel_memory_context"),
        ("narrative_index", "叙事索引", "narrative_index_context"),
        ("chapter_handoff", "上一章交接", "chapter_handoff_context"),
    ),
    # Writer receives the current chapter surfaces and the immediate handoff.
    "writer": (
        ("chapter_outline", "本章大纲", "chapter_outline"),
        ("character_card", "角色卡与当前状态", "character_card_context"),
        ("writer_execution_brief", "Writer 叙事执行简报", "writer_execution_brief_context"),
        ("novel_memory", "分层记忆", "novel_memory_context"),
        ("narrative_index", "叙事索引", "narrative_index_context"),
        ("chapter_handoff", "上一章交接", "chapter_handoff_context"),
        ("vector_context", "相关正文召回", "vector_context"),
        ("world_state", "世界规则", "world_state"),
        ("character_state", "人物状态", "character_state"),
        ("foreshadowing", "伏笔账本", "foreshadowing"),
        ("plot_threads", "剧情线", "plot_threads"),
    ),
    "editor": (
        ("chapter_outline", "本章大纲", "chapter_outline"),
        ("chapter_contract", "章节契约", "chapter_contract_context"),
        ("chapter_handoff", "上一章交接", "chapter_handoff_context"),
        ("character_card", "角色卡与当前状态", "character_card_context"),
        ("novel_memory", "分层记忆", "novel_memory_context"),
        ("narrative_index", "叙事索引", "narrative_index_context"),
        ("world_state", "世界规则", "world_state"),
        ("character_state", "人物状态", "character_state"),
        ("foreshadowing", "伏笔账本", "foreshadowing"),
        ("plot_threads", "剧情线", "plot_threads"),
    ),
    "validator": (
        ("chapter_outline", "本章大纲", "chapter_outline"),
        ("chapter_contract", "章节契约", "chapter_contract_context"),
        ("chapter_handoff", "上一章交接", "chapter_handoff_context"),
        ("character_card", "角色卡与当前状态", "character_card_context"),
        ("novel_memory", "分层记忆", "novel_memory_context"),
        ("narrative_index", "叙事索引", "narrative_index_context"),
        ("world_state", "世界规则", "world_state"),
        ("character_state", "人物状态", "character_state"),
        ("foreshadowing", "伏笔账本", "foreshadowing"),
        ("plot_threads", "剧情线", "plot_threads"),
    ),
    "extractor": (
        ("chapter_outline", "本章大纲", "chapter_outline"),
        ("chapter_contract", "章节契约", "chapter_contract_context"),
        ("chapter_handoff", "上一章交接", "chapter_handoff_context"),
        ("character_card", "角色卡与当前状态", "character_card_context"),
        ("novel_memory", "分层记忆", "novel_memory_context"),
        ("narrative_index", "叙事索引", "narrative_index_context"),
        ("world_state", "世界规则", "world_state"),
        ("character_state", "人物状态", "character_state"),
        ("foreshadowing", "伏笔账本", "foreshadowing"),
        ("plot_threads", "剧情线", "plot_threads"),
    ),
}

_DEFAULT_AUTHORITY: dict[str, str] = {
    "global_outline": "accepted",
    "character_manifest_context": "frozen",
    "character_card_context": "frozen_or_accepted",
    "chapter_handoff_context": "accepted",
    "chapter_contract_context": "accepted",
    "writer_execution_brief_context": "accepted_projection",
    "novel_memory_context": "accepted_with_candidate_boundary",
    "narrative_index_context": "published_projection",
    "vector_context": "retrieved_advisory",
    "world_state": "legacy_advisory",
    "character_state": "legacy_advisory",
    "foreshadowing": "legacy_advisory",
    "plot_threads": "legacy_advisory",
    "chapter_outline": "accepted",
}


def build_agent_context_bundle(
    memory: Mapping[str, Any],
    *,
    agent_type: str = "writer",
) -> AgentContextBundle:
    """Build a role-specific bundle from existing pipeline memory fields."""
    source_metadata = memory.get("context_sources") or {}
    if not isinstance(source_metadata, Mapping):
        source_metadata = {}
    sections: list[ContextSection] = []
    definitions = _SECTION_DEFINITIONS.get(agent_type, _SECTION_DEFINITIONS["writer"])
    for section_id, title, field_name in definitions:
        value = memory.get(field_name)
        if value is None or value == "":
            continue
        content = _serialize_content(value)
        if not content.strip():
            continue
        source_data = source_metadata.get(field_name, {})
        if not isinstance(source_data, Mapping):
            source_data = {}
        source_ref = str(source_data.get("source_ref") or field_name)
        source_chapter = source_data.get("source_chapter")
        version = source_data.get("version")
        authority = str(
            source_data.get("authority")
            or _DEFAULT_AUTHORITY.get(field_name, "advisory")
        )
        source = ContextSource(
            source_ref=source_ref,
            source_chapter=source_chapter,
            authority=authority,
            version=version,
            metadata={"field_name": field_name},
        )
        sections.append(
            ContextSection(
                section_id=section_id,
                title=title,
                content=content,
                sources=(source,),
                authority=authority,
                source_chapter=source_chapter,
                version=version,
                metadata={"field_name": field_name},
            )
        )

    return AgentContextBundle(
        agent_type=agent_type,
        project_id=str(memory.get("project_id") or ""),
        chapter_index=int(memory.get("chapter_index") or 0),
        sections=tuple(sections),
        metadata={"source": "pipeline_memory", "compatibility": "flat_fields_preserved"},
    )


def _serialize_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _compact_text(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    marker = "\n...[context compacted]...\n"
    if max_chars <= len(marker):
        return value[:max_chars]
    available = max_chars - len(marker)
    tail = max(1, available // 4)
    head = available - tail
    return value[:head] + marker + value[-tail:]
