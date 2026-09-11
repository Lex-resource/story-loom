from __future__ import annotations

from typing import Optional

from services import pipeline_ordering
from services.pipeline_types import (
    CHAPTER_STATUS_BY_PIPELINE_STEP,
    JOB_STEP_TO_PIPELINE_STEP,
    PIPELINE_ORDER,
    ChapterStatus,
    JobStatus,
    NovelStatus,
    PipelineStep,
    PipelineTransition,
)


class PipelineStateError(ValueError):
    pass


def pipeline_step_for_job_step(job_step: Optional[str]) -> Optional[str]:
    if not job_step:
        return None
    return JOB_STEP_TO_PIPELINE_STEP.get(job_step, job_step)


def chapter_status_for_pipeline_step(pipeline_step: Optional[str]) -> Optional[str]:
    if not pipeline_step:
        return None
    return CHAPTER_STATUS_BY_PIPELINE_STEP.get(pipeline_step)


def coerce_pipeline_step(step: Optional[str]) -> Optional[PipelineStep]:
    if not step:
        return None
    try:
        return PipelineStep(step)
    except ValueError as exc:
        raise PipelineStateError(f"Unknown pipeline step: {step}") from exc


def validate_pipeline_transition(
    current_step: Optional[str],
    next_step: str,
    *,
    allow_resume: bool = False,
    pipeline_order: Optional[list[PipelineStep]] = None,
) -> None:
    """Validate that *next_step* does not move the pipeline backward."""
    current = coerce_pipeline_step(current_step)
    target = coerce_pipeline_step(pipeline_step_for_job_step(next_step) or next_step)
    if current is None or target is None or allow_resume:
        return
    if pipeline_order is not None:
        order = pipeline_order
    else:
        ctx_order = pipeline_ordering.get_pipeline_order()
        order = ctx_order if ctx_order is not None else PIPELINE_ORDER
    try:
        current_index = order.index(current)
        target_index = order.index(target)
    except ValueError as exc:
        raise PipelineStateError(
            f"Pipeline step transition {current} -> {target} is not allowed by current pipeline order: {order}"
        ) from exc
    if target_index < current_index:
        raise PipelineStateError(f"Cannot move pipeline backward from {current} to {target}")


def set_job_step(
    job,
    job_step: str,
    chapter=None,
    *,
    allow_resume: bool = False,
    pipeline_order: Optional[list[PipelineStep]] = None,
) -> PipelineTransition:
    pipeline_step = pipeline_step_for_job_step(job_step) or job_step
    if chapter is not None:
        validate_pipeline_transition(
            getattr(chapter, "pipeline_step", None),
            pipeline_step,
            allow_resume=allow_resume,
            pipeline_order=pipeline_order,
        )
    job.current_step = job_step
    if chapter is not None:
        chapter.pipeline_step = pipeline_step
    return PipelineTransition(
        job_step=job_step,
        chapter_step=pipeline_step,
        chapter_status=chapter_status_for_pipeline_step(pipeline_step),
    )


def set_chapter_pipeline_step(chapter, pipeline_step: str, update_status: bool = True) -> None:
    coerce_pipeline_step(pipeline_step)
    chapter.pipeline_step = pipeline_step
    if update_status:
        status = chapter_status_for_pipeline_step(pipeline_step)
        if status:
            chapter.status = status


def publish_chapter_state(chapter) -> None:
    chapter.pipeline_step = PipelineStep.PUBLISHED
    chapter.status = ChapterStatus.PUBLISHED


def transition_job_step(job, chapter, next_step: str, *, allow_resume: bool = False) -> PipelineTransition:
    return set_job_step(job, next_step, chapter, allow_resume=allow_resume)


def pause_job(job, novel=None) -> None:
    job.status = JobStatus.PAUSED
    if novel is not None:
        novel.status = NovelStatus.PAUSED


def complete_chapter(job, chapter) -> None:
    publish_chapter_state(chapter)
    job.status = JobStatus.COMPLETED


