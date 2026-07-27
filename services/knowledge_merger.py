import logging
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel import Novel, Chapter, LivingDocVersion, VectorOutbox
from agents.constants import NOVEL_FORMAT_ZHIHU_SHORT, AGENT_PLANNER, AGENT_EXTRACTOR
from agents.pipeline import ExtractorNode
from agents.pipeline_context import PipelineContext
from services import living_docs
from services.document_constants import ALL_DOC_TYPES
from services.novel_constants import CHAPTER_VERSION_DIR_TEMPLATE
from services.stream_constants import STREAM_SOURCE_EXTRACTOR
from services.knowledge_markdown import knowledge_to_markdown
from services.knowledge_frozen_facts import find_frozen_fact_violations
from services.knowledge_patch_models import KnowledgePatchSet
from services.knowledge_patch_service import apply_knowledge_patches
from services.pipeline_transitions import publish_chapter_state
from services.pipeline_types import ChapterStatus, VectorOutboxStatus
from services.project_stats import chapter_chars_from_row, sum_project_chars
from services.stream_manager import stream_manager
from services.knowledge_filtering import (
    get_filtered_world_state,
    get_filtered_foreshadowing,
    get_filtered_character_state,
)

logger = logging.getLogger(__name__)

SOFT_EXTRACTOR_RISK_TERMS = (
    "可能",
    "需后续",
    "后续验证",
    "待验证",
    "需确认",
    "需要确认",
    "动机不明",
    "可靠性低",
    "误读",
    "悬念",
    "伏笔",
    "不确定",
    "信息不足",
    "可疑",
)

HARD_EXTRACTOR_RISK_TERMS = (
    "明确冲突",
    "直接冲突",
    "硬冲突",
    "直接矛盾",
    "违反既有",
    "推翻既有",
    "覆盖既有",
    "删除既有",
    "生死状态冲突",
    "时间线硬冲突",
    "权限体系硬冲突",
)


def is_hard_extractor_issue(issue: dict) -> bool:
    """Return True only for extractor issues that should block publishing.

    Long-form fiction often uses ambiguity on purpose. Notes such as
    "动机不明", "可能是陷阱", or "需后续验证" are useful continuity hints, but
    they should not force a human checkpoint every chapter.
    """
    if not isinstance(issue, dict):
        return False
    if str(issue.get("severity", "")).lower() != "high":
        return False
    if str(issue.get("category", "")) == "frozen_fact":
        return True

    text = " ".join(
        str(issue.get(key, "") or "")
        for key in ("category", "description", "message", "detail")
    )
    if any(term in text for term in SOFT_EXTRACTOR_RISK_TERMS):
        return False
    return any(term in text for term in HARD_EXTRACTOR_RISK_TERMS)


def append_extractor_review_flag(
    chapter: Chapter,
    high_risk_issues: list[dict],
    patch_set: KnowledgePatchSet | None = None,
) -> None:
    flags = chapter.review_flags or []
    if not isinstance(flags, list):
        flags = []

    existing_descriptions = {
        issue.get("description")
        for flag in flags
        if isinstance(flag, dict) and flag.get("type") == "extractor_high_risk"
        for issue in (flag.get("issues") or [])
        if isinstance(issue, dict)
    }
    new_issues = [
        issue for issue in high_risk_issues
        if issue.get("description") not in existing_descriptions
    ]
    if not new_issues:
        return

    flag_entry = {
        "type": "extractor_high_risk",
        "severity": "warning",
        "message": "设定提取器发现高风险知识变更，需人工复核后发布。",
        "issues": new_issues,
    }
    if patch_set is not None:
        flag_entry["patch_set"] = patch_set.model_dump()
    chapter.review_flags = list(flags) + [flag_entry]


