"""Pure, deterministic repairs used when normalizing chapter contracts."""

from __future__ import annotations

import json
import re
from typing import Any


_THREE_READING_PATTERN = re.compile(
    r"(三类潮位(?:记录|读数)[^。；\n]{0,100}?)(?:最大差值|最大相差)九十厘米"
)
_CLOCK_TIME_PATTERN = re.compile(r"(?P<time>\d{1,2}:\d{2}:\d{2})")
_RELATIVE_SECONDS_PATTERN = re.compile(
    r"(?P<number>[零〇一二两三四五六七八九十百千万\d]+)\s*秒(?P<direction>后|前)"
)
_ORDERING_CONFLICT_PATTERNS = (
    (
        re.compile(r"(?P<subject>[^，。；\n]{1,30})同时(?P<first>[^，。；\n]{1,30})，(?P<later>[^，。；\n]{1,30})先(?P<second>[^，。；\n]{1,30})才(?P<action>[^。；\n]{1,30})"),
        lambda match: (
            f"{match.group('subject')}先{match.group('first')}，"
            f"{match.group('later')}随后{match.group('second')}{match.group('action')}"
        ),
    ),
)
_CHINESE_DIGITS = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
_V19_COUNTDOWN_PATTERN = re.compile(
    r"倒计时[^。；\n]{0,24}?(?P<minutes>[零〇一二两三四五六七八九十百千万\d]+)"
    r"\s*分(?:钟)?(?:\s*(?P<seconds>[零〇一二两三四五六七八九十百千万\d]+)\s*秒)?"
    r"|倒计时[^。；\n]{0,24}?(?P<only_seconds>[零〇一二两三四五六七八九十百千万\d]+)\s*秒"
)
_V19_RESET_MARKERS = ("重置", "重新开始", "新周期", "重新校准", "回拨")
_V24_STATE_RESET_MARKERS = _V19_RESET_MARKERS + ("重新生成", "再次生成", "重新执行", "重新写入")
_V24_STATE_RESTATEMENT_PATTERN = re.compile(
    r"(?P<prefix>[^。；\n]{0,100}?)"
    r"从(?:之前|上一章|前一章)(?:的)?[^，。；\n]{1,48}?"
    r"变(?:成|为)(?:了)?[:：]?\s*(?P<value>[^，。；\n]{2,90})"
)


def _contains_any(value: str, terms: tuple[str, ...]) -> bool:
    return any(term in value for term in terms)


def _parse_clock_time(value: str) -> int | None:
    match = re.fullmatch(r"(\d{1,2}):(\d{2}):(\d{2})", value)
    if not match:
        return None
    hour, minute, second = (int(part) for part in match.groups())
    if hour > 23 or minute > 59 or second > 59:
        return None
    return hour * 3600 + minute * 60 + second


