import copy
import uuid
from typing import Optional
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from database import get_db
from models.novel import Novel, Chapter, ChapterOutline, Job, RawIssue, IssueSummary, VectorOutbox, LivingDocVersion, TokenUsage
from agents.constants import AGENT_PLANNER
from agents.pipeline import PlannerNode
from services.novel_constants import API_STATUS_OK
from services.pipeline_transitions import set_chapter_pipeline_step
from services.pipeline_types import PipelineStep



class ProjectConfigRequest(BaseModel):
    word_count_per_chapter: int = Field(ge=0, le=100_000)
    mode: Optional[str] = Field(default=None, pattern="^(step|auto)$")
    optimize_interval: Optional[int] = Field(default=None, ge=1, le=10_000)
    target_chapters: Optional[int] = Field(default=None, ge=1, le=10_000)


class ManualOutlineUpdateRequest(BaseModel):
    outline: dict


class OutlineChatRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=20_000)


async def update_config(project_id: str, data: ProjectConfigRequest, db: AsyncSession = Depends(get_db)):
    from services.project_service import get_novel_or_404
    novel = await get_novel_or_404(db, project_id)

    novel.word_count_per_chapter = data.word_count_per_chapter
    if data.mode is not None:
        novel.mode = data.mode
    if data.optimize_interval is not None:
        novel.optimize_interval = data.optimize_interval
    if data.target_chapters is not None:
        novel.target_chapters = data.target_chapters
    await db.commit()
    return {"status": API_STATUS_OK}


async def update_outline(project_id: str, data: ManualOutlineUpdateRequest, db: AsyncSession = Depends(get_db)):
    from services.project_service import get_novel_or_404
    novel = await get_novel_or_404(db, project_id)

    novel.outline = data.outline
    await db.commit()
    return {"status": API_STATUS_OK, "outline": novel.outline}


async def chat_update_outline(project_id: str, data: OutlineChatRequest, db: AsyncSession = Depends(get_db)):
    from services.project_service import get_novel_or_404
    novel = await get_novel_or_404(db, project_id)

    planner = PlannerNode()

    current_outline = novel.outline or {}
    if not current_outline.get("书名"):
        current_outline["书名"] = novel.title
    updated_outline = await planner.agent.chat_modify_outline(current_outline, data.instruction, novel_format=novel.novel_format)
    await planner.agent.record_usage(db, novel.id, 0, AGENT_PLANNER)
    novel.outline = updated_outline
    await db.commit()
    return {"status": API_STATUS_OK, "outline": novel.outline}


async def optimize_outline_endpoint(project_id: str, db: AsyncSession = Depends(get_db)):
    from services.project_service import get_novel_or_404
    novel = await get_novel_or_404(db, project_id)

    # Get living docs
    from services import living_docs
    all_docs = await living_docs.read_all_docs(str(novel.id), db)
    world_state = all_docs.get("world_state", "")
    character_state = all_docs.get("character_state", "")
    foreshadowing = all_docs.get("foreshadowing", "")
    plot_threads = all_docs.get("plot_threads", "")

    updated_outline = await optimize_skeleton(
        db,
        novel,
        world_state=world_state,
        character_state=character_state,
        foreshadowing=foreshadowing,
        plot_threads=plot_threads,
    )
    return {"status": API_STATUS_OK, "outline": updated_outline}


async def get_outline(project_id: str, db: AsyncSession = Depends(get_db)):
    from services.project_service import get_novel_or_404
    novel = await get_novel_or_404(db, project_id)
    return {"outline": novel.outline}


async def get_chapter_outlines(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ChapterOutline).where(ChapterOutline.project_id == uuid.UUID(project_id)).order_by(ChapterOutline.chapter_index)
    )
    outlines = result.scalars().all()
    return [{"chapter_index": o.chapter_index, "outline": o.outline} for o in outlines]


def resolve_protagonist_name(novel) -> str | None:
    """从 novel.outline 的"主要人物"列表中解析主角姓名，剥离括号别名。

    Args:
        novel: Novel 模型实例，需有 .outline 属性（dict 或 None）

    Returns:
        主角姓名（已剥离括号），或 None
    """
    from services.knowledge_constants import PROTAGONIST_ROLE_LABEL
    if not novel or not novel.outline or not isinstance(novel.outline, dict):
        return None
    for char in novel.outline.get("主要人物", []):
        if char.get("角色") == PROTAGONIST_ROLE_LABEL:
            name = char.get("姓名")
            if name and "（" in name:
                return name.split("（")[0]
            elif name and "(" in name:
                return name.split("(")[0]
            return name
    return None


