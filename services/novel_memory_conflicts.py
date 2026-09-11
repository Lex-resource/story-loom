"""Durable queue for hard layered-memory conflicts.

The queue is deliberately narrow: ambiguity and ordinary generated candidates
stay in the candidate tables. Hard authority/continuity conflicts are recorded
for audit; the production extractor path automatically rejects unsafe
candidates without overwriting canonical facts.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel_memory import NovelMemoryConflict
from models.base import _utcnow
from services.novel_memory_types import (
    AUTHORITY_GENERATED,
    CONFLICT_OPEN,
    CONFLICT_RESOLVED,
    STORYLINE_MAIN,
)


AUTO_EXTRACTOR_REVIEWER = "system:auto_extractor_review"


_CONFLICT_NAMESPACE = uuid.UUID("c7b0ccbb-7c1f-4e1a-9f0b-71d3c37fd2e4")

SOFT_EXTRACTOR_RISK_TERMS = (
    "可能",
    "需后续",
    "后续验证",
    "待验证",
    "需确认",
    "需要确认",
    "动机不明",
    "可靠性低",
    "误读",
    "悬念",
    "伏笔",
    "不确定",
    "信息不足",
    "可疑",
)

HARD_EXTRACTOR_RISK_TERMS = (
    "明确冲突",
    "直接冲突",
    "硬冲突",
    "直接矛盾",
    "违反既有",
    "推翻既有",
    "覆盖既有",
    "删除既有",
    "生死状态冲突",
    "时间线硬冲突",
    "权限体系硬冲突",
)


def is_hard_extractor_issue(issue: dict[str, Any]) -> bool:
    """Return true only for extractor issues that should block publication."""
    if not isinstance(issue, dict):
        return False
    if str(issue.get("severity", "")).lower() != "high":
        return False
    if str(issue.get("category", "")) == "frozen_fact":
        return True
    text = " ".join(
        str(issue.get(key, "") or "")
        for key in ("category", "description", "message", "detail")
    )
    if any(term in text for term in SOFT_EXTRACTOR_RISK_TERMS):
        return False
    return any(term in text for term in HARD_EXTRACTOR_RISK_TERMS)


def build_conflict_hash(
    *,
    project_id: uuid.UUID,
    chapter_index: int | None,
    source_ref: str,
    issue: dict[str, Any],
    branch_id: uuid.UUID | None = None,
    storyline_id: str = STORYLINE_MAIN,
) -> str:
    payload = {
        "project_id": str(project_id),
        "branch_id": str(branch_id) if branch_id else None,
        "storyline_id": storyline_id,
        "chapter_index": chapter_index,
        "source_ref": source_ref,
        "issue": issue,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text(issue: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = issue.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _confidence(issue: dict[str, Any]) -> float:
    try:
        return max(0.0, min(1.0, float(issue.get("confidence", 1.0) or 0.0)))
    except (TypeError, ValueError):
        return 1.0


def _conflict_values(
    *,
    project_id: uuid.UUID,
    chapter_index: int | None,
    source_ref: str,
    issue: dict[str, Any],
    conflict_hash: str,
    branch_id: uuid.UUID | None,
    storyline_id: str,
) -> dict[str, Any]:
    conflict_type = _text(issue, "conflict_type", "category", "type") or "continuity"
    memory_key = _text(issue, "memory_key", "name", "entry_key") or f"issue:{conflict_hash[:16]}"
    return {
        "id": uuid.uuid5(_CONFLICT_NAMESPACE, conflict_hash),
        "project_id": project_id,
        "branch_id": branch_id,
        "storyline_id": storyline_id,
        "source_ref": source_ref,
        "source_chapter": chapter_index,
        "confidence": _confidence(issue),
        "version": 1,
        "valid_from_chapter": chapter_index,
        "valid_to_chapter": None,
        "authority": AUTHORITY_GENERATED,
        "conflict_hash": conflict_hash,
        "conflict_type": conflict_type,
        "memory_key": memory_key,
        "severity": str(issue.get("severity") or "high").lower(),
        "description": _text(issue, "description", "message", "detail") or "未提供冲突描述",
        "evidence": _text(issue, "evidence", "observed", "candidate"),
        "conflicts_with": _text(issue, "conflicts_with", "existing_fact", "accepted_fact"),
        "payload": issue,
        "status": CONFLICT_OPEN,
        "resolved_by": None,
        "resolved_at": None,
    }


async def record_hard_conflicts(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    chapter_index: int,
    issues: Iterable[dict[str, Any]],
    branch_id: uuid.UUID | None = None,
    storyline_id: str = STORYLINE_MAIN,
) -> list[NovelMemoryConflict]:
    """Insert hard conflicts idempotently and return their queue rows."""
    persisted: list[NovelMemoryConflict] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        source_ref = str(issue.get("source_ref") or f"chapter:{chapter_index}:extractor:conflict")
        conflict_hash = build_conflict_hash(
            project_id=project_id,
            chapter_index=chapter_index,
            source_ref=source_ref,
            issue=issue,
            branch_id=branch_id,
            storyline_id=storyline_id,
        )
        values = _conflict_values(
            project_id=project_id,
            chapter_index=chapter_index,
            source_ref=source_ref,
            issue=issue,
            conflict_hash=conflict_hash,
            branch_id=branch_id,
            storyline_id=storyline_id,
        )
        await db.execute(
            pg_insert(NovelMemoryConflict)
            .values(**values)
            .on_conflict_do_nothing()
        )
        conflict = await db.scalar(
            select(NovelMemoryConflict).where(
                NovelMemoryConflict.conflict_hash == conflict_hash
            )
        )
        if conflict is not None:
            persisted.append(conflict)
    return persisted


def resolve_conflicts_automatically(
    conflicts: Iterable[NovelMemoryConflict],
    *,
    resolved_by: str = AUTO_EXTRACTOR_REVIEWER,
) -> list[NovelMemoryConflict]:
    """Close conflict records after rejecting unsafe generated candidates."""
    resolved: list[NovelMemoryConflict] = []
    # The SQLAlchemy model uses PostgreSQL ``TIMESTAMP WITHOUT TIME ZONE``.
    # Keep the stored audit timestamp consistent with the rest of the model
    # timestamps instead of passing an aware datetime to asyncpg.
    resolved_at = _utcnow()
    for conflict in conflicts:
        conflict.status = CONFLICT_RESOLVED
        conflict.resolved_by = resolved_by
        conflict.resolved_at = resolved_at
        resolved.append(conflict)
    return resolved


async def list_open_conflicts(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    branch_id: uuid.UUID | None = None,
    storyline_id: str = STORYLINE_MAIN,
    limit: int = 100,
) -> list[NovelMemoryConflict]:
    result = await db.execute(
        select(NovelMemoryConflict)
        .where(
            NovelMemoryConflict.project_id == project_id,
            NovelMemoryConflict.branch_id == branch_id,
            NovelMemoryConflict.storyline_id == storyline_id,
            NovelMemoryConflict.status == CONFLICT_OPEN,
        )
        .order_by(NovelMemoryConflict.source_chapter, NovelMemoryConflict.created_at)
        .limit(max(1, min(limit, 500)))
    )
    return list(result.scalars().all())
