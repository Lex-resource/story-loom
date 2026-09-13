"""支线生成的图引擎执行流(森林 E5)。

支线 job 与主线共用同一图解释器(`run_chapter_graph`)与同一套角色适配器,
拓扑为支线子图(`branch_default_graph`:plan→draft→review→final→publish→post)。
域隔离:章节落 `character_branch_chapters`,记忆提取写支线域;
主线锚点记忆由创建时冻结的 `anchor_context` 静态承担。
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from config import settings
from core.chapter_domain import ChapterDomain
from core.character_vocab import (
    CHARACTER_BRANCH_CHAPTER_STATUS_DRAFT,
    CHARACTER_BRANCH_CHAPTER_STATUS_FAILED,
    CHARACTER_BRANCH_CHAPTER_STATUS_GENERATING,
    CHARACTER_BRANCH_CHAPTER_STATUS_READY,
    CHARACTER_BRANCH_STATUS_DRAFT,
    CHARACTER_BRANCH_STATUS_FAILED,
    CHARACTER_BRANCH_STATUS_READY,
)
from core.pipeline_vocab import JobStatus
from models.novel import Job, Novel
from services.character_branch_generation import (
    BranchJobAborted,
    _branch_checkpoint,
    _branch_context,
    _broadcast,
    apply_branch_chapter_memory,
)
from services.character_branch_service import (
    create_or_get_branch_chapter,
    get_branch_chapter,
    get_character_branch,
)
from services.character_branch_vector_service import enqueue_branch_chapter_vector
from services.novel_memory_consolidation import consolidate_scene_summary
from services.novel_memory_evidence import capture_branch_generation_evidence
from services.novel_memory_scenes import aggregate_scene_block, fallback_scene_summary
from worker_support.chapter_graph_runner import run_chapter_graph
from worker_support.chapter_run_state import ChapterRunState
from worker_support.events import GenerationEvents
from worker_support.generation_planner_flow import prepare_planner_inputs
from worker_support.pipeline_runtime import load_generation_pipeline_runtime

logger = logging.getLogger(__name__)


async def process_character_branch_job(
    db: AsyncSession,
    job: Job,
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
            context.chapter_content = chapter.content or ""
            if settings.ENABLE_NOVEL_MEMORY_RECALL:
                # A2:支线自身累积记忆的召回(锚点前的主线记忆已冻结在
                # anchor_context);后续续写章节据此看到前几章支线事实。
                recall = await recall_novel_memory(
                    db,
                    project_id=novel.id,
                    chapter_index=next_index,
                    agent_type="writer",
                    branch_id=branch.id,
                    storyline_id=branch.storyline_id,
                    query_text=str(chapter.title or ""),
                )
                context.novel_memory_context = recall.context
            await _broadcast(branch, f"正在生成支线第{next_index}章")

            # E5:支线 job 走与主线同一图引擎(数据库工作流拓扑的支线子图)。
            domain = ChapterDomain(
                project_id=novel.id,
                branch_id=branch.id,
                storyline_id=branch.storyline_id,
                anchor_main_chapter=branch.anchor_main_chapter,
            )
            runtime = await load_generation_pipeline_runtime(db, novel.novel_format)
            planner_inputs = await prepare_planner_inputs(
                db,
                novel,
                next_index,
                None,
                domain=domain,
                previous_ending_override=context.previous_ending,
            )
            from worker_support.generate_job_runner import _bind_stream_callbacks
            from worker_support.chapter_graph_runner import run_chapter_graph
            from services.chapter_graph import branch_default_graph

            state = ChapterRunState(
                db=db,
                job=job,
                novel=novel,
                chapter_index=next_index,
                attempt=0,
                runtime=runtime,
                events=GenerationEvents(str(novel.id)),
                project_id=str(novel.id),
                start_step="planner",
                chapter=chapter,
                domain=domain,
                pipeline_context=context,
                memory=planner_inputs.memory,
                skeleton=context.global_outline,
                issue_summaries=planner_inputs.issue_summaries,
                planner_previous_ending=planner_inputs.previous_ending,
                succeeding_beginning=planner_inputs.succeeding_beginning,
                use_existing_outline=False,
                custom_prompt=None,
            )
            _bind_stream_callbacks(state)

            outcome = await run_chapter_graph(
                state, branch_default_graph(max_rewrites=runtime.max_rewrites)
            )

            if outcome.decision == "blocked":
                chapter.status = CHARACTER_BRANCH_CHAPTER_STATUS_FAILED
                chapter.error = outcome.validation_errors or "支线章节被工作流拦截"
                branch.status = CHARACTER_BRANCH_STATUS_FAILED
                job.status = JobStatus.FAILED
                job.error = chapter.error
                await db.commit()
                await _broadcast(branch, chapter.error, status=branch.status)
                return

            chapter = state.chapter
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
            branch_atoms = (state.domain_artifacts or {}).get("branch_atoms", [])
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
                        branch_summary = fallback_scene_summary(chapter.outline, chapter.content)
                        if settings.ENABLE_SCENE_BLOCK_CONSOLIDATION:
                            branch_summary = (
                                await consolidate_scene_summary(
                                    db, novel, chapter, branch_summary, accepted_atoms=branch_atoms,
                                )
                                or branch_summary
                            )
                        await aggregate_scene_block(
                            db,
                            project_id=novel.id,
                            branch_id=branch.id,
                            storyline_id=branch.storyline_id,
                            scope_type="character_arc",
                            scope_key=branch.storyline_id,
                            summary=branch_summary,
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
