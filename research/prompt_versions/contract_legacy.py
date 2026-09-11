"""V0–V42 的章节契约构建器（冻结副本）。

生产冻结在 A28/V43 后，`services/continuity_contract.py` 里的版本门被按 V43 求值
并内联，因此**低于 V43** 的契约行为无法再从生产代码里恢复。该模块是重构前那份
带完整版本门的实现的逐字节冻结副本，用于复现 V0–V42 的实验。

* 只读。不要在这里修复 bug 或加新版本——它的价值就在于与历史实验一致。
* 生产不导入本模块。入口是 `services/version_surface.research_override`
  在版本低于 V43 时把契约调用整体路由过来。
* 私有 helper 是完整副本，与 `services/continuity_contract.py` 各自独立演进。
"""


from __future__ import annotations

import json
import re
from typing import Any

from services.context_compaction import compact_items, compact_json, compact_text

from research.prompt_versions.version_order import prompt_version_at_least
from services.version_surface import NO_OVERRIDE, research_override


_UNKNOWN_MARKERS = ("不得", "不能", "禁止", "未知", "未确认", "不确定", "无法确认", "不可推断")
_COMMON_UNKNOWN_TERMS = {
    "不得", "不能", "禁止", "未知", "确认", "推断", "上一章", "本章", "未来",
    "事实", "内容", "明确", "状态", "场景", "角色", "信息", "只能", "不要",
}
_EQUIVALENT_TERMS = (
    ("声音", "语音", "录音", "说话"),
    ("灯塔", "信标"),
    ("父亲", "爸爸", "父亲本人"),
    ("活着", "存活", "仍然存在"),
)
_RELATION_GROUPS = (
    ("声音", "语音", "录音", "说话"),
    ("上传", "写下", "作者", "写入", "来源"),
    ("身份", "属于", "本人"),
    ("地点", "位置", "位于", "拍摄", "现场"),
    ("设备", "采集", "来源设备"),
    ("运行", "功能", "中继"),
    ("原因", "因果", "形成"),
    ("死亡", "生死", "存活"),
    ("归属", "所属"),
)
_UNCERTAINTY_MARKERS = (
    "未知",
    "无法确认",
    "不能确认",
    "尚未确认",
    "未确认",
    "证据不足",
    "不确定",
    "待调查",
    "待核对",
    "尚不清楚",
    "无法证明",
    "不能证明",
)


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]
_ASSERTION_MARKERS = (
    "确认",
    "证明",
    "揭示",
    "确定",
    "就是",
    "属于",
    "确实是",
    "已经是",
    "仍然是",
)

_V11_REVOCATION_TERMS = (
    "撤回",
    "已关闭",
    "关闭",
    "已失效",
    "失效",
    "锁定",
    "已锁定",
    "结束",
    "到期",
)
_V11_PERMISSION_TERMS = (
    "权限",
    "授权",
    "访问窗口",
    "只读",
    "可见字段",
)
_V11_COUNTDOWN_TERMS = ("倒计时", "九秒", "计数器", "帧周期")
_V11_STAGE_TERMS = ("阶段性结论", "同一异常事件链", "阶段结论")
_V12_SOURCE_TERMS = (
    "来源",
    "来源字段",
    "读取来源",
    "监测窗口",
    "帧",
    "执行回执",
    "设备侧",
    "实体影响",
)
_V12_POST_STATE_TERMS = (
    "关闭执行登记",
    "只读监测",
    "关闭后",
    "关闭流程",
    "重新开放",
)
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


def _as_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        value = [] if value in (None, "") else [value]
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _normalize_unique_action_ledger(value: Any) -> list[dict[str, Any]]:
    """Keep one compact operation entry per chapter action surface."""
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _as_list(value):
        if isinstance(item, dict):
            operation = str(
                item.get("operation") or item.get("action") or item.get("name") or ""
            ).strip()
            if not operation:
                continue
            entry = {
                "operation": operation,
                "response": compact_text(item.get("response"), 240),
                "change": compact_text(item.get("change") or item.get("consequence"), 240),
            }
            entry = {key: value for key, value in entry.items() if value}
        else:
            operation = str(item or "").strip()
            if not operation:
                continue
            entry = {"operation": compact_text(operation, 240)}
        key = entry["operation"]
        if key in seen:
            continue
        seen.add(key)
        normalized.append(entry)
        if len(normalized) >= 6:
            break
    return normalized


def _normalize_primary_action(value: Any) -> dict[str, str]:
    """Normalize V55's single narrative turn without adding a model call."""
    if isinstance(value, str):
        action = value.strip()
        return {"action": compact_text(action, 320)} if action else {}
    if not isinstance(value, dict):
        return {}
    aliases = {
        "action": ("action", "operation", "choice"),
        "response": ("response", "observed_response", "result"),
        "decision": ("decision", "next_choice", "character_decision"),
        "cost_or_risk": ("cost_or_risk", "cost", "risk", "price"),
        "new_stage": ("new_stage", "change", "consequence", "stage_delta"),
    }
    normalized: dict[str, str] = {}
    for key, candidates in aliases.items():
        for candidate in candidates:
            text = compact_text(value.get(candidate), 320)
            if text:
                normalized[key] = text
                break
    return normalized


def _normalize_character_turn(value: Any) -> dict[str, str]:
    """Normalize V56's grounded character motivation without inventing facts."""
    if not isinstance(value, dict):
        return {}
    aliases = {
        "actor": ("actor", "character", "character_name", "name"),
        "goal": ("goal", "immediate_goal", "objective"),
        "pressure": ("pressure", "conflict", "obstacle"),
        "choice_basis": ("choice_basis", "basis", "reason", "motivation"),
        "choice": ("choice", "decision", "action"),
        "personal_cost": ("personal_cost", "cost", "risk", "price"),
        "state_change": ("state_change", "change", "consequence", "new_stage"),
    }
    normalized: dict[str, str] = {}
    for key, candidates in aliases.items():
        for candidate in candidates:
            text = compact_text(value.get(candidate), 320)
            if text:
                normalized[key] = text
                break
    return normalized


