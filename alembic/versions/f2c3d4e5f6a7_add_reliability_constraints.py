"""add reliability constraints and durable intervention prompts

Revision ID: f2c3d4e5f6a7
Revises: f1b2c3d4e5f6
Create Date: 2026-07-23 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "f1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("intervention_prompt", sa.Text(), nullable=True))
    op.execute(sa.text("""
        DELETE FROM chapters a USING chapters b
        WHERE a.novel_id = b.novel_id
          AND a.chapter_index = b.chapter_index
          AND (a.updated_at, a.id) < (b.updated_at, b.id)
    """))
    op.execute(sa.text("""
        DELETE FROM chapter_outlines a USING chapter_outlines b
        WHERE a.project_id = b.project_id
          AND a.chapter_index = b.chapter_index
          AND (a.updated_at, a.id) < (b.updated_at, b.id)
    """))
    op.execute(sa.text("""
        DELETE FROM living_doc_versions a USING living_doc_versions b
        WHERE a.project_id = b.project_id
          AND a.chapter_index = b.chapter_index
          AND a.doc_type = b.doc_type
          AND (a.created_at, a.id) < (b.created_at, b.id)
    """))
    op.execute(sa.text("""
        UPDATE jobs SET status = 'cancelled'
        WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (
                    PARTITION BY project_id, type ORDER BY created_at DESC, id DESC
                ) AS position
                FROM jobs
                WHERE type = 'generate' AND status IN ('pending', 'running')
            ) ranked
            WHERE ranked.position > 1
        )
    """))
    op.create_unique_constraint("uq_chapters_novel_chapter", "chapters", ["novel_id", "chapter_index"])
    op.create_unique_constraint(
        "uq_chapter_outlines_project_chapter", "chapter_outlines", ["project_id", "chapter_index"]
    )
    op.create_unique_constraint(
        "uq_living_doc_versions_project_chapter_type",
        "living_doc_versions",
        ["project_id", "chapter_index", "doc_type"],
    )
    op.create_index("ix_chapters_novel_status", "chapters", ["novel_id", "status"])
    op.create_index("ix_jobs_status_created", "jobs", ["status", "created_at"])
    op.create_index("ix_jobs_project_status", "jobs", ["project_id", "status"])
    op.create_index(
        "uq_jobs_active_generate_project",
        "jobs",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("type = 'generate' AND status IN ('pending', 'running')"),
    )
    op.create_index(
        "ix_settings_docs_project_category_active",
        "settings_docs",
        ["project_id", "category", "is_active"],
    )
    op.create_index("ix_vector_outbox_status_created", "vector_outbox", ["status", "created_at"])
    op.create_index("ix_vector_outbox_project_status", "vector_outbox", ["project_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_vector_outbox_project_status", table_name="vector_outbox")
    op.drop_index("ix_vector_outbox_status_created", table_name="vector_outbox")
    op.drop_index("ix_settings_docs_project_category_active", table_name="settings_docs")
    op.drop_index("uq_jobs_active_generate_project", table_name="jobs")
    op.drop_index("ix_jobs_project_status", table_name="jobs")
    op.drop_index("ix_jobs_status_created", table_name="jobs")
    op.drop_index("ix_chapters_novel_status", table_name="chapters")
    op.drop_constraint("uq_living_doc_versions_project_chapter_type", "living_doc_versions", type_="unique")
    op.drop_constraint("uq_chapter_outlines_project_chapter", "chapter_outlines", type_="unique")
    op.drop_constraint("uq_chapters_novel_chapter", "chapters", type_="unique")
    op.drop_column("jobs", "intervention_prompt")
