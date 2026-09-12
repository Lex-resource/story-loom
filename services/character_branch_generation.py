"""Branch generation job integration using the existing Planner/Writer nodes."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import uuid
from config import settings
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.pipeline_context import PipelineContext
from database import async_session
from models.character_branches import CharacterBranch, CharacterBranchChapter
from models.novel import Job, Novel
from services.character_branch_service import (
    create_or_get_branch_chapter,
    get_branch_chapter,
    get_character_branch,
    transition_branch_status,
)
from services.character_branch_vector_service import enqueue_branch_chapter_vector
from services.novel_memory_evidence import capture_branch_generation_evidence
from services.novel_memory_scenes import aggregate_scene_block
from services.character_constants import (
    CHARACTER_BRANCH_CHAPTER_STATUS_FAILED,
    CHARACTER_BRANCH_CHAPTER_STATUS_GENERATING,
    CHARACTER_BRANCH_CHAPTER_STATUS_READY,
    CHARACTER_BRANCH_DEFAULT_WORD_COUNT,
    CHARACTER_BRANCH_STATUS_DRAFT,
    CHARACTER_BRANCH_STATUS_ARCHIVED,
    CHARACTER_BRANCH_STATUS_FAILED,
    CHARACTER_BRANCH_STATUS_READY,
)
from services.novel_constants import JOB_TYPE_CHARACTER_BRANCH
from services.pipeline_types import JobStatus
from services.stream_manager import stream_manager
from services.stream_events import STREAM_EVENT_CHARACTER_BRANCH


logger = logging.getLogger(__name__)


class BranchJobAborted(Exception):
    """The durable job or branch was stopped while an LLM call was running."""

    def __init__(self, status: str):
        self.status = status
        super().__init__(f"Branch job stopped with status {status}")


async def _branch_checkpoint(
    db: AsyncSession,
    job: Job,
    branch_id: uuid.UUID,
    character_id: uuid.UUID,
    *,
    lock: bool,
) -> CharacterBranch:
    status = (await db.execute(
        select(Job.status).where(Job.id == job.id)
    )).scalar_one_or_none()
    if status != JobStatus.RUNNING:
        job.status = status or JobStatus.CANCELLED
        raise BranchJobAborted(str(job.status))
    statement = select(CharacterBranch).where(
        CharacterBranch.id == branch_id,
        CharacterBranch.project_id == job.project_id,
        CharacterBranch.character_id == character_id,
    )
    if lock:
        statement = statement.with_for_update()
    branch = (await db.execute(statement)).scalar_one_or_none()
    if branch is None:
        raise LookupError("Branch or project not found")
    if branch.status == CHARACTER_BRANCH_STATUS_ARCHIVED:
        job.status = JobStatus.CANCELLED
        raise BranchJobAborted(JobStatus.CANCELLED)
    return branch


async def enqueue_branch_generation(
    project_id,
    character_id,
    branch_id,
    chapters: int,
    db: AsyncSession | None = None,
) -> Job:
    """Create a durable branch job; the normal worker claims it."""
    owns_session = db is None
    session = db or async_session()
    try:
        job = Job(
            project_id=project_id,
            type=JOB_TYPE_CHARACTER_BRANCH,
            status=JobStatus.PENDING,
            current_step="branch",
            params={
                "character_id": str(character_id),
                "branch_id": str(branch_id),
                "chapters": chapters,
            },
        )
        session.add(job)
        await session.flush()
        if owns_session:
            await session.commit()
        return job
    except Exception:
        if owns_session:
            await session.rollback()
        raise
    finally:
        if owns_session:
            await session.close()


def _branch_context(branch: CharacterBranch, chapter: CharacterBranchChapter, novel: Novel, previous: CharacterBranchChapter | None) -> PipelineContext:
    anchor = branch.anchor_context or {}
    character = copy.deepcopy(anchor.get("character") or {})
    branch_state = copy.deepcopy(previous.state_data if previous else {})
    if branch_state:
        character["state"] = branch_state
    card_data = character.get("card_data") or {}
    identity = card_data.get("identity") or {}
    skeleton = {
        "书名": str((novel.outline or {}).get("书名") or novel.title or ""),
        "类型": str((novel.outline or {}).get("类型") or "小说"),
        "风格": str((novel.outline or {}).get("风格") or "生动、连贯、符合人物设定"),
        "支线故事": True,
        "支线标题": branch.title,
        "支线章节序号": chapter.chapter_index,
        "主线锚点章节": branch.anchor_main_chapter,
        "续写位置": "上一章支线结束之后" if previous else "主线锚点章节结束之后",
        "支线续写规则": "不得复述或重写主线锚点章节，只能从锚点结束后的新时刻继续发展",
    }
    state_text = json.dumps(character, ensure_ascii=False, indent=2)
    historical_docs = anchor.get("historical_docs") or {}
    previous_ending = (
        (previous.content or previous.edited_content or previous.draft_content or "")[-3500:]
        if previous
        else anchor.get("anchor_chapter_ending", "")
    )
    return PipelineContext(
        project_id=str(novel.id),
        chapter_index=chapter.chapter_index,
        novel_format=novel.novel_format or "long_webnovel",
        genre=str(skeleton.get("类型") or "小说"),
        style=str(skeleton.get("风格") or ""),
        global_outline=skeleton,
        previous_ending=previous_ending,
        world_state=historical_docs.get("world_state", ""),
        raw_world_state=historical_docs.get("world_state", ""),
        character_state=state_text,
        raw_character_state=state_text,
        foreshadowing=historical_docs.get("foreshadowing", ""),
        raw_foreshadowing=historical_docs.get("foreshadowing", ""),
        plot_threads=historical_docs.get("plot_threads", ""),
        raw_plot_threads=historical_docs.get("plot_threads", ""),
        character_card_context=json.dumps({
            "branch_anchor": branch.anchor_main_chapter,
            "branch_chapter_index": chapter.chapter_index,
            "continuation_point": "previous_branch_chapter" if previous else "after_mainline_anchor",
            "do_not_recap_anchor": True,
            "character": character,
            "relationships": anchor.get("relationships", []),
            "arc": anchor.get("arc", {}),
            "branch_state": branch_state,
            "user_request": branch.user_request or "",
            "future_mainline_is_forbidden": True,
        }, ensure_ascii=False, indent=2),
        total_chapters=branch.target_chapters,
        word_count=int((branch.generation_config or {}).get("word_count") or CHARACTER_BRANCH_DEFAULT_WORD_COUNT),
    )


async def _broadcast(branch: CharacterBranch, message: str, *, status: str | None = None) -> None:
    data = {"branch_id": str(branch.id), "character_id": str(branch.character_id), "message": message}
    if status:
        data["branch_status"] = status
    try:
        await stream_manager.broadcast(str(branch.project_id), STREAM_EVENT_CHARACTER_BRANCH, data)
    except Exception:
        logger.exception("branch_event_broadcast_failed branch_id=%s", branch.id)


async def process_character_branch_job(
    db: AsyncSession,
    job: Job,
    *,
    planner_node,
    writer_node,
    editor_node,
    validator_node,
) -> None:
    params = job.params or {}
    branch_id = uuid.UUID(str(params["branch_id"]))
    character_id = uuid.UUID(str(params["character_id"]))
    requested = max(1, int(params.get("chapters") or 1))
    novel = (await db.execute(select(Novel).where(Novel.id == job.project_id))).scalar_one_or_none()
    if novel is None:
        raise LookupError("Branch or project not found")

    try:
        branch = await _branch_checkpoint(
            db, job, branch_id, character_id, lock=True
        )
        for _ in range(requested):
            if branch.current_chapter_index >= branch.target_chapters:
                break
            next_index = branch.current_chapter_index + 1
            previous_result = await db.execute(
                select(CharacterBranchChapter)
                .where(
                    CharacterBranchChapter.branch_id == branch.id,
                    CharacterBranchChapter.chapter_index == next_index - 1,
                )
            )
            previous = previous_result.scalar_one_or_none()
            chapter = await create_or_get_branch_chapter(db, branch, next_index)
            chapter.status = CHARACTER_BRANCH_CHAPTER_STATUS_GENERATING
            await db.flush()
            # Persist the resumable checkpoint and release the branch lock
            # before entering a potentially long LLM call.
            await db.commit()
            branch = await _branch_checkpoint(
                db, job, branch_id, character_id, lock=False
            )
            context = _branch_context(branch, chapter, novel, previous)
            await _broadcast(branch, f"正在规划支线第{next_index}章")

            planner_output = await planner_node.run(context, {"skeleton": context.global_outline})
            branch = await _branch_checkpoint(
                db, job, branch_id, character_id, lock=False
            )
            outline = planner_output.payload.get("chapter_outline") or {}
            chapter.outline = outline
            chapter.title = str(outline.get("title") or f"支线第{next_index}章")
            await db.flush()

            await _broadcast(branch, f"正在创作支线第{next_index}章")
            writer_output = await writer_node.run(
                context,
                {
                    "chapter_outline": outline,
                    "skeleton": context.global_outline,
                    "word_count": context.word_count,
                    "on_chunk": None,
                },
            )
            branch = await _branch_checkpoint(
                db, job, branch_id, character_id, lock=False
            )
            draft = writer_output.content
            chapter.draft_content = draft
            chapter.status = CHARACTER_BRANCH_CHAPTER_STATUS_GENERATING
            await db.flush()

            await _broadcast(branch, f"正在审阅支线第{next_index}章")
            editor_output = await editor_node.run(
                context,
                {
                    "chapter_outline": outline,
                    "draft_content": draft,
                    "enable_light_polish": False,
                },
            )
            branch = await _branch_checkpoint(
                db, job, branch_id, character_id, lock=False
            )
            editor_payload = editor_output.payload or {}
            edited = editor_payload.get("edited_content") or draft
            chapter.edited_content = edited
            chapter.content = edited
            chapter.word_count = len(edited)

            validation_context = copy.copy(context)
            validation_context.title = chapter.title
            validation_context.chapter_content = edited
            validator_output = await validator_node.run(
                validation_context,
                {"title": chapter.title, "content": edited},
            )
            branch = await _branch_checkpoint(
                db, job, branch_id, character_id, lock=True
            )
            chapter = await get_branch_chapter(db, branch.id, next_index, lock=True)
            if chapter is None:
                raise LookupError("Branch chapter not found")
            chapter.validator_result = validator_output.payload
            if not validator_output.passed:
                chapter.status = CHARACTER_BRANCH_CHAPTER_STATUS_FAILED
                chapter.error = "支线章节未通过一致性校验"
                branch.status = CHARACTER_BRANCH_STATUS_FAILED
                job.status = JobStatus.FAILED
                job.error = chapter.error
                await db.commit()
                await _broadcast(branch, chapter.error, status=branch.status)
                return

            chapter.state_data = {
                "last_observed_chapter": next_index,
                "end_state": outline.get("end_state", ""),
                "character_goals": copy.deepcopy(outline.get("character_goals", [])),
                "source": branch.storyline_id,
            }
            chapter.relationship_changes = copy.deepcopy(outline.get("relationship_changes", []))
            chapter.status = CHARACTER_BRANCH_CHAPTER_STATUS_READY
            chapter.error = None
            branch.current_chapter_index = next_index
            branch.status = CHARACTER_BRANCH_STATUS_DRAFT
            if settings.ENABLE_NOVEL_MEMORY_EVIDENCE:
                await capture_branch_generation_evidence(
                    db,
                    project_id=novel.id,
                    branch_id=branch.id,
                    storyline_id=branch.storyline_id,
                    chapter_index=next_index,
                    chapter_content=chapter.content or "",
                    generation_data={
                        "title": chapter.title,
                        "outline": outline,
                        "state_data": chapter.state_data,
                        "relationship_changes": chapter.relationship_changes,
                    },
                )
            if settings.ENABLE_NOVEL_MEMORY_SCENE_BLOCKS:
                try:
                    async with db.begin_nested():
                        await aggregate_scene_block(
                            db,
                            project_id=novel.id,
                            branch_id=branch.id,
                            storyline_id=branch.storyline_id,
                            scope_type="character_arc",
                            scope_key=branch.storyline_id,
                            summary=(chapter.outline or {}).get("summary") or (chapter.content or "")[:800],
                            current_state=chapter.state_data or {},
                            open_questions=(chapter.outline or {}).get("open_questions", []),
                            recent_changes=(chapter.relationship_changes or []),
                            source_ref=f"character_branch:{branch.id}:chapter:{next_index}:scene",
                            source_chapter=next_index,
                            valid_from_chapter=next_index,
                        )
                except Exception:
                    logger.exception(
                        "branch_scene_block_aggregation_failed branch_id=%s chapter_index=%s",
                        branch.id,
                        next_index,
                    )
            await enqueue_branch_chapter_vector(db, branch, chapter)
            await db.commit()
            await _broadcast(branch, f"支线第{next_index}章已完成", status=branch.status)
            branch = await _branch_checkpoint(
                db, job, branch_id, character_id, lock=True
            )

        branch.status = (
            CHARACTER_BRANCH_STATUS_READY
            if branch.current_chapter_index >= branch.target_chapters
            else CHARACTER_BRANCH_STATUS_DRAFT
        )
        job.status = JobStatus.COMPLETED
        await db.commit()
        await _broadcast(branch, "支线生成任务完成", status=branch.status)
    except BranchJobAborted as exc:
        await db.rollback()
        job.status = exc.status
        logger.info("branch_job_stopped job_id=%s status=%s", job.id, exc.status)
        return
    except Exception as exc:
        await db.rollback()
        latest_job = await db.get(Job, job.id)
        if latest_job is not None and latest_job.status != JobStatus.RUNNING:
            job.status = latest_job.status
            logger.info(
                "branch_job_failed_after_status_change job_id=%s status=%s",
                job.id,
                latest_job.status,
            )
            return
        branch = await get_character_branch(db, job.project_id, character_id, branch_id, lock=True)
        if branch is not None:
            if branch.status == CHARACTER_BRANCH_STATUS_ARCHIVED:
                if latest_job is not None:
                    latest_job.status = JobStatus.CANCELLED
                    await db.commit()
                job.status = JobStatus.CANCELLED
                return
            branch.status = CHARACTER_BRANCH_STATUS_FAILED
            branch.error = str(exc)[:1000]
            await db.commit()
            await _broadcast(branch, "支线生成失败", status=branch.status)
        raise
