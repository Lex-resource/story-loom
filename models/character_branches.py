"""Independent character side-story branches."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, Uuid, UniqueConstraint

from models.base import Base, _utcnow
from services.character_constants import (
    CHARACTER_BRANCH_CHAPTER_STATUS_DRAFT,
    CHARACTER_BRANCH_DEFAULT_STATUS,
)


class CharacterBranch(Base):
    __tablename__ = "character_branches"
    __table_args__ = (
        Index("ix_character_branches_project_status", "project_id", "status"),
        Index("ix_character_branches_character_status", "character_id", "status"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    character_id = Column(Uuid, ForeignKey("character_cards.id", ondelete="CASCADE"), nullable=False)
    arc_id = Column(Uuid, ForeignKey("character_arcs.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    storyline_id = Column(String(100), nullable=False, unique=True)
    anchor_main_chapter = Column(Integer, nullable=False)
    current_chapter_index = Column(Integer, nullable=False, default=0, server_default="0")
    target_chapters = Column(Integer, nullable=False, default=1, server_default="1")
    status = Column(String(20), nullable=False, default=CHARACTER_BRANCH_DEFAULT_STATUS, server_default=CHARACTER_BRANCH_DEFAULT_STATUS)
    user_request = Column(Text, nullable=False, default="", server_default="")
    generation_config = Column(JSON, nullable=False, default=dict)
    anchor_context = Column(JSON, nullable=False, default=dict)
    error = Column(Text, nullable=True)
    auto_discovered = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class CharacterBranchChapter(Base):
    __tablename__ = "character_branch_chapters"
    __table_args__ = (
        UniqueConstraint("branch_id", "chapter_index", name="uq_character_branch_chapter_position"),
        Index("ix_character_branch_chapters_branch_status", "branch_id", "status"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    branch_id = Column(Uuid, ForeignKey("character_branches.id", ondelete="CASCADE"), nullable=False)
    chapter_index = Column(Integer, nullable=False)
    anchor_main_chapter = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False, default="", server_default="")
    outline = Column(JSON, nullable=True)
    draft_content = Column(Text, nullable=True)
    edited_content = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    word_count = Column(Integer, nullable=True)
    validator_result = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default=CHARACTER_BRANCH_CHAPTER_STATUS_DRAFT, server_default=CHARACTER_BRANCH_CHAPTER_STATUS_DRAFT)
    state_data = Column(JSON, nullable=False, default=dict)
    relationship_changes = Column(JSON, nullable=False, default=list)
    source_ref = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
