"""Hierarchical outline helpers: Book -> Volume -> Chapter -> Beat.

The skeleton already carries the book layer (创作契约) and a volume grid (卷纲),
and per-chapter outlines carry the chapter layer. What was missing is the glue
between the layers:

* volume selection — given a chapter index, find which volume governs it, so the
  planner is told *this* volume's goal/antagonist/payoff instead of guessing from
  the whole grid.
* beat access — normalize the optional per-chapter beat list so the writer gets a
  scene-by-scene breakdown rather than only coarse key_events.

Pure functions only. No DB, no LLM, no agent imports — safe to call from either
the agents layer or worker_support.
"""

from __future__ import annotations

import re
from typing import Any

# Volumes may spell the chapter span as "1-30", "第1-30章", "1~30", "1—30",
# "1 到 30", etc. Capture the two bounding integers regardless of decoration.
_RANGE_RE = re.compile(r"(\d+)\s*(?:-|~|—|–|至|到)\s*(\d+)")
_SINGLE_RE = re.compile(r"(\d+)")

_VOLUME_KEYS = ("卷纲", "volumes", "卷", "故事阶段")
_RANGE_KEYS = ("章节范围", "chapter_range", "range", "章节", "chapters")


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def extract_volumes(skeleton: dict | None) -> list[dict]:
    """Return the volume grid from a skeleton, tolerant of key spelling."""
    if not isinstance(skeleton, dict):
        return []
    for key in _VOLUME_KEYS:
        volumes = skeleton.get(key)
        if volumes:
            return [v for v in _as_list(volumes) if isinstance(v, dict)]
    return []


def parse_chapter_range(volume: dict) -> tuple[int, int] | None:
    """Parse a volume's chapter span into (start, end), inclusive.

    Returns None when the volume has no parseable range. A lone number is
    treated as a single-chapter span (start == end).
    """
    if not isinstance(volume, dict):
        return None
    raw = ""
    for key in _RANGE_KEYS:
        if volume.get(key):
            raw = str(volume[key])
            break
    if not raw:
        return None

    match = _RANGE_RE.search(raw)
    if match:
        start, end = int(match.group(1)), int(match.group(2))
        return (start, end) if start <= end else (end, start)

    single = _SINGLE_RE.search(raw)
    if single:
        n = int(single.group(1))
        return (n, n)
    return None


def _infer_total(skeleton: dict | None, volumes: list[dict]) -> int:
    if isinstance(skeleton, dict):
        for key in ("total_chapters", "目标总章数", "总章数"):
            if skeleton.get(key):
                found = re.search(r"\d+", str(skeleton[key]))
                if found:
                    return int(found.group())
    # Default assumption: ~25 chapters per volume (matches planner guidance).
    return max(1, len(volumes) * 25)


def select_active_volume(skeleton: dict | None, chapter_index: int) -> dict | None:
    """Find the volume whose chapter range contains ``chapter_index``.

    Falls back to positional inference when ranges are missing: if no volume
    declares a parseable range, split the chapter space evenly across the
    volumes so the planner still gets *a* governing volume. Returns None only
    when there are no volumes at all.
    """
    volumes = extract_volumes(skeleton)
    if not volumes:
        return None

    ranged: list[tuple[tuple[int, int], dict]] = []
    for vol in volumes:
        span = parse_chapter_range(vol)
        if span:
            ranged.append((span, vol))

    for (start, end), vol in ranged:
        if start <= chapter_index <= end:
            return vol

    if ranged:
        # chapter_index sits outside every declared range (e.g. overshoot past
        # the last volume). Snap to the nearest volume by range proximity so the
        # writer still gets the most relevant volume context.
        def distance(item: tuple[tuple[int, int], dict]) -> int:
            (start, end), _ = item
            if chapter_index < start:
                return start - chapter_index
            return chapter_index - end

        return min(ranged, key=distance)[1]

    # No parseable ranges anywhere: infer position by even split.
    total = _infer_total(skeleton, volumes)
    idx = max(1, chapter_index)
    bucket = (idx - 1) * len(volumes) // max(1, total)
    bucket = min(len(volumes) - 1, max(0, bucket))
    return volumes[bucket]


def format_active_volume_hint(volume: dict | None) -> str:
    """Render the governing volume as a compact planner hint block."""
    if not isinstance(volume, dict) or not volume:
        return ""
    labels = (
        "卷名", "幕名", "卷目标", "progress", "核心冲突", "主要对手",
        "升级变化", "阶段兑现", "失败代价", "核心事件", "tension_curve", "章节范围",
    )
    lines = ["【本章所属卷/幕（必须服从本卷目标与阶段兑现）】"]
    for key in labels:
        value = volume.get(key)
        if not value:
            continue
        if isinstance(value, list):
            value = "；".join(str(v) for v in value if v)
        lines.append(f"- {key}：{value}")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def normalize_beats(beats: Any) -> list[dict]:
    """Coerce a planner-returned beat list into a list of {beat, purpose} dicts.

    Accepts a list of strings, a list of dicts, or a single value. Empty/blank
    entries are dropped. Never raises.
    """
    result: list[dict] = []
    for item in _as_list(beats):
        if item is None:
            continue
        if isinstance(item, dict):
            beat = str(item.get("beat") or item.get("节拍") or item.get("content") or "").strip()
            purpose = str(item.get("purpose") or item.get("作用") or item.get("goal") or "").strip()
            if beat:
                entry: dict[str, str] = {"beat": beat}
                if purpose:
                    entry["purpose"] = purpose
                result.append(entry)
        else:
            text = str(item).strip()
            if text:
                result.append({"beat": text})
    return result


def format_beats_hint(beats: Any) -> str:
    """Render normalized beats as an ordered scene breakdown for the writer."""
    normalized = normalize_beats(beats)
    if not normalized:
        return ""
    lines = ["【本章节拍分解（按顺序推进，每个节拍都要落到正文）】"]
    for i, entry in enumerate(normalized, start=1):
        beat = entry["beat"]
        purpose = entry.get("purpose")
        if purpose:
            lines.append(f"{i}. {beat}（作用：{purpose}）")
        else:
            lines.append(f"{i}. {beat}")
    return "\n".join(lines)