def validate_state_consistency(job, chapter=None, novel=None) -> None:
    job_status = getattr(job, "status", None)
    current_step = getattr(job, "current_step", None)
    if job_status == JobStatus.RUNNING and chapter is not None and not getattr(chapter, "pipeline_step", None):
        raise PipelineStateError("Running jobs require chapter.pipeline_step")
    if current_step and chapter is not None:
        expected = pipeline_step_for_job_step(current_step)
        actual = getattr(chapter, "pipeline_step", None)
        if expected and actual and expected != actual:
            raise PipelineStateError(f"Job step {current_step} is inconsistent with chapter step {actual}")
    if chapter is not None and getattr(chapter, "pipeline_step", None) == PipelineStep.PUBLISHED:
        status = getattr(chapter, "status", None)
        if status != ChapterStatus.PUBLISHED:
            raise PipelineStateError("Published chapter pipeline step requires chapter.status='published'")
    if novel is not None and getattr(novel, "status", None) == NovelStatus.COMPLETED and job_status == JobStatus.RUNNING:
        raise PipelineStateError("Completed novels cannot have running jobs")


class StateMachine:
    @staticmethod
    def transition_to(job, next_step: str, chapter=None, novel=None, allow_resume: bool = False) -> Optional[PipelineTransition]:
        if next_step == JobStatus.PAUSED:
            pause_job(job, novel)
            return None
        if next_step == JobStatus.FAILED:
            StateMachine.fail_job(job, chapter, novel)
            return None

        job.status = JobStatus.RUNNING
        transition = transition_job_step(job, chapter, next_step, allow_resume=allow_resume)
        if chapter:
            status = chapter_status_for_pipeline_step(transition.chapter_step)
            if status:
                chapter.status = status
        if novel and novel.status != NovelStatus.GENERATING:
            novel.status = NovelStatus.GENERATING

        validate_state_consistency(job, chapter, novel)
        return transition

    @staticmethod
    def fail_job(job, chapter=None, novel=None, error: str = ""):
        if job.status in (JobStatus.PAUSED, JobStatus.CANCELLED):
            return
        job.status = JobStatus.FAILED
        if error:
            from services.job_payload import set_job_error

            set_job_error(job, error)
        if chapter:
            chapter.status = ChapterStatus.FAILED
            if error:
                chapter.error = error
        if novel:
            novel.status = NovelStatus.FAILED
        validate_state_consistency(job, chapter, novel)

    @staticmethod
    def pause_job(job, chapter=None, novel=None):
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            return
        job.status = JobStatus.PAUSED
        if novel:
            novel.status = NovelStatus.PAUSED
        validate_state_consistency(job, chapter, novel)

    @staticmethod
    def cancel_job(job, chapter=None, novel=None):
        """取消任务(worker 控制端点用)。

        generate 任务的 novel 离开 GENERATING 置 PAUSED(与 pause 同语义,
        项目可从锚点恢复);**不动 current_step** —— 保留 resume 锚点语义,
        不引入新取值。
        """
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            return
        job.status = JobStatus.CANCELLED
        if novel and novel.status == NovelStatus.GENERATING:
            novel.status = NovelStatus.PAUSED
        validate_state_consistency(job, chapter, novel)

    @staticmethod
    def complete_job(job, chapter=None, novel=None):
        if job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
            return
        job.status = JobStatus.COMPLETED
        if novel and novel.status != NovelStatus.PAUSED:
            novel.status = NovelStatus.COMPLETED
        validate_state_consistency(job, chapter, novel)

    @staticmethod
    def set_novel_generating(novel) -> None:
        novel.status = NovelStatus.GENERATING

    @staticmethod
    def set_novel_paused(novel) -> None:
        novel.status = NovelStatus.PAUSED

    @staticmethod
    def set_novel_completed(novel) -> None:
        novel.status = NovelStatus.COMPLETED
