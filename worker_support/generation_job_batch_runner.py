from __future__ import annotations

import traceback

from sqlalchemy.ext.asyncio import AsyncSession

from agents.base import LLMJSONParsingError
from models.novel import Job
from services.job_payload import append_job_error, get_job_params
from services.pipeline_transitions import StateMachine
from services.pipeline_types import NovelStatus
from services.stream_manager import stream_manager
from worker_support.events import GenerationEvents
from worker_support.generation_batch import (
    backup_project_after_chapter,
    batch_size_from_params,
    decrement_remaining_chapters,
    find_next_chapter_for_job,
    get_novel_for_job,
    reset_job_for_next_chapter,
    set_agent_chapter,
    update_novel_status_on_finished,
)
from worker_support.generation_bootstrap import BootstrapOutcome, bootstrap_skeleton_outline
from worker_support.generation_exceptions import JobPausedException
from worker_support.generation_nodes import (
    editor,
    extractor,
    planner,
    validator_agent,
    writer,
)
from worker_support.generate_job_runner import process_single_chapter
from worker_support.json_error_recovery import JSONErrorRecoveryOutcome, handle_json_parsing_error


async def process_generate_job(db: AsyncSession, job: Job) -> None:
    novel = await get_novel_for_job(db, job)
    if not novel:
        raise Exception("Novel not found")

    job_params: dict = get_job_params(job)
    project_id_str = str(novel.id)
    events = GenerationEvents(project_id_str)

    bootstrap_outcome = await bootstrap_skeleton_outline(
        db,
        job,
        novel,
        job_params,
        planner,
        events,
    )
    if bootstrap_outcome in {BootstrapOutcome.WAITING_FOR_REVIEW, BootstrapOutcome.FAILED}:
        return

    is_first_iteration = True
    chapters_written = 0
    batch_size = batch_size_from_params(job_params)
    json_error_retries: dict[int, int] = {}

    while True:
        next_chapter = await find_next_chapter_for_job(
            db,
            job,
            novel,
            is_first_iteration=is_first_iteration,
        )
        is_first_iteration = False

        set_agent_chapter(
            [planner, writer, editor, extractor, validator_agent],
            next_chapter,
        )

        if novel.target_chapters and next_chapter > novel.target_chapters:
            novel.status = NovelStatus.COMPLETED
            StateMachine.complete_job(job)
            await db.commit()
            return

        await db.refresh(job)
        if job.status == "paused":
            return

        try:
            await process_single_chapter(db, job, novel, next_chapter)
            await db.refresh(novel)
            await db.refresh(job)

            if novel.status == "paused" or job.status in ["paused", "failed", "completed"]:
                if job.status == "paused" and novel.status != "paused":
                    novel.status = NovelStatus.PAUSED
                    await db.commit()
                break

            await backup_project_after_chapter(novel.id)

            await reset_job_for_next_chapter(db, job, next_chapter)
            await decrement_remaining_chapters(db, job)

            chapters_written += 1
            if chapters_written >= batch_size:
                await update_novel_status_on_finished(db, novel)
                StateMachine.complete_job(job, novel=novel)
                await db.commit()
                break
        except JobPausedException:
            break
        except LLMJSONParsingError as exc:
            retry_count = json_error_retries.get(next_chapter, 0) + 1
            json_error_retries[next_chapter] = retry_count
            outcome = await handle_json_parsing_error(
                db,
                job,
                novel,
                next_chapter,
                retry_count,
                exc,
                events,
            )

            if outcome == JSONErrorRecoveryOutcome.RETRY:
                continue

            if outcome == JSONErrorRecoveryOutcome.RECOVERED:
                chapters_written += 1
                continue

            break
        except Exception as exc:
            StateMachine.fail_job(job)
            append_job_error(job, str(exc), traceback=traceback.format_exc())
            novel.status = NovelStatus.PAUSED
            await db.commit()
            try:
                await stream_manager.broadcast(
                    str(novel.id), "error",
                    {"message": f"创作流异常中断: {exc}"},
                )
            except Exception:
                pass
            raise
