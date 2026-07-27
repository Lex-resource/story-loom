from __future__ import annotations

from fastapi import APIRouter

from services import outline_service, project_service


router = APIRouter()

router.add_api_route("/formats", project_service.get_formats, methods=["GET"])
router.add_api_route("/projects", project_service.list_projects, methods=["GET"])
router.add_api_route("/project", project_service.create_project, methods=["POST"])
router.add_api_route("/project/{project_id}", project_service.delete_project, methods=["DELETE"])
router.add_api_route("/{project_id}/status", project_service.get_status, methods=["GET"])
router.add_api_route("/{project_id}/jobs", project_service.get_jobs, methods=["GET"])
router.add_api_route("/{project_id}/config", outline_service.update_config, methods=["POST"])
router.add_api_route("/{project_id}/outline", outline_service.get_outline, methods=["GET"])
router.add_api_route("/{project_id}/outline", outline_service.update_outline, methods=["POST"])
router.add_api_route("/{project_id}/outline/chat", outline_service.chat_update_outline, methods=["POST"])
router.add_api_route("/{project_id}/outline/optimize", outline_service.optimize_outline_endpoint, methods=["POST"])
router.add_api_route("/{project_id}/chapter-outlines", outline_service.get_chapter_outlines, methods=["GET"])
