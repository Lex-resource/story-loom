from __future__ import annotations

import uuid
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, JSON, Boolean, Uuid, Float, Index, UniqueConstraint
from sqlalchemy.orm import relationship, validates
from models.base import Base, _utcnow


class SettingsDoc(Base):
    __tablename__ = "settings_docs"
    __table_args__ = (
        Index("ix_settings_docs_project_category_active", "project_id", "category", "is_active"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    category = Column(String(50), nullable=False)  # character, world_rule, plot_thread, foreshadowing
    name = Column(String(255), nullable=False)
    content = Column(Text, nullable=False) # Markdown representation for RAG and display (rendered from data)
    data = Column(JSON, nullable=False)    # JSON Source of Truth for the entity
    is_active = Column(Boolean, default=True, server_default="1", nullable=False)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    
    aliases = Column(JSON, nullable=True)
    possible_duplicate_of = Column(JSON, nullable=True)

    novel = relationship("Novel", back_populates="settings_docs")

class GraphNode(Base):
    __tablename__ = "graph_nodes"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    category = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

class GraphEdge(Base):
    __tablename__ = "graph_edges"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    source_node_id = Column(Uuid, ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False)
    target_node_id = Column(Uuid, ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=True)
    label = Column(String(255), nullable=False)
    attributes = Column(JSON, nullable=True)
    valid_from_chapter = Column(Integer, nullable=False)
    valid_to_chapter = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

class RawIssue(Base):
    __tablename__ = "raw_issues"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    chapter_index = Column(Integer, nullable=False)
    category = Column(String(50))
    description = Column(Text)
    severity = Column(String(10))
    source = Column(String(20))  # editor/validator/user/system
    created_at = Column(DateTime, default=_utcnow)

class IssueSummary(Base):
    __tablename__ = "issue_summaries"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    category = Column(String(50))
    summary = Column(Text)
    examples = Column(Text)
    severity = Column(String(10))
    start_chapter = Column(Integer)
    end_chapter = Column(Integer)
    enabled = Column(Boolean, default=False, server_default="0", nullable=False)
    created_at = Column(DateTime, default=_utcnow)

class LivingDocVersion(Base):
    __tablename__ = "living_doc_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "chapter_index", "doc_type", name="uq_living_doc_versions_project_chapter_type"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    chapter_index = Column(Integer, nullable=False)
    doc_type = Column(String(50), nullable=False)
    path = Column(Text, nullable=False)
    checksum = Column(String(64))
    created_at = Column(DateTime, default=_utcnow)

class VectorOutbox(Base):
    __tablename__ = "vector_outbox"
    __table_args__ = (
        Index("ix_vector_outbox_status_created", "status", "created_at"),
        Index("ix_vector_outbox_project_status", "project_id", "status"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    chapter_index = Column(Integer)
    payload = Column(JSON, nullable=False)
    status = Column(String(20), default="pending")  # pending/syncing/done/error/failed
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    error = Column(Text)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

class EntityMergeLog(Base):
    __tablename__ = "entity_merge_logs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    source_name = Column(String(255), nullable=False)
    target_name = Column(String(255), nullable=False)
    reason = Column(Text)
    chapter_index = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
