"""Project deletion and cleanup of derived storage."""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.character_branches import CharacterBranch, CharacterBranchChapter
from models.characters import (
    CharacterArc,
    CharacterCard,
    CharacterCardChangeRecord,
    CharacterCardSnapshot,
    CharacterChapterState,
    CharacterManifest,
    CharacterRelationship,
)
from models.knowledge import (
    EntityMergeLog,
    GraphEdge,
    GraphNode,
    IssueSummary,
    LivingDocVersion,
    RawIssue,
    SettingsDoc,
    VectorOutbox,
)
from models.narrative_index import NarrativeIndexEntry
from models.novel import Chapter, ChapterOutline, Commit, CommitSnapshot, Job, Novel, TokenUsage
from models.novel_memory import (
    NovelMemoryAtom,
    NovelMemoryConflict,
    NovelMemoryEvidence,
    NovelSceneBlock,
    ProjectDoctrine,
)
from services.pipeline_types import JobStatus

logger = logging.getLogger(__name__)

_ACTIVE_JOB_STATUSES = (JobStatus.PENDING, JobStatus.RUNNING)


async def active_project_job_ids(db: AsyncSession, project_id: uuid.UUID) -> list[uuid.UUID]:
    result = await db.execute(
        select(Job.id).where(
            Job.project_id == project_id,
            Job.status.in_(_ACTIVE_JOB_STATUSES),
        )
    )
    return list(result.scalars().all())


async def cancel_active_project_jobs(db: AsyncSession, project_id: uuid.UUID) -> list[uuid.UUID]:
    """Make cancellation visible to workers before project rows disappear."""
    job_ids = await active_project_job_ids(db, project_id)
    if job_ids:
        await db.execute(
            update(Job)
            .where(Job.id.in_(job_ids))
            .values(status=JobStatus.CANCELLED, error="项目已删除，任务已取消")
        )
    return job_ids


async def delete_project_rows(db: AsyncSession, project_id: uuid.UUID) -> list[uuid.UUID]:
    """Delete project-owned rows in dependency order."""
    # Serialize deletion with project commands that also lock the Novel row.
    # The initial cancellation commit makes the first snapshot visible to
    # workers; this lock closes the race before the destructive transaction.
    await db.execute(
        select(Novel.id).where(Novel.id == project_id).with_for_update()
    )
    await cancel_active_project_jobs(db, project_id)
    branch_ids = list(
        (
            await db.execute(
                select(CharacterBranch.id).where(CharacterBranch.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    character_ids = list(
        (
            await db.execute(
                select(CharacterCard.id).where(CharacterCard.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    commit_ids = list(
        (await db.execute(select(Commit.id).where(Commit.project_id == project_id)))
        .scalars()
        .all()
    )

    if branch_ids:
        await db.execute(
            delete(CharacterBranchChapter).where(
                CharacterBranchChapter.branch_id.in_(branch_ids)
            )
        )
    if character_ids:
        for model in (
            CharacterCardChangeRecord,
            CharacterCardSnapshot,
            CharacterChapterState,
        ):
            await db.execute(delete(model).where(model.character_id.in_(character_ids)))
    if commit_ids:
        await db.execute(delete(CommitSnapshot).where(CommitSnapshot.commit_id.in_(commit_ids)))

    await db.execute(delete(GraphEdge).where(GraphEdge.project_id == project_id))
    await db.execute(delete(GraphNode).where(GraphNode.project_id == project_id))

    for model in (
        NovelMemoryAtom,
        NovelMemoryConflict,
        NovelSceneBlock,
        ProjectDoctrine,
        NarrativeIndexEntry,
        NovelMemoryEvidence,
        SettingsDoc,
        RawIssue,
        IssueSummary,
        LivingDocVersion,
        VectorOutbox,
        EntityMergeLog,
        TokenUsage,
        ChapterOutline,
        Chapter,
        Job,
        CharacterManifest,
        CharacterRelationship,
        CharacterBranch,
        CharacterArc,
        CharacterCard,
        Commit,
    ):
        await db.execute(delete(model).where(model.project_id == project_id))

    await db.execute(delete(Novel).where(Novel.id == project_id))
    return branch_ids


async def delete_project_projections(
    project_id: uuid.UUID,
    branch_ids: list[uuid.UUID],
) -> list[str]:
    """Remove rebuildable Chroma and living-doc projections."""
    from services.character_branch_vector_service import branch_vector_collection_name
    from services.living_docs_files import get_project_dir
    from services.vector_chroma import delete_collection
    from services.vector_constants import VECTOR_COLLECTION_PREFIX

    errors: list[str] = []
    collection_names = [f"{VECTOR_COLLECTION_PREFIX}{project_id}"]
    collection_names.extend(branch_vector_collection_name(branch_id) for branch_id in branch_ids)
    for collection_name in collection_names:
        try:
            await delete_collection(collection_name)
        except Exception as exc:
            errors.append(f"chroma:{collection_name}: {exc}")

    project_dir = Path(get_project_dir(str(project_id)))
    if project_dir.exists():
        try:
            shutil.rmtree(project_dir)
        except Exception as exc:
            errors.append(f"living_docs:{project_dir}: {exc}")

    for error in errors:
        logger.warning("project_projection_cleanup_failed project_id=%s detail=%s", project_id, error)
    return errors


async def delete_project_data(db: AsyncSession, project_id: uuid.UUID) -> list[str]:
    """Delete database state and then best-effort rebuildable projections."""
    # Commit cancellation separately so an external worker can observe it
    # before the destructive transaction starts.
    await cancel_active_project_jobs(db, project_id)
    await db.commit()
    branch_ids = await delete_project_rows(db, project_id)
    await db.commit()
    return await delete_project_projections(project_id, branch_ids)