def _derive_character_turn(
    character_turn: dict[str, str],
    outline: dict[str, Any],
    primary_action: dict[str, str],
) -> dict[str, str]:
    """Fill missing turn fields only from already supplied outline evidence."""
    goals = outline.get("character_goals") if isinstance(outline, dict) else []
    goal = next((item for item in _as_list(goals) if isinstance(item, dict)), {})
    fallbacks = {
        "actor": goal.get("character_name") or goal.get("name") or "",
        "goal": goal.get("goal") or "",
        "pressure": goal.get("conflict") or "",
        "choice_basis": primary_action.get("response") or primary_action.get("action") or goal.get("conflict") or "",
        "choice": primary_action.get("decision") or goal.get("state_change") or "",
        "personal_cost": primary_action.get("cost_or_risk") or goal.get("conflict") or "",
        "state_change": primary_action.get("new_stage") or goal.get("state_change") or "",
    }
    return {
        key: value
        for key, value in {
            **fallbacks,
            **character_turn,
        }.items()
        if compact_text(value, 320)
    }


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


def _last_countdown_value(text: str) -> int | None:
    values = [
        parsed
        for match in _V19_COUNTDOWN_PATTERN.finditer(text)
        if (parsed := _parse_countdown_match(match)) is not None
    ]
    return values[-1] if values else None


def _sanitize_v19_cross_chapter_state(
    text: str,
    handoff: dict[str, Any],
    countdown_state: dict[str, int | None],
) -> str:
    if not _prompt_version_at_least("V19"):
        return text
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

    # V22 owns countdown normalization and deliberately keeps one precise
    # value per cycle. Do not let the V19 cross-chapter decrement rewrite it.
    if _prompt_version_at_least("V22"):
        return text

    if countdown_state.get("value") is None:
        countdown_state["value"] = _last_countdown_value(handoff_text)
    replacements: list[tuple[int, int, str]] = []
    for match in _V19_COUNTDOWN_PATTERN.finditer(text):
        current = _parse_countdown_match(match)
        if current is None:
            continue
        nearby = text[max(0, match.start() - 24):match.start()]
        if any(marker in nearby for marker in _V19_RESET_MARKERS):
            countdown_state["value"] = current
            continue
        previous = countdown_state.get("value")
        if previous is not None and current >= previous:
            replacement = max(0, previous - 1)
            start_group = "minutes" if match.group("minutes") else "only_seconds"
            end_group = "seconds" if match.group("seconds") else start_group
            end = match.end(end_group)
            if match.group("seconds"):
                if text[end:end + 1] == "秒":
                    end += 1
            elif match.group("minutes"):
                if text[end:end + 2] == "分钟":
                    end += 2
                elif text[end:end + 1] == "分":
                    end += 1
            replacements.append((match.start(start_group), end, _format_countdown(replacement)))
            countdown_state["value"] = replacement
        else:
            countdown_state["value"] = current
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text


def _sanitize_v22_single_countdown(
    text: str,
    countdown_state: dict[str, int | None],
) -> str:
    """Keep one precise countdown per chapter unless a new cycle is explicit."""
    if not _prompt_version_at_least("V22"):
        return text
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
        if tail_re.search(tail):
            start = first_end + tail_re.search(tail).start()
            end = first_end + tail_re.search(tail).end()
            replacements.append((start, end, "，倒计时继续递减"))
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text


def _sanitize_v23_unmapped_relative_minutes(text: str) -> str:
    """Avoid unsupported exact relative durations beside absolute clocks."""
    if not _prompt_version_at_least("V23"):
        return text
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
        delta = abs(target - start) // 60
        if delta == claimed:
            continue
        replacements.append((match.start(), match.end(), "随后"))
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text


def _sanitize_v24_inherited_state_restatements(
    text: str,
    handoff: dict[str, Any],
) -> str:
    """Keep an inherited value from being narrated as a new transition."""
    if not _prompt_version_at_least("V24"):
        return text
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
    if not _prompt_version_at_least("V17"):
        return text
    matches = list(_CLOCK_TIME_PATTERN.finditer(text))
    if len(matches) < 2:
        return text
    relative_matches = list(_RELATIVE_SECONDS_PATTERN.finditer(text))
    replacements: list[tuple[int, int, str]] = []
    for relative in relative_matches:
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
    if not _prompt_version_at_least("V18"):
        return text
    for pattern, replacement in _ORDERING_CONFLICT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _sanitize_v16_contract_text(
    value: str,
    unknown_boundary: list[str],
    handoff: dict[str, Any] | None = None,
    countdown_state: dict[str, int | None] | None = None,
) -> str:
    """Repair deterministic contract contradictions before LLM prompts.

    Planner prose is retained as the raw experiment artifact.  This pass only
    changes the downstream copy when a statement is mechanically inconsistent
    with its own numbers or explicitly violates an unknown boundary.
    """
    text = str(value)
    if _prompt_version_at_least("V16"):
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
    text = _sanitize_v17_relative_times(text)
    text = _sanitize_v18_event_order(text)
    text = _sanitize_v22_single_countdown(
        text,
        countdown_state if countdown_state is not None else {},
    )
    text = _sanitize_v19_cross_chapter_state(
        text,
        handoff or {},
        countdown_state if countdown_state is not None else {},
    )
    text = _sanitize_v23_unmapped_relative_minutes(text)
    text = _sanitize_v24_inherited_state_restatements(text, handoff or {})
    return text