def extract_genre_style(outline: dict | None) -> tuple[str, str]:
    """从 outline dict 中提取类型和风格，兼容中英文 key。

    Returns:
        (genre, style) 元组，未找到时为空字符串
    """
    if not outline or not isinstance(outline, dict):
        return "", ""
    genre = outline.get("类型") or outline.get("type", "")
    style = outline.get("风格") or outline.get("style", "")
    return genre, style


def protect_outline_contract(current: dict, candidate: dict) -> dict:
    """Restore author-level promises that rolling optimization cannot change."""
    if not isinstance(candidate, dict):
        return copy.deepcopy(current)
    protected = copy.deepcopy(candidate)
    for key in ("书名", "标题", "创作契约"):
        if key in current:
            protected[key] = copy.deepcopy(current[key])
    return protected


async def optimize_skeleton(
    db: AsyncSession,
    novel: Novel,
    *,
    world_state: str,
    character_state: str,
    foreshadowing: str,
    plot_threads: str,
    chapter_index: Optional[int] = None,
    agent_name: str = AGENT_PLANNER,
) -> dict:
    """优化整书大纲：构建 chapter_summaries 并调用 planner.optimize_skeleton_outline。

    Args:
        db: 数据库会话
        novel: Novel 模型实例
        world_state: 世界设定文本
        character_state: 角色状态文本
        foreshadowing: 伏笔文本
        plot_threads: 主线文本
        chapter_index: 当前章节序号（用于 agent 上下文与 usage 记录）；None 表示手动调用，usage 记录 0
        agent_name: 用于 usage 记录的 agent 名称

    Returns:
        更新后的 outline dict
    """
    # Build chapter summaries from existing chapters
    ch_result = await db.execute(
        select(Chapter)
        .where(Chapter.novel_id == novel.id)
        .order_by(Chapter.chapter_index)
    )
    chapters = ch_result.scalars().all()
    summaries_list = []
    for ch in chapters:
        title = ch.title or f"第{ch.chapter_index}章"
        summary = ""
        if ch.outline and isinstance(ch.outline, dict):
            summary = ch.outline.get("summary", "")
        summaries_list.append(f"第{ch.chapter_index}章 {title}: {summary}")
    chapter_summaries = "\n".join(summaries_list)

    planner = PlannerNode()
    if chapter_index is not None:
        planner.agent.project_id = novel.id
        planner.agent.current_chapter = chapter_index

    current_outline = novel.outline or {}
    if not current_outline.get("书名"):
        current_outline["书名"] = novel.title
    rhythm_review = {}
    if novel.novel_format != "zhihu_short" and chapters:
        from services.outline_hierarchy import select_active_volume

        def _volume_goal(chapter_index: int) -> str:
            vol = select_active_volume(current_outline, chapter_index)
            if not isinstance(vol, dict):
                return ""
            name = vol.get("卷名") or vol.get("name") or ""
            goal = vol.get("卷目标") or vol.get("阶段兑现") or vol.get("升级变化") or ""
            if isinstance(goal, list):
                goal = "；".join(str(g) for g in goal if g)
            parts = [p for p in (name, goal) if p]
            return " · ".join(str(p) for p in parts)

        recent_outlines = [
            {
                "chapter_index": ch.chapter_index,
                "title": ch.title or f"第{ch.chapter_index}章",
                "narrative_stage": (ch.outline or {}).get("narrative_stage", "未知")
                if isinstance(ch.outline, dict)
                else "未知",
                "volume_goal": _volume_goal(ch.chapter_index),
            }
            for ch in chapters[-10:]
        ]
        try:
            rhythm_review = await planner.agent.review_act_rhythm(
                recent_outlines,
                novel_format=novel.novel_format,
            )
        except Exception as exc:
            print(f"[Outline WARN] Act rhythm review failed: {exc}")
        else:
            chapter_summaries = (
                f"【阶段节奏复盘】\n{rhythm_review}\n\n"
                f"【已创作章节概要】\n{chapter_summaries}"
            )
    updated_outline = await planner.agent.optimize_skeleton_outline(
        current_outline,
        world_state,
        character_state,
        foreshadowing,
        plot_threads,
        chapter_summaries,
        novel_format=novel.novel_format,
    )
    usage_chapter = chapter_index if chapter_index is not None else 0
    await planner.agent.record_usage(db, novel.id, usage_chapter, agent_name)
    updated_outline = protect_outline_contract(current_outline, updated_outline)
    novel.outline = updated_outline
    # Do not commit here — let the caller control the transaction boundary.
    # Callers that need an immediate commit should do so explicitly.
    return updated_outline



