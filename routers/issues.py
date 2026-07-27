from __future__ import annotations

from fastapi import APIRouter

from services import issue_service, token_usage_service


router = APIRouter()

router.add_api_route("/{project_id}/raw-issues", issue_service.get_raw_issues, methods=["GET"])
router.add_api_route("/{project_id}/issue-summaries", issue_service.get_issue_summaries, methods=["GET"])
router.add_api_route("/{project_id}/issue-summaries/{issue_id}/toggle", issue_service.toggle_issue_summary, methods=["POST"])
router.add_api_route("/{project_id}/token-stats", token_usage_service.get_token_stats, methods=["GET"])