def _sanitize_v16_outline_values(
    value: Any,
    unknown_boundary: list[str],
    handoff: dict[str, Any] | None = None,
    countdown_state: dict[str, int | None] | None = None,
) -> Any:
    if isinstance(value, str):
        return _sanitize_v16_contract_text(value, unknown_boundary, handoff, countdown_state)
    if isinstance(value, list):
        return [_sanitize_v16_outline_values(item, unknown_boundary, handoff, countdown_state) for item in value]
    if isinstance(value, dict):
        return {
            key: _sanitize_v16_outline_values(item, unknown_boundary, handoff, countdown_state)
            for key, item in value.items()
        }
    return value


def _bigrams(value: str) -> set[str]:
    compact = "".join(ch for ch in str(value) if not ch.isspace())
    return {compact[index:index + 2] for index in range(max(0, len(compact) - 1))}


def _boundary_anchors(value: str) -> set[str]:
    anchors = {
        gram for gram in _bigrams(value)
        if gram not in _COMMON_UNKNOWN_TERMS
    }
    for group in _EQUIVALENT_TERMS:
        if any(term in value for term in group):
            anchors.add("|".join(group))
    return anchors


def _relation_groups(value: str) -> set[str]:
    return {
        "|".join(group)
        for group in _RELATION_GROUPS
        if any(term in value for term in group)
    }


def _has_uncertainty_language(value: str) -> bool:
    return any(marker in value for marker in _UNCERTAINTY_MARKERS)


def _event_conflicts_with_unknown(event: str, boundary: str) -> bool:
    """Detect a direct claim while allowing observation and investigation actions.

    Shared nouns alone are not enough: an event that observes an image or
    records a timestamp will naturally mention the same entity as the
    boundary.  A conflict requires assertion language, a shared relation
    category, and a shared subject anchor.
    """
    if not any(marker in boundary for marker in _UNKNOWN_MARKERS):
        return False
    if _has_uncertainty_language(event):
        return False
    if not any(marker in event for marker in _ASSERTION_MARKERS):
        return False

    shared_anchors = _boundary_anchors(event) & _boundary_anchors(boundary)
    shared_relations = _relation_groups(event) & _relation_groups(boundary)
    if not shared_anchors or not shared_relations:
        return False
    return True


def _safe_required_events(events: list[str], unknown_boundary: list[str]) -> tuple[list[str], list[str]]:
    safe: list[str] = []
    uncertain: list[str] = []
    for event in _dedupe(events):
        if any(_event_conflicts_with_unknown(event, boundary) for boundary in unknown_boundary):
            uncertain.append(event)
        else:
            safe.append(event)
    return safe, uncertain


def _contains_any(value: str, terms: tuple[str, ...]) -> bool:
    return any(term in value for term in terms)


def _contains_positive_claim(value: str, terms: tuple[str, ...]) -> bool:
    """Match a claim while ignoring nearby explicit absence markers."""
    absence_markers = ("未提供", "未确认", "未知", "没有", "无", "缺失", "不能")
    for term in terms:
        start = 0
        while True:
            index = value.find(term, start)
            if index < 0:
                break
            window = value[max(0, index - 16): index + len(term) + 16]
            if not any(marker in window for marker in absence_markers):
                return True
            start = index + len(term)
    return False


def _build_v11_state_boundaries(
    outline: dict[str, Any],
    handoff: dict[str, Any],
    contract: dict[str, Any],
) -> tuple[list[dict[str, str]], list[str]]:
    """Create deterministic state-scope rules for downstream agents.

    V10 reduced duplicate context but still allowed a static permission scope,
    a revoked current permission, and a new countdown cycle to appear as
    equally current prose. These rules are derived from existing structured
    inputs and do not require an extra model call.
    """
    handoff_text = json.dumps(handoff, ensure_ascii=False, default=str)
    outline_text = json.dumps(outline, ensure_ascii=False, default=str)
    all_text = f"{handoff_text}\n{outline_text}"
    state_rules: list[dict[str, str]] = []
    claim_rules: list[str] = []

    if _contains_any(all_text, _V11_PERMISSION_TERMS) and _contains_any(all_text, _V11_REVOCATION_TERMS):
        state_rules.append({
            "state": "authorization",
            "inherited_scope": "历史授权范围/可见字段说明",
            "current_scope": "以撤回、关闭、失效或锁定状态为准",
            "rule": "历史权限范围不得写成当前仍可使用的权限；当前权限状态优先于授权时长和可见字段列表。",
        })

    if _contains_any(all_text, _V11_COUNTDOWN_TERMS):
        state_rules.append({
            "state": "countdown_cycle",
            "inherited_scope": "上一章结尾已记录的计数器/帧周期状态",
            "current_scope": "本章新出现的计数器状态必须标注为新周期或明确承接同一周期",
            "rule": "不得把同一计数器从旧状态无说明地重置；再次从起点开始必须明确上一周期如何结束以及这是新的周期。",
        })

    if _contains_any(all_text, _V11_STAGE_TERMS) or contract.get("foreshadowing_actions"):
        claim_rules.append(
            "阶段性结论必须明确写出已确认的范围，同时保留发送者、操作者、完整链路和具体因果等未确认边界；不能用更弱的模糊关联句替代契约要求，也不能把阶段性结论扩展成最终因果。"
        )

    claim_rules.append(
        "上一章交接状态是本章开场的继承事实；start_state 只描述继承与当前缺口，state_changes/end_state 才能引入本章发生的新状态。"
    )
    return state_rules, list(dict.fromkeys(claim_rules))


