"""Branch generation job integration using the existing Planner/Writer nodes."""

from __future__ import annotations

import copy
import json
import logging
import uuid
from config import settings

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.constants import AGENT_EXTRACTOR
from agents.pipeline_context import PipelineContext
from database import async_session
from core.chapter_domain import ChapterDomain
from models.character_branches import CharacterBranch, CharacterBranchChapter
from models.novel import Job, Novel
from services.character_branch_service import get_character_branch
from services.knowledge_patch_models import KnowledgePatchSet
from services.novel_memory_atoms import record_patch_atoms
from services.novel_memory_evidence import capture_chapter_extractor_evidence
from services.novel_memory_recall import recall_novel_memory
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


async def apply_branch_chapter_memory(
    db: AsyncSession,
    *,
    novel: Novel,
    branch: CharacterBranch,
    chapter: CharacterBranchChapter,
    context: PipelineContext,
) -> list:
    """支线域记忆提取(森林 E4):与主链同一提取器,写入支线域。

    证据 + 候选原子;跳过角色卡/教义/叙事索引——权威模型不变。
    提取失败不阻塞支线发布(advisory 哲学),返回支线域候选原子。
    """
    extractor_output = None
    if settings.ENABLE_NOVEL_MEMORY_ATOMS:
        try:
            from agents.pipeline import ExtractorNode

            extraction_context = copy.copy(context)
            extraction_context.chapter_content = chapter.content or ""
            extractor_node = ExtractorNode()
            extractor_output = await extractor_node.run(
                extraction_context, {"content": chapter.content}
            )
            await extractor_node.agent.record_usage(
                db, novel.id, chapter.chapter_index, AGENT_EXTRACTOR
            )
        except Exception:
            logger.exception(
                "branch_memory_extraction_failed branch_id=%s chapter_index=%s",
                branch.id,
                chapter.chapter_index,
            )
    branch_atoms: list = []
    if extractor_output is not None:
        evidence = None
        if settings.ENABLE_NOVEL_MEMORY_EVIDENCE:
            evidence = await capture_chapter_extractor_evidence(
                db,
                project_id=novel.id,
                branch_id=branch.id,
                storyline_id=branch.storyline_id,
                chapter_index=chapter.chapter_index,
                chapter_content=chapter.content or "",
                extractor_output=extractor_output,
            )
        if settings.ENABLE_NOVEL_MEMORY_ATOMS:
            branch_atoms = await record_patch_atoms(
                db,
                project_id=novel.id,
                chapter_index=chapter.chapter_index,
                patch_set=KnowledgePatchSet.model_validate(extractor_output),
                evidence_id=evidence.id if evidence is not None else None,
                branch_id=branch.id,
                storyline_id=branch.storyline_id,
            )
    return branch_atoms
