"""Post-processing entry flow for generated chapters."""

from __future__ import annotations

from agents.constants import AGENT_EXTRACTOR
from services.pipeline_transitions import set_chapter_pipeline_step, set_job_step
from services.pipeline_types import ChapterStatus, NovelStatus, PipelineStep
from sqlalchemy.ext.asyncio import AsyncSession
from worker_support.events import GenerationEvents
from services.knowledge_merger import run_post_processing


async def run_chapter_post_processing(
    db: AsyncSession,
    job,
    novel,
    chapter,
    chapter_index: int,
    *,
    has_extractor: bool,
    enable_living_docs_update: bool = True,
    check_paused,
    events: GenerationEvents,
) -> None:
    await check_paused(db, job.id)
    chapter.status = "post_processing"
    set_chapter_pipeline_step(chapter, PipelineStep.EXTRACTING)
    await db.commit()

    run_extractor = has_extractor and enable_living_docs_update
    if run_extractor:
        await check_paused(db, job.id)
        set_job_step(job, "extractor", chapter)
        await db.commit()
        await events.status(AGENT_EXTRACTOR, chapter_index, "正在提取世界观、人物及剧情设定更新...")
    else:
        await events.status("post_processing", chapter_index, "正在执行章节发布后处理...")

    await run_post_processing(db, novel.id, chapter_index, run_extractor=run_extractor)
    await db.refresh(chapter)
    if chapter.status == ChapterStatus.PENDING_REVIEW:
        novel.status = NovelStatus.PAUSED
        job.status = "paused"
        job.current_step = "extractor"
        await db.commit()
        await events.status(
            AGENT_EXTRACTOR,
            chapter_index,
            "设定提取器发现高风险知识变更，已暂停等待人工复核。",
        )
