"""Shared vocabulary for the novel memory layers.

These values are deliberately plain strings so they can be used by both ORM
models and background workers without coupling the persistence layer to a
specific API schema.
"""

from typing import Final


STORYLINE_MAIN: Final[str] = "main"

ATOM_STATUS_CANDIDATE: Final[str] = "candidate"
ATOM_STATUS_ACCEPTED: Final[str] = "accepted"
ATOM_STATUS_REJECTED: Final[str] = "rejected"
ATOM_STATUS_SUPERSEDED: Final[str] = "superseded"
ATOM_STATUSES: Final[tuple[str, ...]] = (
    ATOM_STATUS_CANDIDATE,
    ATOM_STATUS_ACCEPTED,
    ATOM_STATUS_REJECTED,
    ATOM_STATUS_SUPERSEDED,
)

AUTHORITY_GENERATED: Final[str] = "generated"
AUTHORITY_USER: Final[str] = "user"
AUTHORITY_PUBLISHED: Final[str] = "published"
AUTHORITY_SYSTEM: Final[str] = "system"
AUTHORITIES: Final[tuple[str, ...]] = (
    AUTHORITY_GENERATED,
    AUTHORITY_USER,
    AUTHORITY_PUBLISHED,
    AUTHORITY_SYSTEM,
)

SCENE_BLOCK_ACTIVE: Final[str] = "active"
SCENE_BLOCK_ARCHIVED: Final[str] = "archived"

CONFLICT_OPEN: Final[str] = "open"
CONFLICT_RESOLVED: Final[str] = "resolved"
CONFLICT_DISMISSED: Final[str] = "dismissed"
CONFLICT_STATUSES: Final[tuple[str, ...]] = (
    CONFLICT_OPEN,
    CONFLICT_RESOLVED,
    CONFLICT_DISMISSED,
)


def is_valid_atom_status(value: str) -> bool:
    return value in ATOM_STATUSES


def is_valid_authority(value: str) -> bool:
    return value in AUTHORITIES


def is_valid_conflict_status(value: str) -> bool:
    return value in CONFLICT_STATUSES
