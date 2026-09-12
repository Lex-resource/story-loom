"""Compatibility facade — 实现已下沉到 core.novel_memory_vocab。

现有 `from services.novel_memory_types import X` 全部保持可用。
"""

from __future__ import annotations

from core.novel_memory_vocab import (  # noqa: F401  (facade re-exports)
    ATOM_STATUSES,
    ATOM_STATUS_ACCEPTED,
    ATOM_STATUS_CANDIDATE,
    ATOM_STATUS_REJECTED,
    ATOM_STATUS_SUPERSEDED,
    AUTHORITIES,
    AUTHORITY_GENERATED,
    AUTHORITY_PUBLISHED,
    AUTHORITY_SYSTEM,
    AUTHORITY_USER,
    CONFLICT_DISMISSED,
    CONFLICT_OPEN,
    CONFLICT_RESOLVED,
    CONFLICT_STATUSES,
    SCENE_BLOCK_ACTIVE,
    SCENE_BLOCK_ARCHIVED,
    STORYLINE_MAIN,
    is_valid_atom_status,
    is_valid_authority,
    is_valid_conflict_status,
)
