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
    # 供 services/config_versions.py 的跨进程缓存版本戳使用；写路径全部走
    # ORM setattr+commit，onupdate 可靠。
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

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
    """一个创作工作流的完整定义。

    ``name`` 既是路由键（等于 ``Novel.novel_format``），也是提示词模板的
    ``category`` 默认值。历史上本表只描述「跑哪些节点、重写几次」；工作流模块化之后
    它还承载表面策略、格式相关策略开关和质量维度 —— 即长短篇真正的差异所在。
    """

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
    # 有序阶段列表。为空时从 ``nodes`` 派生，保证存量行继续可用。
    stages = Column(JSON, nullable=True)
    # 格式相关的行为开关，取代散落各处的 ``novel_format ==`` 判断。
    policy = Column(JSON, nullable=True)
    # ``services/workflow_surface`` 的表面策略：frozen_v43 / short_form / custom。
    surface_strategy = Column(String(32), nullable=True)
    # 提示词模板 category。为空时用 ``name``，让自定义工作流可以复用既有提示词。
    prompt_category = Column(String(50), nullable=True)
    # 该工作流的质量维度集；为空时用表面策略的默认维度。
    quality_dims = Column(JSON, nullable=True)
    # 单章生成的**拓扑图**（步骤 + 裁决边 + 预算）。为空时用 ``services/chapter_graph``
    # 的 ``default_graph()`` —— 代码是默认拓扑的权威，本列只承载自定义。
    graph = Column(JSON, nullable=True)
    # 内置工作流不可删除。长篇冻结在 A28/V43，短篇是一等生产工作流，删掉任何一个
    # 都会让存量项目查不到自己的流程配置而在 worker 里炸掉。
    builtin = Column(Boolean, nullable=False, default=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

class WorkflowNodeDict(Base):
    """可复用的工作流节点。

    一个节点 = **角色 + 提示词 + 名称**。角色决定跑哪个适配器
    （``worker_support/chapter_steps``），执行它的 agent 由角色推导 —— 所以这里
    刻意没有 ``executor`` 列：角色和 agent 的对应关系是写死的 Python，存一份可写的
    副本只会让它们不一致。

    节点库与工作流是多对多：``pipeline_configs.graph`` 的每个步骤引用一个节点 id，
    同一个节点可以被任意多个工作流复用。
    """

    __tablename__ = "workflow_nodes"

    # 形如 "editor.review"（内置）或 "editor.review.savage"（自定义）。
    id = Column(String(64), primary_key=True)
    name_zh = Column(String(100), nullable=False)
    role = Column(String(32), nullable=False)
    # 覆盖该角色的内置提示词名。为空时用内置提示词。
    prompt_name = Column(String(100), nullable=True)
    # 目前只有 {"always_run": bool}，供 style_repair 类节点绕过确定性门控。
    options = Column(JSON, nullable=True)
    description = Column(Text, nullable=True)
    # 内置节点不可删除、不可改角色。
    builtin = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

class SystemNodeDict(Base):
    __tablename__ = "system_nodes"

    id = Column(String(50), primary_key=True)
    name_zh = Column(String(100), nullable=False)

class RuntimeTunable(Base):
    """运行参数行(键值存储)。

    缺行 = 用 services/runtime_tunables_service.PARAM_SPECS 的默认值,所以
    迁移不 seed;参数的元数据(类型/范围/说明/生效时机)也只在 PARAM_SPECS 里。
    """

    __tablename__ = "runtime_tunables"

    key = Column(String(64), primary_key=True)
    value = Column(JSON, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

class SystemDocTypeDict(Base):
    __tablename__ = "system_doc_types"

    id = Column(String(50), primary_key=True)
    name_zh = Column(String(100), nullable=False)
