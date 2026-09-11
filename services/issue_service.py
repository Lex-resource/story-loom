"""Persistence operations for generated issue summaries.

This module is deliberately HTTP-independent. Routers own request parsing and
exception mapping; workers can reuse these operations without importing
FastAPI.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel import IssueSummary, RawIssue

DEFAULT_ISSUE_PAGE_SIZE = 200
MAX_ISSUE_PAGE_SIZE = 500


def _apply_page(statement, limit: int | None, offset: int):
    if limit is None:
        return statement
    bounded_limit = min(max(int(limit), 1), MAX_ISSUE_PAGE_SIZE)
    bounded_offset = max(int(offset), 0)
    return statement.limit(bounded_limit).offset(bounded_offset)


async def list_raw_issues(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    result = await db.execute(
        _apply_page(
            select(RawIssue)
            .where(RawIssue.project_id == project_id)
            .order_by(RawIssue.chapter_index, RawIssue.id),
            limit,
            offset,
        )
    )
    return [
        {
            "chapter_index": issue.chapter_index,
            "category": issue.category,
            "description": issue.description,
            "severity": issue.severity,
        }
        for issue in result.scalars().all()
    ]


async def list_issue_summaries(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    result = await db.execute(
        _apply_page(
            select(IssueSummary)
            .where(IssueSummary.project_id == project_id)
            .order_by(IssueSummary.category, IssueSummary.id),
            limit,
            offset,
        )
    )
    return [
        {
            "id": str(summary.id),
            "category": summary.category,
            "summary": summary.summary,
            "severity": summary.severity,
            "examples": summary.examples,
            "enabled": summary.enabled,
        }
        for summary in result.scalars().all()
    ]


async def set_issue_summary_enabled(
    db: AsyncSession,
    project_id: uuid.UUID,
    issue_id: uuid.UUID,
    enabled: bool,
) -> dict:
    result = await db.execute(
        select(IssueSummary).where(
            IssueSummary.project_id == project_id,
            IssueSummary.id == issue_id,
        )
    )
    summary = result.scalar_one_or_none()
    if summary is None:
        raise LookupError("Issue summary not found")

    summary.enabled = enabled
    await db.commit()
    return {"status": "success", "id": str(issue_id), "enabled": summary.enabled}
