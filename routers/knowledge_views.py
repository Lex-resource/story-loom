from __future__ import annotations

from fastapi import APIRouter

from services import knowledge_query_service


router = APIRouter()

router.add_api_route("/{project_id}/character-graph", knowledge_query_service.get_character_graph, methods=["GET"])
router.add_api_route("/{project_id}/world-rules-tree", knowledge_query_service.get_world_rules_tree, methods=["GET"])
router.add_api_route("/{project_id}/foreshadowing-timeline", knowledge_query_service.get_foreshadowing_timeline, methods=["GET"])
router.add_api_route("/{project_id}/plot-tracks", knowledge_query_service.get_plot_tracks, methods=["GET"])
router.add_api_route("/{project_id}/community-summary", knowledge_query_service.get_community_summary, methods=["GET"])