def _build_v12_evidence_surface_rules(
    outline: dict[str, Any],
    handoff: dict[str, Any],
) -> tuple[list[dict[str, str]], list[str]]:
    """Keep observation surfaces distinct without another model call."""
    all_text = "\n".join(
        json.dumps(value, ensure_ascii=False, default=str)
        for value in (handoff, outline)
    )
    rules: list[dict[str, str]] = []
    claims: list[str] = []

    # V27 keeps evidence ledgers authoritative but stops inferring a visible
    # four-surface checklist from generic words such as "回执" or "来源".
    # A handoff with an actual evidence ledger still receives the full rule.
    explicit_evidence_ledger = bool(handoff.get("evidence_state_ledger"))
    v27 = prompt_version_at_least("V27")

    if _contains_any(all_text, _V12_SOURCE_TERMS) and (not v27 or explicit_evidence_ledger):
        rules.append(
            {
                "surface": "evidence_source_surfaces",
                "read_path_source": "读取路径/监测窗口，只说明记录从哪里被读到",
                "frame_source_field": "帧内来源字段，只说明原始记录中是否填写来源",
                "device_execution_source": "设备侧执行回执或来源，只能以设备记录直接支持的范围为准",
                "physical_effect": "实体影响，必须有实体反馈或执行证据；缺失时保持 unknown",
                "rule": "四个面不能用同一个‘来源’短语互相替代；缺失字段不得从读取路径、结构对应或空署名推断。",
            }
        )

    exact_ending = str(handoff.get("exact_ending") or "")
    inherited_text = json.dumps(
        handoff.get("inherited_state") or [], ensure_ascii=False, default=str
    )
    explicit_closed_window = _contains_any(
        f"{exact_ending}\n{inherited_text}",
        ("窗口已关闭", "窗口关闭", "读取窗口已关闭", "执行登记已关闭", "封存窗口"),
    )
    if _contains_any(all_text, _V12_POST_STATE_TERMS) and (
        not v27 or explicit_closed_window
    ):
        rules.append(
            {
                "surface": "post_transition_read_only_observation",
                "required_state": "关闭执行登记完成，控制链仍保持关闭且未重新开放",
                "observation_scope": "新响应只能出现在关闭后保留的只读监测列表中",
                "rule": "关闭后的只读监测记录不是控制链回滚，也不是新的执行授权。",
            }
        )

    # V12 历史上对每个证据密集章节都注入这条 claim。Ariadne A7+ 的契约卫生规则
    # 改为只在交接包/大纲确实引入了阶段性校准或报告主张时才保留它——否则 Validator
    # 会为本章根本无权建立的条件索要证据。
    #
    # 生产冻结在 A28（28 >= 7），因此卫生规则无条件生效。研究运行若需要 A7 以下的
    # 历史行为，通过 `evidence_surface_staged_claim` 表面覆盖。
    staged_claim_required = _contains_positive_claim(
        all_text,
        ("共同校准脉冲", "阶段性报告", "阶段性结论", "同一异常事件链"),
    )
    override = research_override("evidence_surface_staged_claim", all_text)
    if override is not NO_OVERRIDE:
        staged_claim_required = bool(override)
    if staged_claim_required:
        claims.append(
            "阶段性证据链必须写成‘基于共同校准脉冲形成的阶段性报告结论’；它只表示证据链归并或结构/周期对应，不表示同源、因果、归属、发送者或操作者已确认。"
        )
    claims.append(
        "当正文同时出现读取路径、来源字段和设备回执时，必须使用不同的限定词；‘来源显示为’不得同时承担读取路径和帧内来源字段两种含义。"
    )
    return rules, list(dict.fromkeys(claims))


def _build_v40_end_state_boundary(contract: dict[str, Any]) -> dict[str, Any]:
    """Project one terminal-state rule for all downstream agents.

    The Planner payload remains the raw research artifact. This projection
    gives Writer, Editor, and Validator the same precedence rule when beats
    and ``end_state`` use slightly different action wording.
    """
    return {
        "authority": "terminal_chapter_state",
        "final_state": str(contract.get("end_state") or ""),
        "rule": (
            "end_state 表示本章最后已经成立的可观察状态；beats、required_events 和 state_changes "
            "不得把正文推进到该状态之后。"
        ),
        "resolution": (
            "若出现‘准备/决定/将要’与‘已经完成’的轻微措辞差异，先按 end_state 的终态解释并由 Editor 局部统一；"
            "只有正文真实改变已接受事实、时间线、物品/地点状态或核心事件时才阻断。"
        ),
    }


def build_dramatic_turn_projection(contract: dict[str, Any] | None) -> dict[str, Any]:
    """Project existing goal/beat data into a small narrative execution spine.

    V46 deliberately does not invent story facts. It only reshapes fields the
    Planner already produced so generation and review agents share the same
    goal -> pressure -> choice -> consequence vocabulary.
    """
    data = contract if isinstance(contract, dict) else {}
    goals = _as_list(data.get("character_goals"))
    primary = next((item for item in goals if isinstance(item, dict)), {})
    if not primary and goals:
        primary = {"goal": str(goals[0])}

    def first_text(*keys: str) -> str:
        for key in keys:
            value = primary.get(key)
            if value not in (None, "", [], {}):
                return compact_text(value, 360)
        return ""

    projected_beats: list[Any] = []
    for beat in _as_list(data.get("beats"))[:3]:
        if isinstance(beat, dict):
            projected = {
                key: compact_text(beat.get(key), 260)
                for key in (
                    "beat",
                    "action",
                    "purpose",
                    "obstacle",
                    "choice",
                    "consequence",
                    "cost",
                )
                if beat.get(key) not in (None, "", [], {})
            }
            if projected:
                projected_beats.append(projected)
        elif beat not in (None, ""):
            projected_beats.append({"beat": compact_text(beat, 300)})

    consequence = first_text("consequence", "state_change", "change")
    if not consequence:
        consequence = compact_text(data.get("end_state"), 360)
    return {
        "primary_character": first_text("character_name", "name", "character"),
        "goal": first_text("goal", "objective"),
        "pressure": first_text("conflict", "obstacle", "pressure"),
        "choice": first_text("choice", "decision", "action"),
        "consequence": consequence,
        "emotional_arc": compact_text(data.get("emotional_arc"), 360),
        "beats": projected_beats,
    }


