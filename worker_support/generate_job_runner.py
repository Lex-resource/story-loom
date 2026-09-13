"""章节生成流程主逻辑：单章生成 + 批量调度。

本模块由 worker_support/orchestrator.py 调度。orchestrator 负责 Job 轮询、并发槽位、
状态流转封装；本模块负责单章 planner -> writer -> editor -> validator -> extractor
的流水线执行，以及批量 generate 任务的循环。

异常类 JobAbortedException / JobPausedException 由 generation_exceptions 定义，被
orchestrator.check_paused 抛出，由单章/批量流程捕获处理。
"""
from __future__ import annotations

import asyncio

from services.settings_store import load_settings
from sqlalchemy.ext.asyncio import AsyncSession

from agents.constants import (
    AGENT_EDITOR,
    AGENT_EXTRACTOR,
    AGENT_PLANNER,
    AGENT_VALIDATOR,
    AGENT_WRITER,
)
from models.novel import (
    Job,
)
from services.chapter_graph import ChapterGraph, default_graph
from services.job_payload import (
    get_job_params,
)
from services.pipeline_transitions import (
    StateMachine,
    set_job_step,
)
from services.pipeline_types import ChapterStatus
from worker_support import chapter_steps as steps
from worker_support.chapter_graph_runner import (
    OUTCOME_PAUSE,
    OUTCOME_RETRY,
    run_chapter_graph,
)
from core.chapter_domain import mainline_domain
from worker_support.chapter_repository import (
    get_chapter_by_index,
    prepare_chapter_for_step,
)
from worker_support.chapter_run_state import ChapterRunState
from worker_support.events import GenerationEvents
from worker_support.generation_exceptions import JobAbortedException, JobPausedException
from worker_support.generation_start_policy import (
    initial_generation_loop_state,
    resolve_generation_start_state,
    should_resume_extractor,
)
from worker_support.pipeline_runtime import load_generation_pipeline_runtime
from worker_support.generation_planner_flow import prepare_planner_inputs
from services.experiment_recorder import (
    activate,
    context_from_job,
    code_snapshot,
    adeactivate,
    arecord_run_manifest,
    provider_snapshot,
    record_chapter_finished,
)


# ---------------------------------------------------------------------------
# Single chapter pipeline
# ---------------------------------------------------------------------------

