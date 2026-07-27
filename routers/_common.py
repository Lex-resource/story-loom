"""Shared helpers for router modules."""

from services.ids import is_project_id, parse_project_id


def validate_project_id(project_id: str):
    """Validate project_id and return the parsed UUID.

    Raises HTTPException(422) when the value is not a valid UUID.
    """
    return parse_project_id(project_id)


def is_valid_project_id(project_id: str) -> bool:
    """Return True if project_id is a valid UUID, False otherwise.

    Use this when a boolean check is preferred over raising (e.g. WebSocket
    endpoints that need to close the connection with a custom code instead of
    returning an HTTP error response).
    """
    return is_project_id(project_id)
