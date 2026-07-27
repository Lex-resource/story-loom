from __future__ import annotations

from fastapi import APIRouter

from services import chapter_service


router = APIRouter()

router.add_api_route("/{project_id}/chapters", chapter_service.get_chapters, methods=["GET"])
router.add_api_route("/{project_id}/chapters/{chapter_index}", chapter_service.get_chapter, methods=["GET"])
router.add_api_route("/{project_id}/chapters/{chapter_index}", chapter_service.delete_chapter, methods=["DELETE"])
router.add_api_route("/{project_id}/chapters/{chapter_index}/edit", chapter_service.edit_chapter, methods=["POST"])
router.add_api_route("/{project_id}/chapters/{chapter_index}/outline", chapter_service.update_chapter_outline, methods=["POST"])
router.add_api_route("/{project_id}/chapters/{chapter_index}/review_json", chapter_service.review_json, methods=["POST"])
router.add_api_route("/{project_id}/publish/{chapter_index}", chapter_service.publish_chapter, methods=["POST"])