async def _process_single_chapter(
    db: AsyncSession,
    job: Job,
    novel,
    next_chapter: int,
    attempt: int = 1,
    *,
    experiment=None,
):
    """跑完一章：planner -> writer -> editor -> validator -> extractor。

    编排在这里，每一步做什么在 ``worker_support/chapter_steps.py``。本函数只做三件事：
    算出 resume 入口、按顺序调适配器、根据裁决决定下一步（回边 / 暂停 / 递归 / 发布）。

    状态跨阶段传递走 ``ChapterRunState``（黑板），不再用 30 个局部变量。

    状态中途被改成 paused/cancelled 时，散布各处的 check_paused 会抛
    JobPausedException / JobAbortedException。
    """
    # orchestrator <-> generate_job_runner 相互导入，只能函数内 lazy import。
    from worker_support.orchestrator import check_paused

    runtime = await load_generation_pipeline_runtime(db, novel.novel_format)

    await check_paused(db, job.id)
    job.current_chapter = next_chapter

    domain = mainline_domain(novel.id)
    chapter = await get_chapter_by_index(db, novel.id, next_chapter, domain=domain)
    if chapter and chapter.status == ChapterStatus.PENDING_REVIEW:
        job.current_step = chapter.pipeline_step or job.current_step or AGENT_EXTRACTOR
        StateMachine.pause_job(job, novel=novel)
        await db.commit()
        return

    start_state = resolve_generation_start_state(
        job,
        chapter,
        get_job_params(job),
        has_editor=runtime.has_editor,
    )
    start_step = start_state.start_step
    set_job_step(job, start_step, chapter, allow_resume=True)

    chapter = await prepare_chapter_for_step(db, chapter, novel.id, next_chapter, start_step, domain=domain)

    await db.commit()
    project_id_str = str(novel.id)
    events = GenerationEvents(project_id_str)

    state = ChapterRunState(
        db=db,
        job=job,
        novel=novel,
        chapter_index=next_chapter,
        attempt=attempt,
        runtime=runtime,
        events=events,
        project_id=project_id_str,
        start_step=start_step,
        use_existing_outline=start_state.use_existing_outline,
        custom_prompt=start_state.custom_prompt,
        prompt_category=getattr(runtime, "prompt_category", None),
        chapter=chapter,
        domain=domain,
    )
    _bind_stream_callbacks(state)

    if should_resume_extractor(start_step, chapter):
        # 失败或被中断的 extractor：正文早已写完并校验过，重跑 Writer 会改动有效正文。
        await check_paused(db, job.id)
        set_job_step(job, AGENT_EXTRACTOR, chapter, allow_resume=True)
        await db.commit()
        await steps.run_postprocess(state)
        return

    state.skeleton = novel.outline or {}

    await check_paused(db, job.id)

    # 记忆与议题摘要是所有阶段的共同输入，与图里有没有 planner 步骤无关 —— 无条件加载。
    planner_inputs = await prepare_planner_inputs(db, novel, next_chapter, state.custom_prompt)
    state.memory = planner_inputs.memory
    state.custom_prompt = planner_inputs.custom_prompt
    state.succeeding_beginning = planner_inputs.succeeding_beginning
    state.issue_summaries = planner_inputs.issue_summaries
    state.planner_previous_ending = planner_inputs.previous_ending

    # 循环状态必须在进图之前算好：图入口边的预算守卫读的就是 rewrite_count /
    # max_rewrites —— `skip_write_edit` 把 rewrite_count 顶到上限，于是 plan 的
    # 默认后继落到 on_exhausted，整个 write-edit 簇被跳过。
    loop_state = initial_generation_loop_state(
        chapter,
        start_step,
        max_rewrites=runtime.max_rewrites,
    )
    state.draft_content = loop_state.draft_content
    state.edited_content = loop_state.edited_content
    state.rewrite_count = loop_state.rewrite_count
    state.max_rewrites = loop_state.max_rewrites
    state.decision = loop_state.decision
    state.validation_errors = loop_state.validation_errors
    state.latest_validator_result = loop_state.latest_validator_result
    state.raw_issues = loop_state.raw_issues
    state.skip_write_edit = loop_state.skip_write_edit

    outcome = await run_chapter_graph(state, _graph_for_runtime(runtime))

    if outcome.kind == OUTCOME_PAUSE:
        job.current_step = outcome.anchor
        StateMachine.pause_job(job)
        await db.commit()
        return

    if outcome.kind == OUTCOME_RETRY:
        # 整章重跑。锚点设为 writer，于是恢复时复用大纲而不重烧一遍 planner。
        await check_paused(db, job.id)
        job.current_step = AGENT_WRITER
        await db.commit()
        return await process_single_chapter(
            db,
            job,
            novel,
            next_chapter,
            attempt + 1,
            _experiment=experiment,
        )


def _graph_for_runtime(runtime) -> ChapterGraph:
    """本次生成生效的拓扑图。

    工作流的 `graph` 列有内容时 `pipeline_runtime` 已经解析好挂在 runtime 上；为空时
    按 runtime 的开关构造默认图 —— 与改造前那段硬编码的 `while` + `if/elif` 等价，
    由 `tests/worker_support/test_generation_trace.py` 的 20 条序列逐项证明。
    """
    graph = getattr(runtime, "graph", None)
    if graph is not None:
        return graph
    return default_graph(
        has_editor=bool(runtime.has_editor),
        has_style_repair=bool(getattr(runtime, "has_style_repair", runtime.has_editor)),
        validation_before_editor=bool(runtime.validation_before_editor),
    )


