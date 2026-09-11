"""Persistence models for layered, provenance-aware novel memory."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import validates

from models.base import Base, _utcnow
from services.novel_memory_types import (
    ATOM_STATUSES,
    AUTHORITIES,
    CONFLICT_STATUSES,
    SCENE_BLOCK_ACTIVE,
    STORYLINE_MAIN,
)


class _NovelMemoryScoped(Base):
    """Common project and timeline fields shared by all memory records."""

    __abstract__ = True

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(
        Uuid,
        ForeignKey("character_branches.id", ondelete="CASCADE"),
        nullable=True,
    )
    storyline_id = Column(String(100), nullable=False, default=STORYLINE_MAIN, server_default=STORYLINE_MAIN)
    source_ref = Column(Text, nullable=False)
    source_chapter = Column(Integer, nullable=True)
    confidence = Column(Float, nullable=False, default=0.0, server_default="0")
    version = Column(Integer, nullable=False, default=1, server_default="1")
    valid_from_chapter = Column(Integer, nullable=True)
    valid_to_chapter = Column(Integer, nullable=True)
    authority = Column(String(20), nullable=False, default="generated", server_default="generated")
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class NovelMemoryEvidence(_NovelMemoryScoped):
    __tablename__ = "novel_memory_evidence"
    __table_args__ = (
        Index("uq_novel_memory_evidence_mainline", "project_id", "storyline_id", "source_ref", "content_hash", unique=True, postgresql_where=text("branch_id IS NULL")),
        Index("uq_novel_memory_evidence_branch", "project_id", "branch_id", "storyline_id", "source_ref", "content_hash", unique=True, postgresql_where=text("branch_id IS NOT NULL")),
        Index("ix_novel_memory_evidence_scope_chapter", "project_id", "branch_id", "storyline_id", "source_chapter"),
    )

    stage = Column(String(50), nullable=False)
    content_hash = Column(String(64), nullable=False)
    raw_content = Column(Text, nullable=False)
    extracted_data = Column(JSON, nullable=True)
    is_immutable = Column(Boolean, nullable=False, default=True, server_default="true")


class NovelMemoryConflict(_NovelMemoryScoped):
    """A durable review item for a hard authority or continuity conflict."""

    __tablename__ = "novel_memory_conflicts"
    __table_args__ = (
        Index("uq_novel_memory_conflict_hash", "conflict_hash", unique=True),
        Index(
            "ix_novel_memory_conflicts_queue",
            "project_id", "branch_id", "storyline_id", "status", "source_chapter",
        ),
        CheckConstraint(
            "status IN ('open', 'resolved', 'dismissed')",
            name="ck_novel_memory_conflict_status",
        ),
    )

    conflict_hash = Column(String(64), nullable=False)
    conflict_type = Column(String(50), nullable=False)
    memory_key = Column(String(255), nullable=False)
    severity = Column(String(20), nullable=False, default="high", server_default="high")
    description = Column(Text, nullable=False)
    evidence = Column(Text, nullable=False, default="", server_default="")
    conflicts_with = Column(Text, nullable=False, default="", server_default="")
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default=CONFLICT_STATUSES[0], server_default=CONFLICT_STATUSES[0])
    resolved_by = Column(String(255), nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    @validates("status")
    def validate_status(self, _key, value):
        if value not in CONFLICT_STATUSES:
            raise ValueError(f"Invalid novel memory conflict status: {value}")
        return value


class NovelMemoryAtom(_NovelMemoryScoped):
    __tablename__ = "novel_memory_atoms"
    __table_args__ = (
        Index("uq_novel_memory_atom_mainline", "project_id", "storyline_id", "memory_key", "version", unique=True, postgresql_where=text("branch_id IS NULL")),
        Index("uq_novel_memory_atom_branch", "project_id", "branch_id", "storyline_id", "memory_key", "version", unique=True, postgresql_where=text("branch_id IS NOT NULL")),
        Index("uq_novel_memory_atom_candidate_mainline", "project_id", "storyline_id", "memory_key", "candidate_hash", unique=True, postgresql_where=text("branch_id IS NULL")),
        Index("uq_novel_memory_atom_candidate_branch", "project_id", "branch_id", "storyline_id", "memory_key", "candidate_hash", unique=True, postgresql_where=text("branch_id IS NOT NULL")),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_novel_memory_atom_confidence"),
        Index("ix_novel_memory_atoms_recall", "project_id", "branch_id", "storyline_id", "status", "valid_from_chapter"),
    )

    evidence_id = Column(Uuid, ForeignKey("novel_memory_evidence.id", ondelete="SET NULL"), nullable=True)
    memory_key = Column(String(255), nullable=False)
    candidate_hash = Column(String(64), nullable=False)
    atom_type = Column(String(50), nullable=False)
    statement = Column(Text, nullable=False)
    data = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default=ATOM_STATUSES[0], server_default=ATOM_STATUSES[0])
    # 召回命中簿记（ENABLE_RECALL_HIT_TRACKING）：candidate 生命周期清扫的数据源。
    recall_use_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_recalled_chapter = Column(Integer, nullable=True)

    @validates("status")
    def validate_status(self, _key, value):
        if value not in ATOM_STATUSES:
            raise ValueError(f"Invalid novel memory atom status: {value}")
        return value

    @validates("authority")
    def validate_authority(self, _key, value):
        if value not in AUTHORITIES:
            raise ValueError(f"Invalid novel memory authority: {value}")
        return value


class NovelSceneBlock(_NovelMemoryScoped):
    __tablename__ = "novel_scene_blocks"
    __table_args__ = (
        Index("uq_novel_scene_block_mainline", "project_id", "storyline_id", "scope_type", "scope_key", "version", unique=True, postgresql_where=text("branch_id IS NULL")),
        Index("uq_novel_scene_block_branch", "project_id", "branch_id", "storyline_id", "scope_type", "scope_key", "version", unique=True, postgresql_where=text("branch_id IS NOT NULL")),
        Index("uq_novel_scene_block_content_mainline", "project_id", "storyline_id", "scope_type", "scope_key", "content_hash", unique=True, postgresql_where=text("branch_id IS NULL")),
        Index("uq_novel_scene_block_content_branch", "project_id", "branch_id", "storyline_id", "scope_type", "scope_key", "content_hash", unique=True, postgresql_where=text("branch_id IS NOT NULL")),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_novel_scene_block_confidence"),
        Index("ix_novel_scene_blocks_recall", "project_id", "branch_id", "storyline_id", "scope_type", "valid_to_chapter"),
    )

    scope_type = Column(String(30), nullable=False)
    scope_key = Column(String(255), nullable=False)
    content_hash = Column(String(64), nullable=False)
    summary = Column(Text, nullable=False)
    current_state = Column(JSON, nullable=False, default=dict)
    open_questions = Column(JSON, nullable=False, default=list)
    recent_changes = Column(JSON, nullable=False, default=list)
    status = Column(String(20), nullable=False, default=SCENE_BLOCK_ACTIVE, server_default=SCENE_BLOCK_ACTIVE)
    # 本版本相对上一版本的整合审计（参照 Codex memories 的 phase2 diff）：
    # 首个版本为 NULL；结构见 services.novel_memory_scenes.build_consolidation_diff。
    consolidation_diff = Column(JSON, nullable=True)


class ProjectDoctrine(_NovelMemoryScoped):
    __tablename__ = "project_doctrines"
    __table_args__ = (
        Index("uq_project_doctrine_mainline", "project_id", "storyline_id", "doctrine_key", "version", unique=True, postgresql_where=text("branch_id IS NULL")),
        Index("uq_project_doctrine_branch", "project_id", "branch_id", "storyline_id", "doctrine_key", "version", unique=True, postgresql_where=text("branch_id IS NOT NULL")),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_project_doctrine_confidence"),
        Index("ix_project_doctrines_recall", "project_id", "branch_id", "storyline_id", "doctrine_type"),
    )

    doctrine_key = Column(String(255), nullable=False)
    doctrine_type = Column(String(30), nullable=False)
    content = Column(Text, nullable=False)
    data = Column(JSON, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
