from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from routers._common import validate_project_id
from services import knowledge_query_service
from services.knowledge_query_service import (
    DEFAULT_CHARACTER_GRAPH_LIMIT,
    MAX_CHARACTER_GRAPH_LIMIT,
)
from services.novel_memory_views import (
    DEFAULT_KNOWLEDGE_VIEW_LIMIT,
    MAX_KNOWLEDGE_VIEW_LIMIT,
)


router = APIRouter()


async def get_character_graph_view(
    project_id: str,
    limit: int = Query(DEFAULT_CHARACTER_GRAPH_LIMIT, ge=1, le=MAX_CHARACTER_GRAPH_LIMIT),
    db: AsyncSession = Depends(get_db),
):
    return await knowledge_query_service.get_character_graph(
        validate_project_id(project_id), db, limit=limit
    )


async def get_world_rules_tree_view(
    project_id: str,
    limit: int = Query(DEFAULT_KNOWLEDGE_VIEW_LIMIT, ge=1, le=MAX_KNOWLEDGE_VIEW_LIMIT),
    db: AsyncSession = Depends(get_db),
):
    return await knowledge_query_service.get_world_rules_tree(
        validate_project_id(project_id), db, limit=limit
    )


async def get_foreshadowing_timeline_view(
    project_id: str,
    limit: int = Query(DEFAULT_KNOWLEDGE_VIEW_LIMIT, ge=1, le=MAX_KNOWLEDGE_VIEW_LIMIT),
    db: AsyncSession = Depends(get_db),
):
    return await knowledge_query_service.get_foreshadowing_timeline(
        validate_project_id(project_id), db, limit=limit
    )


async def get_plot_tracks_view(
    project_id: str,
    limit: int = Query(DEFAULT_KNOWLEDGE_VIEW_LIMIT, ge=1, le=MAX_KNOWLEDGE_VIEW_LIMIT),
    db: AsyncSession = Depends(get_db),
):
    return await knowledge_query_service.get_plot_tracks(
        validate_project_id(project_id), db, limit=limit
    )


async def get_community_summary_view(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    return await knowledge_query_service.get_community_summary(
        validate_project_id(project_id), db
    )


router.add_api_route("/{project_id}/character-graph", get_character_graph_view, methods=["GET"])
router.add_api_route("/{project_id}/world-rules-tree", get_world_rules_tree_view, methods=["GET"])
router.add_api_route("/{project_id}/foreshadowing-timeline", get_foreshadowing_timeline_view, methods=["GET"])
router.add_api_route("/{project_id}/plot-tracks", get_plot_tracks_view, methods=["GET"])
router.add_api_route("/{project_id}/community-summary", get_community_summary_view, methods=["GET"])