def _bind_stream_callbacks(state: ChapterRunState) -> None:
    """把四个 agent 的流式回调绑到黑板上。

    每个回调只转发自己频道的 chunk —— 否则前端会把 Writer 的正文流塞进 Editor 面板。
    """
    events = state.events
    chapter_index = state.chapter_index

    async def planner_cb(channel: str, chunk: str):
        if channel != "llm":
            return
        await events.chunk(AGENT_PLANNER, chapter_index, chunk)

    async def writer_cb(channel: str, chunk: str):
        if channel != "llm":
            return
        await events.chunk(AGENT_WRITER, chapter_index, chunk)

    async def editor_cb(channel: str, chunk: str):
        if channel != "llm":
            return
        await events.chunk(AGENT_EDITOR, chapter_index, chunk)

    async def validator_cb(phase: str, text: str):
        if phase != "llm":
            return
        await events.chunk(AGENT_VALIDATOR, chapter_index, text, phase=phase)

    state.planner_cb = planner_cb
    state.writer_cb = writer_cb
    state.editor_cb = editor_cb
    state.validator_cb = validator_cb


async def process_single_chapter(
    db: AsyncSession,
    job: Job,
    novel,
    next_chapter: int,
    attempt: int = 1,
    *,
    _experiment=None,
):
    """Run a chapter with one recorder context across in-job retries.

    A Validator retry is part of the same chapter attempt, not a new chapter
    segment. Reusing the context keeps elapsed time, tokens, and retry counts
    cumulative and prevents recursive attempts from writing duplicate
    ``chapter_finished`` events. A resumed Job still creates a new context, so
    the publication reconciler can preserve genuine cross-Job segments.
    """
    is_root_attempt = _experiment is None
    experiment = _experiment or context_from_job(job, novel.id, next_chapter)
    token = activate(experiment) if is_root_attempt else None
    completed = False
    try:
        if experiment and is_root_attempt:
            app_settings = await load_settings()
            active_id = app_settings.get("active_provider_id")
            active_provider = next(
                (
                    provider
                    for provider in app_settings.get("providers", [])
                    if provider.get("id") == active_id
                ),
                None,
            )
            await arecord_run_manifest(
                {
                    "provider": provider_snapshot(active_provider),
                    # git diff --binary 可能扫描几万文件的仓库，同步跑会冻结事件循环
                    "code": await asyncio.to_thread(code_snapshot),
                    "backup_provider_id": app_settings.get("backup_provider_id"),
                    "attempt": attempt,
                }
            )
        result = await _process_single_chapter(
            db,
            job,
            novel,
            next_chapter,
            attempt,
            experiment=experiment,
        )
        completed = True
        if experiment and is_root_attempt:
            job_status = str(getattr(job, "status", "") or "")
            novel_status = str(getattr(novel, "status", "") or "")
            status = "completed"
            if job_status in {"paused", "failed", "cancelled"} or novel_status == "paused":
                status = job_status or novel_status
            record_chapter_finished(
                status=status,
                rewrite_count=experiment.content_retry_count,
                extra={
                    "pipeline_attempt": attempt,
                    "job_status": job_status,
                    "novel_status": novel_status,
                },
            )
        return result
    except JobPausedException:
        if experiment and is_root_attempt:
            record_chapter_finished(
                status="paused",
                rewrite_count=experiment.content_retry_count,
                extra={"pipeline_attempt": attempt},
            )
        raise
    except JobAbortedException:
        if experiment and is_root_attempt:
            record_chapter_finished(
                status="aborted",
                rewrite_count=experiment.content_retry_count,
                extra={"pipeline_attempt": attempt},
            )
        raise
    except Exception:
        if experiment and is_root_attempt:
            record_chapter_finished(
                status="error",
                rewrite_count=experiment.content_retry_count,
                extra={"pipeline_attempt": attempt},
            )
        raise
    finally:
        if experiment and is_root_attempt and not experiment.chapter_finished_recorded:
            record_chapter_finished(
                status="completed" if completed else "error",
                rewrite_count=experiment.content_retry_count,
                extra={
                    "pipeline_attempt": attempt,
                    "recording_fallback": True,
                },
            )
        if token is not None:
            await adeactivate(token)