def _parse_chinese_integer(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    if len(value) == 1:
        return _CHINESE_DIGITS.get(value)
    if "十" in value:
        left, _, right = value.partition("十")
        tens = _CHINESE_DIGITS.get(left, 1) if left else 1
        ones = _CHINESE_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    return None


def _format_seconds(value: int) -> str:
    if value < 10:
        return "零" + "一二三四五六七八九"[value - 1]
    if value == 10:
        return "十"
    if value < 20:
        return "十" + "一二三四五六七八九"[value - 11]
    tens, ones = divmod(value, 10)
    return "一二三四五六七八九"[tens - 1] + "十" + ("一二三四五六七八九"[ones - 1] if ones else "")


def _format_chinese_number(value: int) -> str:
    if value < 10:
        return "零一两三四五六七八九"[value]
    if value < 20:
        return "十" + ("一二三四五六七八九"[value - 10] if value > 10 else "")
    tens, ones = divmod(value, 10)
    return "一二三四五六七八九"[tens - 1] + "十" + ("一二三四五六七八九"[ones - 1] if ones else "")


def _parse_countdown_match(match: re.Match[str]) -> int | None:
    only_seconds = match.group("only_seconds")
    if only_seconds:
        return _parse_chinese_integer(only_seconds)
    minutes = match.group("minutes")
    if minutes is None:
        return None
    seconds = match.group("seconds")
    minute_value = _parse_chinese_integer(minutes)
    second_value = _parse_chinese_integer(seconds) if seconds else 0
    if minute_value is None or second_value is None or second_value > 59:
        return None
    return minute_value * 60 + second_value


def _format_countdown(value: int) -> str:
    minutes, seconds = divmod(max(0, value), 60)
    if seconds == 0:
        return f"{_format_chinese_number(minutes)}分钟"
    return f"{_format_chinese_number(minutes)}分{_format_chinese_number(seconds)}秒"


def _sanitize_v19_cross_chapter_state(
    text: str,
    handoff: dict[str, Any],
    countdown_state: dict[str, int | None],
) -> str:
    handoff_text = json.dumps(handoff, ensure_ascii=False, default=str)
    previous_closed = (
        _contains_any(handoff_text, ("读取窗口", "访问窗口", "ACL-"))
        and _contains_any(handoff_text, ("关闭", "关掉", "已关闭", "封存", "锁定"))
    )
    if previous_closed:
        text = re.sub(
            r"(?P<actor>[^，。；\n]{0,12}?)(?:关掉|关闭)(?P<target>[A-Za-z0-9_-]*(?:限定)?(?:只读)?(?:读取|访问)窗口)",
            lambda match: f"{match.group('actor')}确认{match.group('target')}仍处于只读封存状态",
            text,
        )
    # V22 owns countdown normalization and keeps one precise value per cycle.
    return text


def _sanitize_v22_single_countdown(text: str, countdown_state: dict[str, int | None]) -> str:
    """Keep one precise countdown per chapter unless a new cycle is explicit."""
    replacements: list[tuple[int, int, str]] = []
    matches = list(_V19_COUNTDOWN_PATTERN.finditer(text))
    for match in matches:
        current = _parse_countdown_match(match)
        if current is None:
            continue
        nearby = text[max(0, match.start() - 24):match.start()]
        if any(marker in nearby for marker in _V19_RESET_MARKERS):
            countdown_state["value"] = current
            continue
        if countdown_state.get("value") is None:
            countdown_state["value"] = current
            continue
        replacements.append((match.start(), match.end(), "倒计时继续递减"))
    if matches:
        first_end = matches[0].end()
        sentence_end = next(
            (index for index in (text.find("。", first_end), text.find("；", first_end), text.find("\n", first_end)) if index >= 0),
            len(text),
        )
        tail = text[first_end:sentence_end]
        tail_re = re.compile(
            r"(?:从|变为|剩余|还剩|降到|跳到)\s*[零〇一二两三四五六七八九十百千万\d]+\s*分(?:钟)?(?:\s*[零〇一二两三四五六七八九十百千万\d]+\s*秒)?"
            r"|(?:从|变为|剩余|还剩|降到|跳到)\s*[零〇一二两三四五六七八九十百千万\d]+\s*秒"
        )
        tail_match = tail_re.search(tail)
        if tail_match:
            replacements.append((first_end + tail_match.start(), first_end + tail_match.end(), "，倒计时继续递减"))
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text


def _sanitize_v23_unmapped_relative_minutes(text: str) -> str:
    """Avoid unsupported exact relative durations beside absolute clocks."""
    if len(_CLOCK_TIME_PATTERN.findall(text)) < 2:
        return text
    relative = re.compile(
        r"(?P<number>[零〇一二两三四五六七八九十百千万\d]+)\s*分钟(?P<direction>后|前)"
    )
    replacements: list[tuple[int, int, str]] = []
    for match in relative.finditer(text):
        previous = next((item for item in reversed(list(_CLOCK_TIME_PATTERN.finditer(text))) if item.end() <= match.start()), None)
        following = next((item for item in _CLOCK_TIME_PATTERN.finditer(text) if item.start() >= match.end()), None)
        claimed = _parse_chinese_integer(match.group("number"))
        if previous is None or following is None or claimed is None:
            continue
        start = _parse_clock_time(previous.group("time"))
        target = _parse_clock_time(following.group("time"))
        if start is None or target is None:
            continue
        if abs(target - start) // 60 != claimed:
            replacements.append((match.start(), match.end(), "随后"))
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text


def _sanitize_v24_inherited_state_restatements(text: str, handoff: dict[str, Any]) -> str:
    """Keep an inherited value from being narrated as a new transition."""
    inherited = handoff.get("inherited_state") or []
    handoff_text = json.dumps(handoff, ensure_ascii=False, default=str)
    if not inherited and not handoff_text:
        return text
    replacements: list[tuple[int, int, str]] = []
    for match in _V24_STATE_RESTATEMENT_PATTERN.finditer(text):
        nearby = text[max(0, match.start() - 100):match.start()] + match.group("prefix")
        if any(marker in nearby for marker in _V24_STATE_RESET_MARKERS):
            continue
        value = match.group("value").strip()
        identifiers = set(re.findall(r"[A-Za-z]{2,}[\w-]*[-_]\d+", value))
        if not identifiers or not any(identifier in handoff_text for identifier in identifiers):
            continue
        prefix = match.group("prefix").rstrip()
        replacements.append((match.start(), match.end(), f"{prefix}仍保持：{value}"))
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text


def _sanitize_v17_relative_times(text: str) -> str:
    """Align a relative-second claim with adjacent absolute clock times."""
    matches = list(_CLOCK_TIME_PATTERN.finditer(text))
    if len(matches) < 2:
        return text
    replacements: list[tuple[int, int, str]] = []
    for relative in _RELATIVE_SECONDS_PATTERN.finditer(text):
        previous = next((item for item in reversed(matches) if item.end() <= relative.start()), None)
        following = next((item for item in matches if item.start() >= relative.end()), None)
        if previous is None or following is None:
            continue
        start = _parse_clock_time(previous.group("time"))
        target = _parse_clock_time(following.group("time"))
        claimed = _parse_chinese_integer(relative.group("number"))
        if start is None or target is None or claimed is None:
            continue
        delta = target - start
        if relative.group("direction") == "前":
            delta = -delta
        if delta < 0 or delta > 3600 or delta == claimed:
            continue
        replacements.append((relative.start("number"), relative.end("number"), _format_seconds(delta)))
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text


def _sanitize_v18_event_order(text: str) -> str:
    """Resolve explicit same-event ordering contradictions in contract text."""
    for pattern, replacement in _ORDERING_CONFLICT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def sanitize_contract_text(
    value: str,
    unknown_boundary: list[str],
    handoff: dict[str, Any] | None = None,
    countdown_state: dict[str, int | None] | None = None,
) -> str:
    """Repair deterministic contract contradictions before LLM prompts."""
    text = str(value)
    if _THREE_READING_PATTERN.search(text):
        text = _THREE_READING_PATTERN.sub(
            lambda match: f"{match.group(1)}存在九十厘米的相邻读数差异，最大差值为一百八十厘米",
            text,
        )
    unknown_text = " ".join(unknown_boundary)
    if "继电器" in text and "旧维护区" in text and any(
        marker in unknown_text for marker in ("来源", "地点", "位置", "设备")
    ):
        text = re.sub(
            r"旧维护区(?:传出|出现|附近出现|方向的)?(?:一次)?继电器(?:吸合)?声",
            "无法定位来源的继电器吸合声",
            text,
        )
    state = countdown_state if countdown_state is not None else {}
    text = _sanitize_v17_relative_times(text)
    text = _sanitize_v18_event_order(text)
    text = _sanitize_v22_single_countdown(text, state)
    text = _sanitize_v19_cross_chapter_state(text, handoff or {}, state)
    text = _sanitize_v23_unmapped_relative_minutes(text)
    text = _sanitize_v24_inherited_state_restatements(text, handoff or {})
    return text


def sanitize_outline_values(
    value: Any,
    unknown_boundary: list[str],
    handoff: dict[str, Any] | None = None,
    countdown_state: dict[str, int | None] | None = None,
) -> Any:
    if isinstance(value, str):
        return sanitize_contract_text(value, unknown_boundary, handoff, countdown_state)
    if isinstance(value, list):
        return [sanitize_outline_values(item, unknown_boundary, handoff, countdown_state) for item in value]
    if isinstance(value, dict):
        return {
            key: sanitize_outline_values(item, unknown_boundary, handoff, countdown_state)
            for key, item in value.items()
        }
    return value


# Preserve the old private helper names for focused imports and diagnostics.
_sanitize_v16_contract_text = sanitize_contract_text
_sanitize_v16_outline_values = sanitize_outline_values

