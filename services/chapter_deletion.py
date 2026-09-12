import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel import (
    Chapter,
    ChapterOutline,
    Job,
    LivingDocVersion,
    RawIssue,
    TokenUsage,
    VectorOutbox,
)
from models.characters import (
    CharacterArc,
    CharacterCard,
    CharacterChapterState,
    CharacterRelationship,
)
from models.character_branches import CharacterBranch
from models.knowledge import GraphEdge
from models.narrative_index import NarrativeIndexEntry
from models.novel_memory import (
    NovelMemoryAtom,
    NovelMemoryConflict,
    NovelMemoryEvidence,
    NovelSceneBlock,
    ProjectDoctrine,
)
from services.novel_constants import JOB_TYPE_GENERATE
from services.character_constants import CHARACTER_STORYLINE_MAIN
from services.pipeline_types import JobStatus
from services.project_stats import sum_project_chars


class ChapterDeletionError(ValueError):
    """Raised when deleting a chapter would invalidate position references."""


async def lock_project_for_chapter_deletion(db: AsyncSession, pid: uuid.UUID):
    """Serialize chapter deletion with generation and other project commands."""
    from models.novel import Novel

    novel = (
        await db.execute(select(Novel).where(Novel.id == pid).with_for_update())
    ).scalar_one_or_none()
    return novel


async def assert_chapter_deletable(db: AsyncSession, pid: uuid.UUID, chapter_index: int) -> None:
    max_index = await db.scalar(
        select(func.max(Chapter.chapter_index)).where(Chapter.novel_id == pid)
    )
    if max_index != chapter_index:
        raise ChapterDeletionError("为保持章节引用一致，只能删除最后一章")

    active_job = await db.scalar(
        select(Job.id)
        .where(Job.project_id == pid, Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING)))
        .limit(1)
    )
    if active_job is not None:
        raise ChapterDeletionError("创作任务运行中，暂不能删除章节")

    anchored_branch = await db.scalar(
        select(CharacterBranch.id)
        .where(
            CharacterBranch.project_id == pid,
            CharacterBranch.anchor_main_chapter == chapter_index,
        )
        .limit(1)
    )
    if anchored_branch is not None:
        raise ChapterDeletionError("该章节是支线锚点，请先处理支线后再删除")


def _project_id_column(model_class):
    if hasattr(model_class, "project_id"):
        return model_class.project_id
    if hasattr(model_class, "novel_id"):
        return model_class.novel_id
    raise AttributeError(f"{model_class.__name__} has no project_id or novel_id column")


async def _delete_and_renumber(
    db: AsyncSession,
    model_class,
    pid: uuid.UUID,
    chapter_index: int,
) -> None:
    project_column = _project_id_column(model_class)
    await db.execute(
        delete(model_class).where(
            project_column == pid,
            model_class.chapter_index == chapter_index,
        )
    )
    await db.execute(
        update(model_class)
        .where(
            project_column == pid,
            model_class.chapter_index > chapter_index,
        )
        .values(chapter_index=model_class.chapter_index - 1)
    )


async def _renumber_after_deletion(
    db: AsyncSession,
    model_class,
    pid: uuid.UUID,
    chapter_index: int,
) -> None:
    project_column = _project_id_column(model_class)
    await db.execute(
        update(model_class)
        .where(
            project_column == pid,
            model_class.chapter_index > chapter_index,
        )
        .values(chapter_index=model_class.chapter_index - 1)
    )


