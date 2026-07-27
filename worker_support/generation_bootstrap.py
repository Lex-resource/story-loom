"""Bootstrap skeleton generation for new novels."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
import json
import inspect

from agents.constants import AGENT_PLANNER
from models.novel import Job, Novel
from services.job_payload import set_job_error, set_job_params
from services.pipeline_transitions import StateMachine
from services.pipeline_types import NovelStatus
from sqlalchemy.ext.asyncio import AsyncSession
from worker_support.events import GenerationEvents
from agents.constants import NOVEL_FORMAT_ZHIHU_SHORT


class BootstrapOutcome(StrEnum):
    NOT_NEEDED = "not_needed"
    CONTINUE = "continue"
    WAITING_FOR_REVIEW = "waiting_for_review"
    FAILED = "failed"


def should_bootstrap_skeleton(job_params: dict[str, Any], novel: Novel) -> bool:
    return bool(job_params.get("bootstrap_skeleton") and not novel.outline)


def skeleton_prompt(job_params: dict[str, Any], novel: Novel) -> str:
    user_prompt = job_params.get("user_prompt", "")
    title = job_params.get("title") or novel.title or ""
    profile = job_params.get("creative_profile") or getattr(novel, "creative_profile", None) or {}
    profile_hint = (
        f"\n创作参数：{json.dumps(profile, ensure_ascii=False)}"
        if profile else ""
    )
    if not title:
        return f"{user_prompt}{profile_hint}"
    return f"书名：《{title}》\n用户需求：{user_prompt}{profile_hint}"


async def bootstrap_skeleton_outline(
    db: AsyncSession,
    job: Job,
    novel: Novel,
    job_params: dict[str, Any],
    planner_node,
    events: GenerationEvents,
) -> BootstrapOutcome:
    if not should_bootstrap_skeleton(job_params, novel):
        return BootstrapOutcome.NOT_NEEDED

    async def on_chunk(channel: str, chunk: str) -> None:
        if channel != "llm":
            return
        await events.chunk("planner", 0, chunk, phase="skeleton")

    await events.status(AGENT_PLANNER, 0, "策划智能体正在生成整书骨架大纲…")

    try:
        novel.status = NovelStatus.GENERATING
        job.current_step = AGENT_PLANNER
        job.current_chapter = 0
        await db.commit()

        generate_skeleton = planner_node.agent.generate_skeleton_outline
        supported = inspect.signature(generate_skeleton).parameters
        generate_kwargs = {
            "novel_format": novel.novel_format,
            "on_chunk": on_chunk,
        }
        if "total_chapters" in supported:
            generate_kwargs["total_chapters"] = getattr(novel, "target_chapters", 0) or 0
        if "reference_style" in supported:
            generate_kwargs["reference_style"] = job_params.get("reference_style", "")
        skeleton = await generate_skeleton(
            skeleton_prompt(job_params, novel),
            **generate_kwargs,
        )
        await planner_node.agent.record_usage(db, novel.id, 0, AGENT_PLANNER)
        novel.outline = skeleton
        if novel.novel_format == NOVEL_FORMAT_ZHIHU_SHORT:
            from services.short_story_living_docs import sync_short_story_living_docs
            await sync_short_story_living_docs(db, novel)
        job_params["bootstrap_skeleton"] = False

        if novel.mode != "auto":
            await _pause_for_outline_review(db, job, novel, job_params, events)
            return BootstrapOutcome.WAITING_FOR_REVIEW

        await _continue_after_bootstrap(db, job, job_params, events)
        return BootstrapOutcome.CONTINUE
    except Exception as exc:
        await _fail_bootstrap(db, job, novel, job_params, events, exc)
        return BootstrapOutcome.FAILED


async def _pause_for_outline_review(
    db: AsyncSession,
    job: Job,
    novel: Novel,
    job_params: dict[str, Any],
    events: GenerationEvents,
) -> None:
    job_params["await_outline_review"] = True
    set_job_params(job, job_params)
    StateMachine.pause_job(job)
    job.current_step = AGENT_PLANNER
    job.current_chapter = 1
    novel.status = NovelStatus.PAUSED
    await db.commit()
    await events.log("策划器", "整书骨架大纲已生成，请审阅后点击「继续创作」开始章节策划。")
    await events.status(AGENT_PLANNER, 0, "整书骨架大纲已就绪，等待审阅…")


async def _continue_after_bootstrap(
    db: AsyncSession,
    job: Job,
    job_params: dict[str, Any],
    events: GenerationEvents,
) -> None:
    job_params["await_outline_review"] = False
    set_job_params(job, job_params)
    job.current_step = AGENT_PLANNER
    job.current_chapter = 1
    await db.commit()
    await events.log("策划器", "全自动模式：整书骨架大纲已生成，即将开始连续生成章节。")


async def _fail_bootstrap(
    db: AsyncSession,
    job: Job,
    novel: Novel,
    job_params: dict[str, Any],
    events: GenerationEvents,
    exc: Exception,
) -> None:
    novel.status = NovelStatus.PAUSED
    StateMachine.fail_job(job)
    set_job_params(job, job_params)
    set_job_error(job, f"骨架大纲生成失败: {exc}")
    await db.commit()
    await events.error(f"骨架大纲生成失败: {exc}")
