import uuid
from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.novel import RawIssue, IssueSummary


async def get_raw_issues(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RawIssue).where(RawIssue.project_id == uuid.UUID(project_id)).order_by(RawIssue.chapter_index)
    )
    issues = result.scalars().all()
    return [{"chapter_index": i.chapter_index, "category": i.category, "description": i.description, "severity": i.severity} for i in issues]


class ToggleIssueRequest(BaseModel):
    enabled: bool


async def get_issue_summaries(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(IssueSummary).where(IssueSummary.project_id == uuid.UUID(project_id))
    )
    summaries = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "category": s.category,
            "summary": s.summary,
            "severity": s.severity,
            "examples": s.examples,
            "enabled": s.enabled
        }
        for s in summaries
    ]


async def toggle_issue_summary(
    project_id: str,
    issue_id: str,
    data: ToggleIssueRequest,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(IssueSummary).where(
            IssueSummary.project_id == uuid.UUID(project_id),
            IssueSummary.id == uuid.UUID(issue_id)
        )
    )
    summary = result.scalar_one_or_none()
    if not summary:
        raise HTTPException(status_code=404, detail="Issue summary not found")

    summary.enabled = data.enabled
    await db.commit()
    return {"status": "success", "id": issue_id, "enabled": summary.enabled}
