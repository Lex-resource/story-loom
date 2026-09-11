"""Deterministic narrative projections for continuity-oriented retrieval."""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Column, Index, Integer, JSON, String, Text, text
from sqlalchemy.orm import validates

from models.novel_memory import _NovelMemoryScoped


NARRATIVE_ENTRY_TYPES = (
    "story_event",
    "story_segment",
    "stage_summary",
    "foreshadowing_link",
)
NARRATIVE_STATUSES = ("candidate", "accepted")


class NarrativeIndexEntry(_NovelMemoryScoped):
    """One accepted or candidate narrative projection."""

    __tablename__ = "novel_narrative_index"
    __table_args__ = (
        Index(
            "uq_narrative_index_mainline",
            "project_id", "storyline_id", "entry_type", "entry_key", "content_hash",
            unique=True, postgresql_where=text("branch_id IS NULL"),
        ),
        Index(
            "uq_narrative_index_branch",
            "project_id", "branch_id", "storyline_id", "entry_type", "entry_key", "content_hash",
            unique=True, postgresql_where=text("branch_id IS NOT NULL"),
        ),
        CheckConstraint(
            "entry_type IN ('story_event', 'story_segment', 'stage_summary', 'foreshadowing_link')",
            name="ck_narrative_index_entry_type",
        ),
        CheckConstraint("status IN ('candidate', 'accepted')", name="ck_narrative_index_status"),
        Index(
            "ix_narrative_index_recall",
            "project_id", "branch_id", "storyline_id", "status", "chapter_index", "entry_type",
        ),
    )

    entry_type = Column(String(30), nullable=False)
    entry_key = Column(String(255), nullable=False)
    parent_key = Column(String(255), nullable=True)
    target_key = Column(String(255), nullable=True)
    relation = Column(String(50), nullable=False, default="contains", server_default="contains")
    chapter_index = Column(Integer, nullable=True)
    chapter_end = Column(Integer, nullable=True)
    sequence = Column(Integer, nullable=False, default=0, server_default="0")
    content_hash = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False, default="", server_default="")
    content = Column(Text, nullable=False, default="", server_default="")
    data = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="accepted", server_default="accepted")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")

    @validates("entry_type")
    def validate_entry_type(self, _key, value):
        if value not in NARRATIVE_ENTRY_TYPES:
            raise ValueError(f"Invalid narrative entry type: {value}")
        return value

    @validates("status")
    def validate_status(self, _key, value):
        if value not in NARRATIVE_STATUSES:
            raise ValueError(f"Invalid narrative status: {value}")
        return value
