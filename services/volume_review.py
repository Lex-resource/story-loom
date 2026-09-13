"""Volume-level read-through revision — unpublished chapters only.

The paradigm-level pass: once a volume's chapters are all generated but before
any of them is published, read the whole volume as a unit and let the validator
flag cross-chapter problems (planted-but-unpaid debts, sagging tension, dropped
threads) that the per-chapter pipeline cannot see.

HARD PRODUCT RED LINE — serialized-release model:
    A published chapter is frozen forever. Readers have already consumed it, so
    no revision pass may ever mutate it. Every write target is checked against
    ``is_frozen`` and ``assert_no_frozen_writes`` raises before any edit. This
    guard is the most important property in this module: reads are always safe,
    writes to frozen chapters must never happen.

Note: under the current pipeline every completed chapter is auto-published
(``publish_chapter_state``), so in practice the editable set is often empty and
this pass becomes a no-op. That is intentional — the freeze guard takes absolute
precedence over any quality gain.
"""

from __future__ import annotations

from agents.constants import NOVEL_FORMAT_ZHIHU_SHORT
from services.chapter_progress import is_frozen
from services.outline_hierarchy import extract_volumes, parse_chapter_range
from services.short_story_context import build_short_manuscript_context
from services.novel_constants import SHORT_MANUSCRIPT_CONTEXT_MAX_CHARS
from models.novel import Chapter
from agents.writing.validator_agent import ValidatorAgent
from sqlalchemy import select
from services.workflow_surface import is_short_form_workflow

VOLUME_REVIEW_FLAG_TYPE = "volume_read_through_review"

class FrozenChapterWriteError(RuntimeError):
    """Raised when a revision pass would mutate a published (frozen) chapter."""

def select_volume(outline: dict | None, volume_index: int) -> dict | None:
    """Return the volume at ``volume_index`` (0-based), or None if out of range."""
    volumes = extract_volumes(outline)
    if volume_index < 0 or volume_index >= len(volumes):
        return None
    return volumes[volume_index]

def volume_index_ending_at(outline: dict | None, chapter_index: int) -> int | None:
    """Return the 0-based index of the volume whose range *ends* at
    ``chapter_index``, or None. Used as the trigger: a volume becomes reviewable
    the moment its final chapter is generated.
    """
    for i, vol in enumerate(extract_volumes(outline)):
        span = parse_chapter_range(vol)
        if span and span[1] == chapter_index:
            return i
    return None

def chapters_in_span(chapters: list, span: tuple[int, int] | None) -> list:
    """Chapters whose index falls within an inclusive (start, end) span."""
    if not span:
        return []
    start, end = span
    return [c for c in chapters if start <= c.chapter_index <= end]

def frozen_chapters(chapters: list) -> list:
    return [c for c in chapters if is_frozen(c)]

def editable_chapters(chapters: list) -> list:
    return [c for c in chapters if not is_frozen(c)]

def assert_no_frozen_writes(targets: list) -> None:
    """The red line. Raise if any write target is a published/frozen chapter."""
    frozen = frozen_chapters(targets)
    if frozen:
        indices = ", ".join(str(c.chapter_index) for c in frozen)
        raise FrozenChapterWriteError(
            f"卷级通读修订试图改动已发布章节（第 {indices} 章）；已发布章节为终态，绝不可回改。"
        )

def should_review_volume(novel, editable: list) -> bool:
    """只有走长篇表面的工作流做卷级通读，且只在有未发布内容可改时做。

    按表面策略而不是格式名判断：克隆自长篇的自定义工作流有卷纲，同样需要卷级通读。
    """
    return bool(not is_short_form_workflow(novel.novel_format) and editable)

def append_volume_review_flag(chapter, report: dict) -> None:
    flags = chapter.review_flags if isinstance(chapter.review_flags, list) else []
    flags = [flag for flag in flags if flag.get("type") != VOLUME_REVIEW_FLAG_TYPE]
    message = report.get("summary") or "卷级通读审校已完成。"
    chapter.review_flags = flags + [{
        "type": VOLUME_REVIEW_FLAG_TYPE,
        "severity": "info" if report.get("passed", False) else "warning",
        "message": message,
        "detail": message,
        "report": report,
    }]

async def review_volume(db, novel, volume_index: int) -> dict | None:
    """Read-through the given volume and attach a review flag to its last
    unpublished chapter. Never mutates a published chapter (raises if asked to).

    Returns the report dict, or None when there is nothing to review.
    """
    outline = novel.outline or {}
    volume = select_volume(outline, volume_index)
    span = parse_chapter_range(volume) if volume else None
    if not span:
        return None

    start, end = span
    result = await db.execute(
        select(Chapter)
        .where(
            Chapter.novel_id == novel.id,
            Chapter.chapter_index >= start,
            Chapter.chapter_index <= end,
        )
        .order_by(Chapter.chapter_index.asc())
    )
    chapters = result.scalars().all()
    editable = editable_chapters(chapters)
    if not should_review_volume(novel, editable):
        return None

    manuscript = build_short_manuscript_context(
        chapters,
        max_chars=SHORT_MANUSCRIPT_CONTEXT_MAX_CHARS,
    )
    report = await ValidatorAgent().review_full_story(
        title=f"{novel.title}· {volume.get('卷名') or f'第{volume_index + 1}卷'}",
        outline=outline,
        manuscript=manuscript,
        # `validator_review_full_story` 目前只存在于短篇模板集（prompts/validation/
        # zhihu_short_validation.json）；长篇那份里没有这个名字。卷级通读复用它，因此这里
        # 只能显式指向短篇类别 —— 代价是长篇卷报告用的是短篇的审校维度（开篇承诺、伏笔
        # 公平性、情绪曲线、信息密度、结尾兑现）。给长篇写一份卷级专用模板是独立的一件事。
        category=NOVEL_FORMAT_ZHIHU_SHORT,
    )

    # Red line: the flag lands only on an unpublished chapter, never a frozen one.
    target = editable[-1]
    assert_no_frozen_writes([target])
    append_volume_review_flag(target, report)
    await db.commit()
    return report