async def delete_related_chapter_rows(
    db: AsyncSession,
    pid: uuid.UUID,
    chapter_index: int,
) -> None:
    for model_class in (
        ChapterOutline,
        LivingDocVersion,
        RawIssue,
        TokenUsage,
    ):
        await _delete_and_renumber(db, model_class, pid, chapter_index)

    # A project and a character branch use the same VectorOutbox table but
    # different namespaces. Never remove a branch outbox just because its
    # independent chapter happens to have the same number as this mainline
    # chapter.
    outboxes = (
        await db.execute(select(VectorOutbox).where(VectorOutbox.project_id == pid))
    ).scalars().all()
    main_collection = f"project_{pid}"
    for outbox in outboxes:
        payload = outbox.payload or {}
        collection_name = str(payload.get("collection_name") or main_collection)
        if collection_name != main_collection or outbox.chapter_index != chapter_index:
            continue
        await db.delete(outbox)

    character_ids = (
        await db.execute(select(CharacterCard.id).where(CharacterCard.project_id == pid))
    ).scalars().all()
    if character_ids:
        await db.execute(
            delete(CharacterChapterState).where(
                CharacterChapterState.character_id.in_(character_ids),
                CharacterChapterState.storyline_id == CHARACTER_STORYLINE_MAIN,
                CharacterChapterState.chapter_index == chapter_index,
            )
        )
        # 单条相关子查询:仅当被删章节是角色最后一次出场(last_appearance ==
        # chapter_index)时,回填为剩余状态的最大章号(无则 NULL)。逐角色循环
        # 会产生 N+1(森林 I1),这里一条语句完成同样的语义。
        await db.execute(
            update(CharacterCard)
            .where(
                CharacterCard.id.in_(character_ids),
                CharacterCard.last_appearance == chapter_index,
            )
            .values(
                last_appearance=select(func.max(CharacterChapterState.chapter_index))
                .where(
                    CharacterChapterState.character_id == CharacterCard.id,
                    CharacterChapterState.storyline_id == CHARACTER_STORYLINE_MAIN,
                )
                .scalar_subquery()
            )
        )
        await db.execute(
            update(CharacterArc)
            .where(
                CharacterArc.project_id == pid,
                CharacterArc.storyline_id == CHARACTER_STORYLINE_MAIN,
                CharacterArc.anchor_chapter >= chapter_index,
            )
            .values(anchor_chapter=max(0, chapter_index - 1))
        )
        await db.execute(
            update(CharacterArc)
            .where(
                CharacterArc.project_id == pid,
                CharacterArc.storyline_id == CHARACTER_STORYLINE_MAIN,
                CharacterArc.target_chapter >= chapter_index,
            )
            .values(target_chapter=max(0, chapter_index - 1))
        )

    await db.execute(
        delete(CharacterRelationship).where(
            CharacterRelationship.project_id == pid,
            CharacterRelationship.valid_from_chapter >= chapter_index,
        )
    )
    await db.execute(
        update(CharacterRelationship)
        .where(
            CharacterRelationship.project_id == pid,
            CharacterRelationship.valid_to_chapter == chapter_index,
        )
        .values(valid_to_chapter=max(0, chapter_index - 1))
    )

    # Last-chapter deletion removes records produced by that chapter and
    # closes ranges that ended there. There are no later chapters to shift.
    for model in (NovelMemoryAtom, NovelMemoryConflict):
        await db.execute(
            delete(model).where(
                model.project_id == pid,
                model.branch_id.is_(None),
                model.source_chapter == chapter_index,
            )
        )
    await db.execute(
        delete(NovelMemoryEvidence).where(
            NovelMemoryEvidence.project_id == pid,
            NovelMemoryEvidence.branch_id.is_(None),
            NovelMemoryEvidence.source_chapter == chapter_index,
        )
    )
    for model in (NovelSceneBlock, ProjectDoctrine, NarrativeIndexEntry):
        await db.execute(
            delete(model).where(
                model.project_id == pid,
                model.branch_id.is_(None),
                model.source_chapter == chapter_index,
            )
        )
    await db.execute(
        delete(NarrativeIndexEntry).where(
            NarrativeIndexEntry.project_id == pid,
            NarrativeIndexEntry.branch_id.is_(None),
            NarrativeIndexEntry.chapter_index == chapter_index,
        )
    )
    for model in (
        NovelMemoryEvidence,
        NovelMemoryConflict,
        NovelMemoryAtom,
        NovelSceneBlock,
        ProjectDoctrine,
    ):
        await db.execute(
            update(model)
            .where(
                model.project_id == pid,
                model.branch_id.is_(None),
                model.valid_to_chapter == chapter_index,
            )
            .values(valid_to_chapter=max(0, chapter_index - 1))
        )
    await db.execute(
        update(NarrativeIndexEntry)
        .where(
            NarrativeIndexEntry.project_id == pid,
            NarrativeIndexEntry.branch_id.is_(None),
            NarrativeIndexEntry.valid_to_chapter == chapter_index,
        )
        .values(valid_to_chapter=max(0, chapter_index - 1))
    )
    await db.execute(
        update(NarrativeIndexEntry)
        .where(
            NarrativeIndexEntry.project_id == pid,
            NarrativeIndexEntry.branch_id.is_(None),
            NarrativeIndexEntry.chapter_end == chapter_index,
        )
        .values(chapter_end=max(0, chapter_index - 1))
    )
    await db.execute(
        delete(GraphEdge).where(
            GraphEdge.project_id == pid,
            GraphEdge.valid_from_chapter >= chapter_index,
        )
    )
    await db.execute(
        update(GraphEdge)
        .where(GraphEdge.project_id == pid, GraphEdge.valid_to_chapter == chapter_index)
        .values(valid_to_chapter=max(0, chapter_index - 1))
    )


async def renumber_chapters_after_deletion(
    db: AsyncSession,
    pid: uuid.UUID,
    chapter_index: int,
) -> None:
    await _renumber_after_deletion(db, Chapter, pid, chapter_index)


async def update_novel_stats_after_delete(
    db: AsyncSession,
    pid: uuid.UUID,
    novel,
) -> int:
    count_res = await db.execute(
        select(func.count()).select_from(Chapter).where(Chapter.novel_id == pid)
    )
    written_count = int(count_res.scalar() or 0)
    novel.current_chapter = written_count
    novel.total_chapters = written_count
    novel.total_chars = await sum_project_chars(db, pid)

    job_res = await db.execute(
        select(Job)
        .where(Job.project_id == pid, Job.type == JOB_TYPE_GENERATE)
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    job = job_res.scalar_one_or_none()
    if job and job.current_chapter and job.current_chapter > max(written_count, 1):
        job.current_chapter = max(written_count, 1)
    return written_count
