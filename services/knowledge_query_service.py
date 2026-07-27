from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select
from database import get_db
from models.novel import Novel
from services import living_docs
from services.knowledge_character_graph import build_character_graph
from services.knowledge_foreshadowing_timeline import build_foreshadowing_timeline
from services.knowledge_plot_tracks import build_plot_tracks
from services.knowledge_world_rules import build_world_rules_tree
from services.community_service import CommunityService

async def get_community_summary(project_id: str, db: AsyncSession = Depends(get_db)):
    graph = await get_character_graph(project_id, db)
    novel_res = await db.execute(select(Novel).where(Novel.id == project_id))
    novel = novel_res.scalar_one_or_none()
    novel_format = novel.novel_format if novel else None
    return await CommunityService.generate_community_summaries(graph["nodes"], graph["edges"], novel_format)

async def get_character_graph(project_id: str, db: AsyncSession = Depends(get_db)):
    items = await living_docs.read_knowledge(project_id, "character_state", db)
    return build_character_graph(items)

async def get_world_rules_tree(project_id: str, db: AsyncSession = Depends(get_db)):
    items = await living_docs.read_knowledge(project_id, "world_state", db)
    return build_world_rules_tree(items)

async def get_foreshadowing_timeline(project_id: str, db: AsyncSession = Depends(get_db)):
    items = await living_docs.read_knowledge(project_id, "foreshadowing", db)
    return build_foreshadowing_timeline(items)

async def get_plot_tracks(project_id: str, db: AsyncSession = Depends(get_db)):
    items = await living_docs.read_knowledge(project_id, "plot_threads", db)
    return build_plot_tracks(items)