def build_chapter_contract(
    outline: dict[str, Any] | None,
    handoff: dict[str, Any] | None = None,
    *,
    enforce_authority: bool | None = None,
) -> dict[str, Any]:
    outline = outline if isinstance(outline, dict) else {}
    handoff = handoff if isinstance(handoff, dict) else {}
    if enforce_authority is None:
        enforce_authority = prompt_version_at_least("V3")

    handoff_unknown = _as_strings(handoff.get("unknown_boundary"))
    outline_unknown = _as_strings(outline.get("unknown_boundary"))
    unknown_boundary = _dedupe(handoff_unknown + outline_unknown)
    # Planner V2+ emits a smaller executable contract alongside descriptive
    # key_events.  Prefer it when present; older saved outlines fall back to
    # key_events so they remain compatible with the research runs.
    required_events = _as_strings(outline.get("required_events"))
    if not required_events:
        required_events = _as_strings(outline.get("key_events"))
    existing_uncertain_events = _as_strings(outline.get("uncertain_events"))
    if enforce_authority:
        required_events, moved_uncertain_events = _safe_required_events(
            required_events,
            unknown_boundary,
        )
        uncertain_events = _dedupe(existing_uncertain_events + moved_uncertain_events)
    else:
        uncertain_events = existing_uncertain_events
    forbidden_deviations = _as_strings(
        outline.get("forbidden_deviations")
        or outline.get("forbidden_changes")
    )
    if enforce_authority:
        forbidden_deviations = _dedupe(
            forbidden_deviations
            + ["不得把 unknown 或 candidate/generated 线索写成已确认身份、因果、生死或地点事实。"]
        )

    primary_action = _normalize_primary_action(outline.get("primary_action"))
    character_turn = _normalize_character_turn(outline.get("character_turn"))
    if _prompt_version_at_least("V58"):
        character_turn = _derive_character_turn(character_turn, outline, primary_action)

    contract = {
        "required_events": required_events,
        "continuity_from_previous": _as_strings(
            outline.get("continuity_from_previous")
            or ([handoff.get("next_hook")] if handoff.get("next_hook") else [])
            or handoff.get("open_questions")
            or []
        ),
        "new_stage_delta": _as_strings(outline.get("new_stage_delta")),
        "unique_action_ledger": _normalize_unique_action_ledger(
            outline.get("unique_action_ledger")
        ),
        "primary_action": primary_action,
        "character_turn": character_turn,
        "state_changes": _as_strings(
            outline.get("state_changes")
            or outline.get("required_changes")
            or []
        ),
        "foreshadowing_actions": _as_strings(
            outline.get("foreshadowing_actions")
            or outline.get("related_foreshadowing")
            or []
        ),
        "end_state": outline.get("end_state") or "",
        "item_state_ledger": handoff.get("item_state_ledger") or [],
        "evidence_state_ledger": handoff.get("evidence_state_ledger") or [],
        "evidence_boundaries": _as_strings(handoff.get("evidence_boundaries")),
        "forbidden_deviations": forbidden_deviations,
        "unknown_boundary": unknown_boundary,
    }
    if _prompt_version_at_least("V53"):
        prior_events = handoff.get("completed_event_ledger") or []
        prior_terminal = handoff.get("previous_terminal_state") or {}
        contract["previous_progress"] = {
            "completed_event_ledger": compact_items(
                prior_events, max_items=8, item_chars=360, keep="tail"
            ),
            "previous_terminal_state": prior_terminal,
        }
        contract["forbidden_deviations"] = _dedupe(
            contract.get("forbidden_deviations", [])
            + [
                "不得把 completed_event_ledger 中已经完成的动作、响应或终态再次完整执行；必须产生非空 new_stage_delta。",
            ]
        )
    if _prompt_version_at_least("V54"):
        contract["forbidden_deviations"] = _dedupe(
            contract.get("forbidden_deviations", [])
            + [
                "同一 unique_action_ledger 操作在本章最多执行一次；后续只能观察其响应或作出新的选择。",
                "未知字段只能写成待判定、未返回或匹配结果为空，不得写成已确认属性。",
            ]
        )
    if _prompt_version_at_least("V55"):
        contract["forbidden_deviations"] = _dedupe(
            contract.get("forbidden_deviations", [])
            + [
                "本章只保留一个核心动作、一个可观察回应和一个角色决策/代价；不得用第二轮查询、确认或解释替代决策。",
            ]
        )
    if _prompt_version_at_least("V56"):
        contract["forbidden_deviations"] = _dedupe(
            contract.get("forbidden_deviations", [])
            + [
                "character_turn 只能使用角色卡、已发生状态或本章可见压力；不得凭空补写性格、背景、关系、能力或动机。",
                "primary_action 说明发生了什么，character_turn 说明角色为何在当前压力下这样选择；二者不得变成第二套重复动作。",
            ]
        )
    if _prompt_version_at_least("V46"):
        contract.update(
            {
                "character_goals": _as_list(outline.get("character_goals")),
                "emotional_arc": outline.get("emotional_arc") or "",
                "beats": _as_list(outline.get("beats")),
            }
        )
    if enforce_authority:
        contract.update(
            {
                "uncertain_events": uncertain_events,
                "authority_policy": {
                    "direct_fact_levels": ["published", "user", "frozen", "accepted"],
                    "clue_only_levels": ["candidate", "generated"],
                "unknown_action": "可描写观察、疑问和调查动作，但禁止补全结论。",
                "evidence_relation_policy": "关联/相似/指向不等于归属、执行、身份或因果确认。",
                },
                "authoritative_sources": [
                    {"source": "published_chapter", "authority": "published"},
                    {"source": "user_setting_or_frozen_character_card", "authority": "frozen"},
                    {"source": "accepted_layered_memory", "authority": "accepted"},
                    {"source": "current_chapter_contract", "authority": "accepted"},
                ],
            }
        )
        if _prompt_version_at_least("V11"):
            state_boundary_rules, claim_boundary_rules = _build_v11_state_boundaries(
                outline,
                handoff,
                contract,
            )
            contract["state_boundary_rules"] = state_boundary_rules
            contract["claim_boundary_rules"] = claim_boundary_rules
        if _prompt_version_at_least("V12"):
            evidence_surface_rules, evidence_surface_claims = _build_v12_evidence_surface_rules(
                outline,
                handoff,
            )
            contract["evidence_surface_rules"] = evidence_surface_rules
            contract["evidence_surface_claims"] = evidence_surface_claims
        if _prompt_version_at_least("V19"):
            contract.setdefault("state_boundary_rules", []).extend(
                [
                    {
                        "state": "post_closure_window",
                        "rule": "上一章已关闭或封存的读取/访问窗口，本章只能确认其封存状态；重新开启必须明确操作人、范围和关闭过程。",
                    },
                    {
                        "state": "countdown_monotonic",
                        "rule": "同一倒计时沿用上一章状态并单向递减；数值回升必须明确标注重置、校准或新周期。",
                    },
                ]
            )
        if _prompt_version_at_least("V22"):
            contract.setdefault("state_boundary_rules", []).append(
                {
                    "state": "single_precise_countdown",
                    "rule": "同一章节同一倒计时周期只保留一个精确数值；后续只能写继续递减或事件推进。新的精确值必须明确标注重置、校准或新周期。",
                }
            )
        if _prompt_version_at_least("V24"):
            contract.setdefault("state_boundary_rules", []).append(
                {
                    "state": "inherited_current_state",
                    "rule": "handoff.inherited_state 是本章开场已经成立的当前状态；不得把同一状态写成再次发生的变化。只有明确的本章动作、撤回、转移、重置或新周期才能改变它。",
                    "inherited_state_source": "chapter_handoff.inherited_state",
                    "current_change_source": "current_chapter_contract.state_changes",
                }
            )
        if _prompt_version_at_least("V25"):
            item_ledger = handoff.get("item_state_ledger") or []
            contract["item_state_rules"] = [
                {
                    "state": "unregistered_physical_artifact",
                    "ledger_entries": item_ledger,
                    "rule": (
                        "除既有场景和 item_state_ledger 已登记条目外，不得新增纸张、记录页、原件、副本、附件、工具、"
                        "持有者或转移过程；账本为空时，实体物品状态保持 unknown。记录证据只能使用界面内记录、口述复述、"
                        "纯观察或已在场设备。"
                    ),
                },
                {
                    "state": "closed_read_only_window",
                    "rule": (
                        "上一章已关闭的读取窗口只能展开或查看仍保留的只读监测列表；不得写成重新点开、重新开启、"
                        "重新授权或设备主动响应。"
                    ),
                },
            ]
            contract["forbidden_deviations"] = _dedupe(
                contract.get("forbidden_deviations", [])
                + [
                    "不得把未登记实体物品或持有者写成当前事实；不得把已关闭窗口写成重新开放。",
                ]
            )
        if _prompt_version_at_least("V28"):
            contract.setdefault("state_boundary_rules", []).append(
                {
                    "state": "read_only_action_ownership",
                    "rule": (
                        "界面读取、展开、确认或接受历史内容只能改变可见信息，不能直接产生开门、授权、控制链执行或实体影响；"
                        "实体变化必须有角色明确的物理动作或直接反馈，机制不明时保持 observation/unknown。"
                    ),
                }
            )
            contract["forbidden_deviations"] = _dedupe(
                contract.get("forbidden_deviations", [])
                + [
                    "不得把界面读取或确认直接写成设备开门、授权、控制链执行或实体状态变化。",
                ]
            )
        if _prompt_version_at_least("V36"):
            item_ledger = handoff.get("item_state_ledger") or []
            contract["recording_action_rules"] = {
                "mode": "ledger_only_physical_artifacts" if item_ledger else "no_new_physical_record_artifact",
                "allowed_default": [
                    "界面内记录",
                    "口述复述",
                    "纯观察",
                    "item_state_ledger 已登记且已在场的设备",
                ],
                "requires_matching_ledger": [
                    "笔记本",
                    "纸张",
                    "纸面",
                    "记录页",
                    "笔",
                    "便签",
                    "原件",
                    "副本",
                    "附件",
                    "文件夹",
                ],
                "rule": (
                    "记录、保存或留存信息的剧情动作不得自动新增具体实体物品；"
                    "只有 item_state_ledger 明确登记对应物品且本章动作允许，才能描写该物品的持有、书写、翻页、拍摄或转移。"
                ),
            }
        if _prompt_version_at_least("V37"):
            contract["interpretation_boundary_rules"] = {
                "observed": [
                    "界面、设备、回执明确显示的原文或角色直接感知的可见变化。",
                ],
                "tentative": [
                    "角色保留‘也许/可能/尚不能判断’的暂时解释，只能作为猜测或待核对线索。",
                ],
                "investigation": [
                    "角色的追问、核对、查询和寻找下一条证据的动作，不等于目标已经存在或事件已经发生。",
                ],
                "forbidden_upgrades": [
                    "残缺片段、显示时间、相邻出现或重复响应不得升级为已发生历史、完整记录、真实地点或因果。",
                    "设备提示、拒答或响应不得单独证明设备意图、要求、控制动作或目标存在。",
                    "角色猜测不得在句末被收束为身份、来源、归属、执行、能力或因果事实。",
                ],
                "rule": "先写观察，再写保留不确定性的猜测或调查；没有直接证据不得把解释写成事实。",
            }
            contract["forbidden_deviations"] = _dedupe(
                contract.get("forbidden_deviations", [])
                + [
                    "不得把可见提示、残缺片段、角色猜测或调查目标升级成已发生历史、设备意图、完整记录或因果事实。",
                ]
            )
        if _prompt_version_at_least("V40"):
            contract["end_state_boundary"] = _build_v40_end_state_boundary(contract)
    return contract


