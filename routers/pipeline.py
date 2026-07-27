from __future__ import annotations

from fastapi import APIRouter

from services import pipeline_service


router = APIRouter()

router.add_api_route("/{project_id}/generate", pipeline_service.generate, methods=["POST"])
router.add_api_route("/{project_id}/pause", pipeline_service.pause, methods=["POST"])
router.add_api_route("/{project_id}/resume", pipeline_service.resume, methods=["POST"])
router.add_api_route("/{project_id}/intervention", pipeline_service.intervene, methods=["POST"])
router.add_api_route("/{project_id}/rewrite", pipeline_service.rewrite, methods=["POST"])
