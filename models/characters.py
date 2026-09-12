"""Character cards, chapter state history, relationships, and manifests."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
    UniqueConstraint,
    true as sql_true,
)

from models.base import Base, _utcnow
from core.character_vocab import (
    CHARACTER_GENERATION_DEFAULT_IMPORTANCE,
    CHARACTER_GENERATION_DEFAULT_STATUS,
    CHARACTER_ARC_DEFAULT_STATUS,
    CHARACTER_ARC_DEFAULT_TYPE,
    CHARACTER_RELATIONSHIP_DEFAULT_TYPE,
    CHARACTER_FIRST_CHAPTER,
    CHARACTER_RELATIONSHIP_ACTIVE,
    CHARACTER_STORYLINE_MAIN,
)


class CharacterCard(Base):
    __tablename__ = "character_cards"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_character_cards_project_name"),
        Index("ix_character_cards_project_importance", "project_id", "importance"),
        Index("ix_character_cards_project_status", "project_id", "status"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    aliases = Column(JSON, nullable=False, default=list)
    card_data = Column(JSON, nullable=False, default=dict)
    current_state = Column(JSON, nullable=False, default=dict)
    importance = Column(
        String(20),
        nullable=False,
        default=CHARACTER_GENERATION_DEFAULT_IMPORTANCE,
        server_default=CHARACTER_GENERATION_DEFAULT_IMPORTANCE,
    )
    last_appearance = Column(Integer, nullable=True)
    status = Column(
        String(20),
        nullable=False,
        default=CHARACTER_GENERATION_DEFAULT_STATUS,
        server_default=CHARACTER_GENERATION_DEFAULT_STATUS,
    )
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class CharacterCardSnapshot(Base):
    __tablename__ = "character_card_snapshots"
    __table_args__ = (
        Index("ix_character_card_snapshots_character_created", "character_id", "created_at"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    character_id = Column(Uuid, ForeignKey("character_cards.id", ondelete="CASCADE"), nullable=False)
    card_data = Column(JSON, nullable=False)
    current_state = Column(JSON, nullable=False)
    snapshot_metadata = Column("metadata", JSON, nullable=False, default=dict)
    checksum = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=_utcnow)


class CharacterCardChangeRecord(Base):
    __tablename__ = "character_card_change_records"
    __table_args__ = (
        UniqueConstraint("before_snapshot_id", name="uq_character_card_change_before_snapshot"),
        Index("ix_character_card_changes_character_created", "character_id", "created_at"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    character_id = Column(Uuid, ForeignKey("character_cards.id", ondelete="CASCADE"), nullable=False)
    before_snapshot_id = Column(
        Uuid,
        ForeignKey("character_card_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    changed_fields = Column(JSON, nullable=False, default=list)
    patch = Column(JSON, nullable=False, default=dict)
    effective_from_chapter = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class CharacterChapterState(Base):
    __tablename__ = "character_chapter_states"
    __table_args__ = (
        UniqueConstraint(
            "character_id",
            "storyline_id",
            "chapter_index",
            name="uq_character_chapter_state_position",
        ),
        Index(
            "ix_character_chapter_states_lookup",
            "character_id",
            "storyline_id",
            "chapter_index",
        ),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    character_id = Column(Uuid, ForeignKey("character_cards.id", ondelete="CASCADE"), nullable=False)
    storyline_id = Column(
        String(100),
        nullable=False,
        default=CHARACTER_STORYLINE_MAIN,
        server_default=CHARACTER_STORYLINE_MAIN,
    )
    chapter_index = Column(Integer, nullable=False)
    state_data = Column(JSON, nullable=False, default=dict)
    changed_fields = Column(JSON, nullable=False, default=list)
    checksum = Column(String(64), nullable=False)
    source_ref = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class CharacterRelationship(Base):
    __tablename__ = "character_relationships"
    __table_args__ = (
        Index("ix_character_relationships_project_source", "project_id", "source_character_id"),
        Index("ix_character_relationships_project_target", "project_id", "target_character_id"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    source_character_id = Column(
        Uuid,
        ForeignKey("character_cards.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_character_id = Column(
        Uuid,
        ForeignKey("character_cards.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type = Column(
        String(100),
        nullable=False,
        default=CHARACTER_RELATIONSHIP_DEFAULT_TYPE,
        server_default=CHARACTER_RELATIONSHIP_DEFAULT_TYPE,
    )
    status = Column(
        String(20),
        nullable=False,
        default=CHARACTER_RELATIONSHIP_ACTIVE,
        server_default=CHARACTER_RELATIONSHIP_ACTIVE,
    )
    attributes = Column(JSON, nullable=False, default=dict)
    valid_from_chapter = Column(
        Integer,
        nullable=False,
        default=CHARACTER_FIRST_CHAPTER,
        server_default=str(CHARACTER_FIRST_CHAPTER),
    )
    valid_to_chapter = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class CharacterArc(Base):
    __tablename__ = "character_arcs"
    __table_args__ = (
        Index("ix_character_arcs_character_storyline", "character_id", "storyline_id"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    character_id = Column(Uuid, ForeignKey("character_cards.id", ondelete="CASCADE"), nullable=False)
    storyline_id = Column(
        String(100),
        nullable=False,
        default=CHARACTER_STORYLINE_MAIN,
        server_default=CHARACTER_STORYLINE_MAIN,
    )
    arc_type = Column(
        String(20),
        nullable=False,
        default=CHARACTER_ARC_DEFAULT_TYPE,
        server_default=CHARACTER_ARC_DEFAULT_TYPE,
    )
    name = Column(String(255), nullable=False)
    anchor_chapter = Column(Integer, nullable=True)
    target_chapter = Column(Integer, nullable=True)
    status = Column(
        String(20),
        nullable=False,
        default=CHARACTER_ARC_DEFAULT_STATUS,
        server_default=CHARACTER_ARC_DEFAULT_STATUS,
    )
    data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class CharacterManifest(Base):
    __tablename__ = "character_manifests"
    __table_args__ = (
        UniqueConstraint("character_id", name="uq_character_manifests_character"),
        Index("ix_character_manifests_project_updated", "project_id", "updated_at"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("novels.id", ondelete="CASCADE"), nullable=False)
    character_id = Column(Uuid, ForeignKey("character_cards.id", ondelete="CASCADE"), nullable=False)
    data = Column(JSON, nullable=False, default=dict)
    checksum = Column(String(64), nullable=False)
    is_read_only = Column(Boolean, nullable=False, default=True, server_default=sql_true())
    generated_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