def sanitize_outline_for_contract(
    outline: dict[str, Any] | None,
    handoff: dict[str, Any] | None = None,
    *,
    enforce_authority: bool | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return an outline and contract with unresolved claims kept as clues.

    The original Planner payload is copied so the experiment recorder can still
    preserve the raw model response.  Downstream agents receive the sanitized
    outline and the same contract.
    """
    source = dict(outline) if isinstance(outline, dict) else {}
    raw_unknown_boundary = _as_strings(source.get("unknown_boundary"))
    if _prompt_version_at_least("V16"):
        source = _sanitize_v16_outline_values(source, raw_unknown_boundary, handoff, {})
        # The boundary itself is authoritative input and must remain verbatim;
        # only downstream descriptions are normalized against it.
        source["unknown_boundary"] = raw_unknown_boundary
    contract = build_chapter_contract(
        source,
        handoff,
        enforce_authority=enforce_authority,
    )
    if enforce_authority is None:
        enforce_authority = prompt_version_at_least("V3")
    if enforce_authority and contract.get("uncertain_events"):
        source["key_events"] = list(contract["required_events"])
        source["required_events"] = list(contract["required_events"])
        source["uncertain_events"] = list(contract["uncertain_events"])
        source["forbidden_deviations"] = list(contract["forbidden_deviations"])
        source["unknown_boundary"] = list(contract["unknown_boundary"])
    source["continuity_contract"] = contract
    return source, contract


def contract_prompt(
    contract: dict[str, Any] | None,
    *,
    agent_type: str = "writer",
) -> str:
    import json

    if _prompt_version_at_least("V34"):
        contract = contract or {}
        # V34 assigns each context block one owner. The handoff owns inherited
        # state and ledgers; the contract owns only current-chapter execution.
        compact_contract = {
            "required_events": compact_items(
                contract.get("required_events"), max_items=8, item_chars=420, keep="head"
            ),
            "state_changes": compact_items(
                contract.get("state_changes"), max_items=6, item_chars=420, keep="head"
            ),
            "foreshadowing_actions": compact_items(
                contract.get("foreshadowing_actions"), max_items=6, item_chars=420, keep="head"
            ),
            "end_state": compact_text(contract.get("end_state"), 700),
            "new_stage_delta": compact_items(
                contract.get("new_stage_delta"), max_items=5, item_chars=360, keep="head"
            ),
            "unique_action_ledger": compact_items(
                contract.get("unique_action_ledger"), max_items=6, item_chars=320, keep="head"
            ) if _prompt_version_at_least("V54") else [],
            "primary_action": contract.get("primary_action") if _prompt_version_at_least("V55") else {},
            "character_turn": contract.get("character_turn") if _prompt_version_at_least("V56") else {},
            "end_state_boundary": contract.get("end_state_boundary"),
            "uncertain_events": compact_items(
                contract.get("uncertain_events"), max_items=5, item_chars=360, keep="head"
            ),
            "unknown_boundary": compact_items(
                contract.get("unknown_boundary"), max_items=5, item_chars=360, keep="head"
            ),
            "forbidden_deviations": compact_items(
                contract.get("forbidden_deviations"), max_items=6, item_chars=360, keep="head"
            ),
            "execution_boundaries": [
                "上一章继承状态以交接包为准，本契约只列本章新增动作和可见后果。",
                "unknown/candidate/generated 只能写成观察、疑问或调查线索，不得写成确认事实。",
                "界面读取只改变可见信息；实体变化必须来自角色明确动作或保持未知。",
            ],
        }
        if _prompt_version_at_least("V46"):
            compact_contract["dramatic_turn"] = build_dramatic_turn_projection(contract)
        if _prompt_version_at_least("V53"):
            compact_contract["previous_progress"] = contract.get("previous_progress") or {}
        if _prompt_version_at_least("V36") and contract.get("recording_action_rules"):
            compact_contract["recording_action_rules"] = contract["recording_action_rules"]
        if _prompt_version_at_least("V37") and contract.get("interpretation_boundary_rules"):
            compact_contract["interpretation_boundary_rules"] = contract["interpretation_boundary_rules"]
        return compact_json(compact_contract, 3000, label=f"chapter_contract_{agent_type}")

    if _prompt_version_at_least("V29"):
        contract = contract or {}
        compact_contract = {
            "required_events": compact_items(
                contract.get("required_events"),
                max_items=8,
                item_chars=420,
                keep="head",
            ),
            "continuity_from_previous": compact_items(
                contract.get("continuity_from_previous"),
                max_items=6,
                item_chars=420,
                keep="head",
            ),
            "state_changes": compact_items(
                contract.get("state_changes"),
                max_items=6,
                item_chars=420,
                keep="head",
            ),
            "foreshadowing_actions": compact_items(
                contract.get("foreshadowing_actions"),
                max_items=6,
                item_chars=420,
                keep="head",
            ),
            "end_state": compact_text(contract.get("end_state"), 700),
            "new_stage_delta": compact_items(
                contract.get("new_stage_delta"), max_items=5, item_chars=360, keep="head"
            ),
            "unknown_boundary": compact_items(
                contract.get("unknown_boundary"),
                max_items=5,
                item_chars=360,
                keep="head",
            ),
            "forbidden_deviations": compact_items(
                contract.get("forbidden_deviations"),
                max_items=6,
                item_chars=360,
                keep="head",
            ),
            "execution_boundaries": [
                "unknown/candidate/generated 只能作为观察、疑问或调查线索，不得写成确认事实。",
                "界面读取只改变可见信息；实体变化必须来自角色明确动作或保持未知。",
                "物品/证据账本以交接包为准；账本未登记的实体状态不得补全。",
            ],
            "backend_boundary": (
                "物品/证据账本、角色卡和权威等级以结构化交接包为准；"
                "本契约只规定本章要发生的叙事动作，不要求正文复述后台字段。"
            ),
        }
        if _prompt_version_at_least("V53"):
            compact_contract["previous_progress"] = contract.get("previous_progress") or {}
        return compact_json(compact_contract, 3600, label="chapter_contract")

    if _prompt_version_at_least("V10"):
        contract = contract or {}
        # The handoff is the single owner of the previous-ending evidence
        # ledgers. The chapter contract carries executable obligations only;
        # repeating the ledgers here was the largest V9 prompt multiplier.
        compact_contract = {
            "required_events": compact_items(
                contract.get("required_events"),
                max_items=12,
                item_chars=500,
                keep="head",
            ),
            "continuity_from_previous": compact_items(
                contract.get("continuity_from_previous"),
                max_items=8,
                item_chars=450,
                keep="head",
            ),
            "state_changes": compact_items(
                contract.get("state_changes"),
                max_items=8,
                item_chars=450,
                keep="head",
            ),
            "foreshadowing_actions": compact_items(
                contract.get("foreshadowing_actions"),
                max_items=8,
                item_chars=450,
                keep="head",
            ),
            "end_state": compact_text(contract.get("end_state"), 900),
            "new_stage_delta": compact_items(
                contract.get("new_stage_delta"), max_items=5, item_chars=360, keep="head"
            ),
            "uncertain_events": compact_items(
                contract.get("uncertain_events"),
                max_items=8,
                item_chars=450,
                keep="head",
            ),
            "forbidden_deviations": compact_items(
                contract.get("forbidden_deviations"),
                max_items=12,
                item_chars=450,
                keep="head",
            ),
            "boundary_reference": "物品/证据账本、未知边界和权威来源以同章结构化交接包为唯一来源。",
        }
        if _prompt_version_at_least("V11"):
            compact_contract["state_boundary_rules"] = compact_items(
                contract.get("state_boundary_rules"),
                max_items=5 if _prompt_version_at_least("V28") else 4,
                item_chars=700,
                keep="head",
            )
            compact_contract["claim_boundary_rules"] = compact_items(
                contract.get("claim_boundary_rules"),
                max_items=4,
                item_chars=700,
                keep="head",
            )
        if _prompt_version_at_least("V12"):
            compact_contract["evidence_surface_rules"] = compact_items(
                contract.get("evidence_surface_rules"),
                max_items=3,
                item_chars=700,
                keep="head",
            )
            compact_contract["evidence_surface_claims"] = compact_items(
                contract.get("evidence_surface_claims"),
                max_items=4,
                item_chars=500,
                keep="head",
            )
        if _prompt_version_at_least("V25"):
            compact_contract["item_state_rules"] = compact_items(
                contract.get("item_state_rules"),
                max_items=2,
                item_chars=900,
                keep="head",
            )
        return compact_json(compact_contract, 5000, label="chapter_contract")

    return json.dumps(
        contract or {},
        ensure_ascii=False,
        indent=2,
    )


def prompt_outline_for_agent(
    outline: dict[str, Any] | None,
    *,
    agent_type: str | None = None,
) -> dict[str, Any]:
    """Remove persisted contracts and, for V35 Writer, audit-only fields."""
    source = dict(outline) if isinstance(outline, dict) else {}
    if not _prompt_version_at_least("V10"):
        return source
    source.pop("continuity_contract", None)
    if _prompt_version_at_least("V45") and agent_type in {"editor", "validator", "extractor"}:
        execution_keys = {
            "editor": (
                "chapter_index", "title", "summary", "required_events", "end_state",
                "related_foreshadowing", "characters_involved", "beats", "new_stage_delta",
                "primary_action", "character_turn",
            ),
            "validator": (
                "chapter_index", "title", "required_events", "end_state",
                "forbidden_deviations", "related_foreshadowing", "new_stage_delta",
                "primary_action", "character_turn",
            ),
            "extractor": (
                "chapter_index", "title", "required_events", "end_state",
                "related_foreshadowing", "new_stage_delta", "primary_action", "character_turn",
            ),
        }[agent_type]
        return {key: source[key] for key in execution_keys if key in source}
    if _prompt_version_at_least("V44") and agent_type in {"editor", "validator", "extractor"}:
        execution_keys = (
            "chapter_index",
            "title",
            "summary",
            "key_events",
            "required_events",
            "state_changes",
            "end_state",
            "forbidden_deviations",
            "related_foreshadowing",
            "characters_involved",
            "character_goals",
            "beats",
            "new_stage_delta",
        )
        return {key: source[key] for key in execution_keys if key in source}
    if _prompt_version_at_least("V35") and agent_type == "writer":
        writer_keys = (
            "chapter_index",
            "title",
            "summary",
            "key_events",
            "emotional_arc",
            "narrative_stage",
            "characters_involved",
            "character_goals",
            "beats",
            "new_stage_delta",
            "primary_action",
            "character_turn",
        )
        return {key: source[key] for key in writer_keys if key in source}
    return source


def _prompt_version_at_least(version: str) -> bool:
    return prompt_version_at_least(version)
