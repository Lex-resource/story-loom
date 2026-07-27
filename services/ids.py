"""Shared identifier parsing helpers for service and router layers."""

from __future__ import annotations

import uuid

from fastapi import HTTPException


def parse_project_id(project_id: str) -> uuid.UUID:
    """Return a UUID for project_id or raise the API's standard 422 error."""
    try:
        return uuid.UUID(project_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid project_id")


def is_project_id(project_id: str) -> bool:
    """Return True when project_id is a syntactically valid UUID."""
    try:
        uuid.UUID(project_id)
        return True
    except (ValueError, TypeError):
        return False
