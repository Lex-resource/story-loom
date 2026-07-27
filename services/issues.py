import uuid
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from models.novel import RawIssue, IssueSummary, Novel
from agents.writing.issue_classifier import IssueClassifierAgent
from services.novel_constants import AGENT_NAME_CLASSIFIER, ISSUE_SIMILARITY_THRESHOLD

def is_similar(s1: str, s2: str) -> bool:
    """Return True if two strings are textually similar.

    Uses character-bigram Jaccard similarity instead of raw character-set
    Jaccard. The previous set-based comparison treated "abc" and "cba" as
    identical and, for Chinese text, flagged unrelated sentences as similar
    because common characters (的/了/是) dominate the intersection. Bigrams
    capture sequence information, so "主角" and "角主" no longer match.
    """
    if not s1 or not s2:
        return False

    # Build overlapping character bigrams. Pad with a leading space so that
    # single-char strings still produce one bigram and short strings aren't
    # unfairly penalized.
    def bigrams(s: str) -> set[str]:
        padded = " " + s
        return {padded[i : i + 2] for i in range(len(padded) - 1)}

    bg1 = bigrams(s1)
    bg2 = bigrams(s2)
    if not bg1 or not bg2:
        return False

    intersection = bg1 & bg2
    union = bg1 | bg2
    similarity = len(intersection) / len(union)
    return similarity > ISSUE_SIMILARITY_THRESHOLD


async def update_project_issue_summaries(db: AsyncSession, project_id: uuid.UUID):
    """
    Fetch all raw issues for a project, aggregate them using the IssueClassifierAgent,
    and save the global issue summaries back to the database.
    """
    novel_res = await db.execute(select(Novel).where(Novel.id == project_id))
    novel = novel_res.scalar_one_or_none()
    if not novel:
        return
        
    # 1. Fetch all RawIssue items for the project
    result = await db.execute(
        select(RawIssue).where(RawIssue.project_id == project_id)
    )
    raw_issues = result.scalars().all()
    
    if not raw_issues:
        # If no raw issues, clear the summaries
        await db.execute(
            delete(IssueSummary).where(IssueSummary.project_id == project_id)
        )
        await db.commit()
        return
        
    # Convert DB models to list of dicts for the classifier
    raw_issues_list = [
        {
            "chapter_index": r.chapter_index,
            "category": r.category,
            "description": r.description,
            "severity": r.severity
        }
        for r in raw_issues
    ]
    
    # 2. Call IssueClassifierAgent to aggregate them
    classifier = IssueClassifierAgent()
    try:
        summarized = await classifier.classify_issues(raw_issues_list, novel_format=novel.novel_format)
        await classifier.record_usage(db, project_id, 0, AGENT_NAME_CLASSIFIER)
    except Exception as e:
        print(f"[Issue Classifier ERROR] Failed to classify issues: {e}")
        return
    
    # 3. Fetch existing disabled summaries to preserve their disabled status
    existing_disabled_result = await db.execute(
        select(IssueSummary).where(IssueSummary.project_id == project_id, IssueSummary.enabled == False)
    )
    disabled_summaries = {e.summary for e in existing_disabled_result.scalars().all()}

    # 4. Delete existing IssueSummary entries for the project
    await db.execute(
        delete(IssueSummary).where(IssueSummary.project_id == project_id)
    )
    
    # 5. Insert new IssueSummary entries
    for s in summarized:
        summary_text = s.get("summary", "")
        # Default to True (enabled) unless it matches a previously disabled summary
        is_disabled = any(is_similar(summary_text, disabled_text) for disabled_text in disabled_summaries)
        is_enabled = not is_disabled
        
        summary = IssueSummary(
            project_id=project_id,
            category=s.get("category"),
            summary=summary_text,
            examples=str(s.get("examples", "")),  # Convert list or other types to string
            severity=s.get("severity"),
            enabled=is_enabled
        )
        db.add(summary)

        
    await db.commit()