async def apply_extractor_updates(db: AsyncSession, novel: Novel, chapter: Chapter, extract_result: dict):
    """Apply extractor output to living docs, vector outbox, and chapter state.

    .. warning::
        This function calls ``await db.commit()`` on the caller's session.
        Any uncommitted changes the caller has accumulated will be committed
        together with the extractor updates. Callers that need to keep their
        own changes pending should commit (or rollback) before calling this
        function, or use a nested transaction (savepoint).

    After the commit, two best-effort background tasks run in independent
    try/except blocks so their failure does not roll back the extractor
    updates: (1) issue summary refresh, (2) periodic outline optimization.
    """
    chapter_index = chapter.chapter_index
    await stream_manager.broadcast(str(novel.id), "log", {"source": STREAM_SOURCE_EXTRACTOR, "message": "正在写入并更新最新的人物经历与状态卡..."})
    patch_set = KnowledgePatchSet.model_validate(extract_result)
    frozen_fact_issues = await find_frozen_fact_violations(str(novel.id), patch_set, db)
    high_risk_issues = [
        issue for issue in patch_set.raw_issues
        if is_hard_extractor_issue(issue)
    ]
    high_risk_issues = frozen_fact_issues + high_risk_issues
    if high_risk_issues:
        chapter.status = ChapterStatus.PENDING_REVIEW
        append_extractor_review_flag(chapter, high_risk_issues, patch_set)
        chapter.error = "设定提取器发现高风险知识变更，需人工复核后发布。"
        await db.commit()
        return

    patch_summary = await apply_knowledge_patches(str(novel.id), patch_set, db, chapter_index=chapter_index)
    vector_items = patch_summary.vector_items
    character_state_txt = knowledge_to_markdown(
        "character_state",
        await living_docs.read_knowledge(str(novel.id), "character_state", db),
    )
    if vector_items:
        outbox = VectorOutbox(
            project_id=novel.id, chapter_index=chapter_index,
            payload={"items": vector_items}, status=VectorOutboxStatus.PENDING
        )
        db.add(outbox)

    for doc_type in ALL_DOC_TYPES:
        checksum = await living_docs.snapshot_doc(str(novel.id), chapter_index, doc_type, db)
        if checksum:
            version = LivingDocVersion(
                project_id=novel.id, chapter_index=chapter_index,
                doc_type=doc_type,
                path=f"versions/{CHAPTER_VERSION_DIR_TEMPLATE.format(chapter_index)}/{doc_type}.md",
                checksum=checksum,
            )
            db.add(version)

    publish_chapter_state(chapter)
    novel.current_chapter = max(novel.current_chapter or 0, chapter_index)
    if (novel.total_chapters or 0) < chapter_index:
        novel.total_chapters = chapter_index
    word_count = chapter_chars_from_row(chapter)
    chapter.word_count = word_count
    novel.total_chars = await sum_project_chars(db, novel.id)
    await db.commit()

    try:
        from services.issues import update_project_issue_summaries
        await update_project_issue_summaries(db, novel.id)
    except Exception:
        logger.exception("issue_summary_refresh_failed project_id=%s chapter_index=%s", novel.id, chapter_index)

    if novel.novel_format == NOVEL_FORMAT_ZHIHU_SHORT:
        try:
            from services.short_story_review import review_completed_short_story
            await review_completed_short_story(db, novel, chapter_index)
        except Exception:
            logger.exception("short_story_review_failed project_id=%s chapter_index=%s", novel.id, chapter_index)
    else:
        try:
            from services.volume_review import review_volume, volume_index_ending_at
            volume_index = volume_index_ending_at(novel.outline, chapter_index)
            if volume_index is not None:
                await review_volume(db, novel, volume_index)
        except Exception:
            logger.exception("volume_review_failed project_id=%s chapter_index=%s", novel.id, chapter_index)

    if novel.novel_format != NOVEL_FORMAT_ZHIHU_SHORT and novel.optimize_interval and chapter_index % novel.optimize_interval == 0:
        try:
            await stream_manager.broadcast(
                str(novel.id),
                "status",
                {"step": AGENT_PLANNER, "chapter": chapter_index, "message": f"达到优化间隔（每 {novel.optimize_interval} 章），策划智能体正在自动优化整书大纲..."}
            )
            world_state = await get_filtered_world_state(db, novel.id, chapter.content or "")
            foreshadowing = await get_filtered_foreshadowing(db, novel.id, chapter.content or "")
            plot_threads = knowledge_to_markdown(
                "plot_threads",
                await living_docs.read_knowledge(str(novel.id), "plot_threads", db),
            )

            from services.outline_service import optimize_skeleton
            await optimize_skeleton(
                db,
                novel,
                world_state=world_state,
                character_state=character_state_txt,
                foreshadowing=foreshadowing,
                plot_threads=plot_threads,
                chapter_index=chapter_index,
            )
            await stream_manager.broadcast(
                str(novel.id),
                "status",
                {"step": AGENT_PLANNER, "chapter": chapter_index, "message": "整书大纲自动优化完成！"}
            )
        except Exception:
            logger.exception("outline_optimization_failed project_id=%s chapter_index=%s", novel.id, chapter_index)


