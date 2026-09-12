from __future__ import annotations

import uuid
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, JSON, Boolean, Uuid, Index, UniqueConstraint
from sqlalchemy.orm import relationship, validates
from core.pipeline_vocab import NovelStatus, PipelineStep
from models.base import Base, _utcnow


class Novel(Base):
    __tablename__ = "novels"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    author = Column(String(255))
    type = Column(String(20))  # reference / project
    novel_format = Column(String(50))
    creative_profile = Column(JSON, nullable=True)
    character_branch_auto_discovery_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    readonly_docs = Column(JSON, nullable=True)
    reference_book_id = Column(Uuid, ForeignKey("novels.id", ondelete="SET NULL"), nullable=True)
    target_chapters = Column(Integer)
    word_count_per_chapter = Column(Integer, default=3000)
    optimize_interval = Column(Integer, default=10)
    mode = Column(String(10), default="step")  # step / auto
    total_chapters = Column(Integer, default=0)
    total_chars = Column(Integer, default=0)
    status = Column(String(20), default="planning")  # planning/generating/paused/failed/completed/cancelled
    current_chapter = Column(Integer, default=0)
    outline = Column(JSON)
    style_evolution = Column(JSON)
    active_commit_id = Column(Uuid, nullable=True)  # Version control active commit
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    @validates('status')
    def validate_novel_status(self, key, value):
        valid_statuses = {e.value for e in NovelStatus}
        if value and value not in valid_statuses:
            raise ValueError(f"Invalid Novel status: {value}")
        return value

    chapters = relationship("Chapter", back_populates="novel", foreign_keys="Chapter.novel_id", cascade="all, delete-orphan")
    chapter_outlines = relationship("ChapterOutline", back_populates="novel", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="novel", cascade="all, delete-orphan")
    commits = relationship("Commit", back_populates="novel", cascade="all, delete-orphan")
    settings_docs = relationship("SettingsDoc", back_populates="novel", cascade="all, delete-orphan")

class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (
        UniqueConstraint("novel_id", "chapter_index", name="uq_chapters_novel_chapter"),
        Index("ix_chapters_novel_status", "novel_id", "status"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    novel_id = Column(Uuid, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    chapter_index = Column(Integer, nullable=False)
    title = Column(String(255))
    outline = Column(JSON)
    draft_content = Column(Text)
    edited_content = Column(Text)
    content = Column(Text)
    word_count = Column(Integer)
    validator_result = Column(JSON)
    editor_decision = Column(String(20))  # proceed/revise/rewrite (see services.constants.EDITOR_DECISION_*)
    rewrite_count = Column(Integer, default=0)
    force_corrected = Column(Boolean, default=False, server_default="0", nullable=False)
    evaluations = Column(JSON, nullable=True)
    review_flags = Column(JSON, default=list, nullable=True)
    error = Column(Text)
    pipeline_step = Column(String(50), nullable=True)  # outline/writing/editing/validating/extracting/published
    status = Column(String(20))  # draft/validated/pending_review/post_processing/published/failed/postprocess_failed/audit_failed (see services.pipeline_state.ChapterStatus)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    novel = relationship("Novel", back_populates="chapters", foreign_keys=[novel_id])

    @validates('pipeline_step')
    def validate_pipeline_step(self, key, value):
        valid_steps = {e.value for e in PipelineStep}
        if value and value not in valid_steps:
            raise ValueError(f"Invalid pipeline step: {value}")
        return value

class ChapterOutline(Base):
    __tablename__ = "chapter_outlines"
    __table_args__ = (
        UniqueConstraint("project_id", "chapter_index", name="uq_chapter_outlines_project_chapter"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    chapter_index = Column(Integer, nullable=False)
    outline = Column(JSON, nullable=False)
    source = Column(String(20), default="planner")
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    novel = relationship("Novel", back_populates="chapter_outlines")

class Commit(Base):
    __tablename__ = "commits"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    parent_commit_id = Column(Uuid, ForeignKey("commits.id", ondelete="SET NULL"), nullable=True)
    commit_message = Column(String(255))
    author = Column(String(50), default="AI")  # AI / User
    created_at = Column(DateTime, default=_utcnow)

    novel = relationship("Novel", back_populates="commits", foreign_keys=[project_id])
    snapshots = relationship("CommitSnapshot", back_populates="commit", cascade="all, delete-orphan")

class CommitSnapshot(Base):
    __tablename__ = "commit_snapshots"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    commit_id = Column(Uuid, ForeignKey("commits.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(String(50), nullable=False)  # chapter, character_state, world_rule, plot_thread
    entity_id = Column(String(50), nullable=False)    # chapter_index or doc_name
    data = Column(JSON, nullable=False)

    commit = relationship("Commit", back_populates="snapshots")
