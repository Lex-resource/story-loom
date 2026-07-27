from __future__ import annotations

import uuid
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, JSON, Boolean, Uuid, Float, Index, text
from sqlalchemy.orm import relationship, validates
from models.base import Base, _utcnow


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_created", "status", "created_at"),
        Index("ix_jobs_project_status", "project_id", "status"),
        Index(
            "uq_jobs_active_generate_project",
            "project_id",
            unique=True,
            postgresql_where=text("type = 'generate' AND status IN ('pending', 'running')"),
        ),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(20), nullable=False)  # generate/extraction/vector_sync/living_doc_compact
    status = Column(String(20), nullable=False)  # pending/running/paused/failed/completed/cancelled
    current_step = Column(String(50))
    current_chapter = Column(Integer)
    params = Column(JSON, nullable=True)
    intervention_prompt = Column(Text, nullable=True)
    error = Column(Text)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    @validates('status')
    def validate_job_status(self, key, value):
        from services.pipeline_state import JobStatus
        valid_statuses = {e.value for e in JobStatus}
        if value and value not in valid_statuses:
            raise ValueError(f"Invalid Job status: {value}")
        return value

    novel = relationship("Novel", back_populates="jobs")

class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(255))
    name_zh = Column(String(100), nullable=True)
    category = Column(String(50))
    type = Column(String(20))  # extraction/writing
    system_prompt = Column(Text)
    user_prompt_template = Column(Text)
    is_default = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utcnow)

class TokenUsage(Base):
    __tablename__ = "token_usages"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    chapter_index = Column(Integer, nullable=False)
    agent_name = Column(String(50), nullable=False)  # writer, editor, planner, extractor, etc.
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    cache_hit_tokens = Column(Integer, default=0, nullable=False)
    cache_miss_tokens = Column(Integer, default=0, nullable=False)
    duration = Column(Float, default=0.0, nullable=False)
    model_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=_utcnow)

class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(String(50), primary_key=True)
    value = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

class PipelineConfigModel(Base):
    __tablename__ = "pipeline_configs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(50), unique=True, nullable=False)
    name_zh = Column(String(50), nullable=True)
    nodes = Column(JSON, nullable=False)
    enable_living_docs_update = Column(Boolean, nullable=False, default=True)
    enable_editor_loop = Column(Boolean, nullable=False, default=True)
    max_rewrite = Column(Integer, nullable=False, default=1)
    readonly_docs = Column(JSON, nullable=False)
    required_docs = Column(JSON, nullable=False)
    enable_force_correction = Column(Boolean, nullable=False, default=False)
    validation_before_editor = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

class SystemNodeDict(Base):
    __tablename__ = "system_nodes"

    id = Column(String(50), primary_key=True)
    name_zh = Column(String(100), nullable=False)

class SystemDocTypeDict(Base):
    __tablename__ = "system_doc_types"

    id = Column(String(50), primary_key=True)
    name_zh = Column(String(100), nullable=False)