async def run_post_processing(
    db: AsyncSession,
    novel_id: uuid.UUID,
    chapter_index: int,
    *,
    run_extractor: bool = True,
):
    result_novel = await db.execute(select(Novel).where(Novel.id == novel_id))
    novel = result_novel.scalar_one_or_none()
    result_chapter = await db.execute(
        select(Chapter).where(Chapter.novel_id == novel_id, Chapter.chapter_index == chapter_index)
    )
    chapter = result_chapter.scalar_one_or_none()
    if not novel or not chapter:
        return

    if not run_extractor:
        publish_chapter_state(chapter)
        novel.current_chapter = max(novel.current_chapter or 0, chapter_index)
        if (novel.total_chapters or 0) < chapter_index:
            novel.total_chapters = chapter_index
        chapter.word_count = chapter_chars_from_row(chapter)
        novel.total_chars = await sum_project_chars(db, novel.id)
        await db.commit()
        if novel.novel_format == NOVEL_FORMAT_ZHIHU_SHORT:
            try:
                from services.short_story_review import review_completed_short_story
                await review_completed_short_story(db, novel, chapter_index)
            except Exception:
                logger.exception("short_story_review_failed project_id=%s chapter_index=%s", novel.id, chapter_index)
        return

    await stream_manager.broadcast(str(novel.id), "log", {"source": STREAM_SOURCE_EXTRACTOR, "message": "设定提取器启动：开始读取章节最新的伏笔、主线和世界设定卡..."})

    # Filter world_state and foreshadowing
    world_state = await get_filtered_world_state(db, novel.id, chapter.content or "")
    foreshadowing = await get_filtered_foreshadowing(db, novel.id, chapter.content or "")

    # Filter character state to only active characters in chapter content
    character_state_txt_raw = knowledge_to_markdown(
        "character_state",
        await living_docs.read_knowledge(str(novel.id), "character_state", db),
    )
    from services.outline_service import resolve_protagonist_name
    protagonist_name = resolve_protagonist_name(novel)
    character_state = get_filtered_character_state(
        character_state_txt_raw, chapter.content or "", protagonist_name
    )

    plot_threads = knowledge_to_markdown(
        "plot_threads",
        await living_docs.read_knowledge(str(novel.id), "plot_threads", db),
    )

    await stream_manager.broadcast(str(novel.id), "log", {"source": STREAM_SOURCE_EXTRACTOR, "message": "设定提取分析中：正在通过大语言模型同步人物状态、伏笔回收及世界规则变动..."})

    extractor_context = PipelineContext(
        project_id=str(novel.id),
        chapter_index=chapter.chapter_index,
        world_state=world_state,
        character_state=character_state,
        foreshadowing=foreshadowing,
        plot_threads=plot_threads,
        title=chapter.title or "",
        chapter_content=chapter.content or "",
        previous_ending="",
        novel_format=novel.novel_format or "",
        genre="",
        style="",
    )

    extractor = ExtractorNode()
    extractor.agent.project_id = novel.id
    extractor.agent.current_chapter = chapter.chapter_index

    extractor_output = await extractor.run(extractor_context, {"content": chapter.content})
    extract_result = extractor_output.payload
    await extractor.agent.record_usage(db, novel.id, chapter.chapter_index, AGENT_EXTRACTOR)

    await apply_extractor_updates(db, novel, chapter, extract_result)
