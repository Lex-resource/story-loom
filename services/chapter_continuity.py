"""Deterministic chapter-to-chapter continuity handoff.

This module deliberately does not call an LLM. It packages canonical chapter
data and accepted layered memory so the next Planner/Writer can continue from
the previous ending without inventing a second summary call.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel import Chapter
from models.novel_memory import NovelMemoryAtom, NovelSceneBlock
from services.context_compaction import compact_json, compact_text
from services.novel_memory_types import ATOM_STATUS_ACCEPTED, STORYLINE_MAIN
from services.chapter_handoff_formatting import ChapterHandoffFormattingMixin
from core.source_refs import chapter_source_ref


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _first_value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def build_completed_event_ledger(
    outline: dict[str, Any] | None,
    atoms: list[Any] | None = None,
    *,
    source_chapter: int | None = None,
    end_scene: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Project bounded, already-completed work for the next chapter.

    This is deliberately deterministic.  The previous chapter is already
    accepted when a handoff is built, so its accepted outline, memory atoms,
    and terminal scene are safer continuity evidence than asking a model to
    summarize the same chapter a second time.
    """
    outline = outline if isinstance(outline, dict) else {}
    events: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(value: Any, source: str) -> None:
        if isinstance(value, dict):
            value = _first_value(
                value,
                "action",
                "event",
                "consequence",
                "state_change",
                "beat",
                "purpose",
            )
        text = compact_text(value, 320).strip()
        if not text:
            return
        key = "".join(text.lower().split())
        if key in seen:
            return
        seen.add(key)
        events.append(
            {
                "event": text,
                "status": "completed",
                "source": source,
                "source_chapter": source_chapter,
            }
        )

    for field_name in (
        "required_events",
        "key_events",
        "state_changes",
        "foreshadowing_actions",
    ):
        for value in _as_list(outline.get(field_name)):
            add(value, f"outline.{field_name}")

    for atom in atoms or []:
        add(getattr(atom, "statement", ""), f"accepted_memory.{getattr(atom, 'atom_type', 'unknown')}")

    terminal = end_scene if isinstance(end_scene, dict) else {}
    for value in _as_list(terminal.get("recent_changes")):
        add(value, "terminal_scene.recent_changes")

    return events[:12]


@dataclass(frozen=True)
class ChapterHandoff(ChapterHandoffFormattingMixin):
    previous_chapter: int
    previous_title: str = ""
    exact_ending: str = ""
    end_scene: dict[str, Any] = field(default_factory=dict)
    characters_present: list[Any] = field(default_factory=list)
    inherited_state: list[dict[str, Any]] = field(default_factory=list)
    state_changes: list[str] = field(default_factory=list)
    completed_event_ledger: list[dict[str, Any]] = field(default_factory=list)
    previous_terminal_state: dict[str, Any] = field(default_factory=dict)
    open_questions: list[Any] = field(default_factory=list)
    foreshadowing: list[str] = field(default_factory=list)
    next_hook: Any = None
    item_state_ledger: list[dict[str, Any]] = field(default_factory=list)
    evidence_state_ledger: list[dict[str, Any]] = field(default_factory=list)
    evidence_boundaries: list[str] = field(default_factory=list)
    unknown_boundary: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)

_ALL_BRIEF_BOILERPLATE: dict[str, bool] = {
    "recording_boundary": True,
    "interpretation_boundary": True,
    "end_state_boundary": True,
    "do_not_turn_into_a_report": True,
}


def _execution_brief_boilerplate(novel_format: str | None) -> dict[str, bool]:
    """哪些长篇兜底块出现在简报里。长篇（及未知格式）全部出现。"""
    from services.workflow_surface import NO_WORKFLOW_OVERRIDE, workflow_override

    override = workflow_override("execution_brief_boilerplate", novel_format)
    if override is not NO_WORKFLOW_OVERRIDE:
        return {**_ALL_BRIEF_BOILERPLATE, **override}
    return _ALL_BRIEF_BOILERPLATE


def _execution_brief_extras(
    novel_format: str | None,
    contract_data: dict[str, Any],
    outline_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """该工作流要补进 ``chapter_execution`` 的额外字段。长篇不补（保持冻结投影）。

    短篇要的 ``emotional_arc``/``beats``/``character_goals`` 只在**大纲**上，
    ``build_chapter_contract`` 不会把它们带进契约，所以这里要同时看两边。
    """
    from services.workflow_surface import NO_WORKFLOW_OVERRIDE, workflow_override

    override = workflow_override(
        "execution_brief_extras", novel_format, contract_data, outline_data
    )
    if override is not NO_WORKFLOW_OVERRIDE:
        return override
    return {}


def writer_execution_brief(
    handoff: ChapterHandoff | dict[str, Any] | None,
    contract: dict[str, Any] | None,
    *,
    max_chars: int = 4200,
    novel_format: str | None = None,
    outline: dict[str, Any] | None = None,
) -> str:
    """Project continuity inputs into one narrative-facing Writer brief.

    The full handoff and contract remain canonical and available to review
    agents. This projection keeps only the opening state, executable chapter
    actions, closing target, and explicit unknown boundary so the Writer does
    not have to reconcile several audit-shaped context blocks.

    ``novel_format`` selects the workflow surface. Long-form keeps the frozen
    A28/V43 projection verbatim. Short-form drops the four hardcoded long-form
    fallback blocks: its planner emits no ``end_state``/``state_changes``/
    ``new_stage_delta``, so those blocks always rendered as boilerplate defaults
    and crowded out the section's own content (measured at 70% of the brief).
    """
    handoff_data = (
        handoff.to_dict()
        if isinstance(handoff, ChapterHandoff)
        else _as_dict(handoff)
    )
    contract_data = _as_dict(contract)

    def text_list(value: Any, *, max_items: int, item_chars: int) -> list[str]:
        values = _as_list(value)
        result: list[str] = []
        for item in values:
            text = (
                compact_text(item, item_chars)
                if isinstance(item, str)
                else compact_text(json.dumps(item, ensure_ascii=False, default=str), item_chars)
            )
            if text and text not in result:
                result.append(text)
            if len(result) >= max_items:
                break
        return result

    def state_list(value: Any) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for item in _as_list(value):
            if isinstance(item, dict):
                projected = {
                    key: compact_text(item.get(key), 300)
                    for key in (
                        "memory_key",
                        "statement",
                        "current_statement",
                        "state",
                        "current_state",
                    )
                    if item.get(key) not in (None, "", [], {})
                }
                if projected:
                    result.append(projected)
            elif item not in (None, ""):
                result.append({"statement": compact_text(item, 300)})
            if len(result) >= 10:
                break
        return result

    scene = _as_dict(handoff_data.get("end_scene"))
    scene_projection = {
        key: scene[key]
        for key in ("scope_type", "scope_key", "current_state", "recent_changes")
        if scene.get(key) not in (None, "", [], {})
    }
    unknown = text_list(
        list(_as_list(handoff_data.get("unknown_boundary")))
        + list(_as_list(contract_data.get("unknown_boundary")))
        + list(_as_list(contract_data.get("uncertain_events"))),
        max_items=8,
        item_chars=320,
    )
    payload = {
        "opening": {
            "previous_ending": compact_text(
                handoff_data.get("exact_ending"), 1200, tail_chars=780
            ),
            "scene": scene_projection,
            "characters_present": text_list(
                handoff_data.get("characters_present"), max_items=8, item_chars=180
            ),
            "inherited_state": state_list(handoff_data.get("inherited_state")),
            "completed_event_ledger": text_list(
                handoff_data.get("completed_event_ledger"), max_items=8, item_chars=320
            ),
            "previous_terminal_state": handoff_data.get("previous_terminal_state") or {},
        },
        "chapter_execution": {
            "required_actions": text_list(
                contract_data.get("required_events") or contract_data.get("key_events"),
                max_items=8,
                item_chars=320,
            ),
            "state_changes": text_list(
                contract_data.get("state_changes"), max_items=6, item_chars=320
            ),
            "foreshadowing_actions": text_list(
                contract_data.get("foreshadowing_actions"), max_items=5, item_chars=320
            ),
            "new_stage_delta": text_list(
                contract_data.get("new_stage_delta"), max_items=5, item_chars=320
            ),
            "closing_state": compact_text(contract_data.get("end_state"), 700),
        },
        "open_questions": text_list(
            handoff_data.get("open_questions"), max_items=5, item_chars=280
        ),
        "next_hook": compact_text(handoff_data.get("next_hook"), 420),
        "unknown_boundary": unknown,
        "do_not_turn_into_a_report": [
            "简报是幕后执行参考，正文只呈现场景、人物动作、选择和可见后果。",
            "不要逐项复述简报字段、来源、权限、证据或审计术语。",
            "candidate、generated、unknown 只能写成观察、疑问或调查线索。",
        ],
    }
    boilerplate = _execution_brief_boilerplate(novel_format)
    if not boilerplate["do_not_turn_into_a_report"]:
        payload.pop("do_not_turn_into_a_report", None)
    if boilerplate["recording_boundary"]:
        recording_rules = contract_data.get("recording_action_rules")
        if not recording_rules:
            item_ledger = _as_list(handoff_data.get("item_state_ledger"))
            recording_rules = {
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
                "rule": "记录、保存或留存信息不得自动新增具体实体物品。",
            }
        payload["chapter_execution"]["recording_boundary"] = recording_rules
    if boilerplate["interpretation_boundary"]:
        interpretation_rules = contract_data.get("interpretation_boundary_rules")
        if not interpretation_rules:
            interpretation_rules = {
                "observed": ["界面、设备、回执明确显示的原文或角色直接感知的可见变化。"],
                "tentative": ["角色保留‘也许/可能/尚不能判断’的暂时解释，只能作为猜测或待核对线索。"],
                "investigation": ["角色的追问、核对、查询和寻找下一条证据的动作，不等于目标已经存在或事件已经发生。"],
                "forbidden_upgrades": [
                    "残缺片段、显示时间、相邻出现或重复响应不得升级为已发生历史、完整记录、真实地点或因果。",
                    "设备提示、拒答或响应不得单独证明设备意图、要求、控制动作或目标存在。",
                    "角色猜测不得在句末被收束为身份、来源、归属、执行、能力或因果事实。",
                ],
                "rule": "先写观察，再写保留不确定性的猜测或调查；没有直接证据不得把解释写成事实。",
            }
        payload["interpretation_boundary"] = interpretation_rules
    if boilerplate["end_state_boundary"]:
        end_state_boundary = contract_data.get("end_state_boundary")
        if not end_state_boundary:
            end_state_boundary = {
                "authority": "terminal_chapter_state",
                "final_state": compact_text(contract_data.get("end_state"), 700),
                "rule": "end_state 表示本章最后已经成立的可观察状态，正文不得越过该终态。",
                "resolution": "轻微措辞差异由 Editor 局部统一；真实硬事实或核心事件冲突才阻断。",
            }
        payload["chapter_execution"]["end_state_boundary"] = end_state_boundary
    payload["chapter_execution"].update(
        _execution_brief_extras(novel_format, contract_data, outline)
    )
    from services.version_surface import NO_OVERRIDE, research_override

    dramatic_turn = research_override("dramatic_turn_projection", contract_data)
    if dramatic_turn is not NO_OVERRIDE:
        payload["chapter_execution"]["dramatic_turn"] = dramatic_turn
    return compact_json(
        payload,
        max_chars,
        label="writer_execution_brief_v40",
    )


def build_item_state_ledger(atoms: list[Any]) -> list[dict[str, Any]]:
    """Build latest accepted item states and their chapter transitions."""
    grouped: dict[str, list[Any]] = {}
    for atom in atoms:
        if getattr(atom, "status", None) != ATOM_STATUS_ACCEPTED:
            continue
        data = _as_dict(getattr(atom, "data", {}))
        patch_data = _as_dict(data.get("data"))
        rule_type = patch_data.get("rule_type") or data.get("rule_type")
        memory_key = str(getattr(atom, "memory_key", "") or "")
        statement = str(getattr(atom, "statement", "") or "")
        is_item = (
            getattr(atom, "atom_type", None) == "world_rule"
            and (rule_type == "item" or "物品" in memory_key or "证物" in statement or "封存" in statement)
        )
        if is_item:
            grouped.setdefault(memory_key, []).append(atom)

    ledger = []
    for memory_key, versions in grouped.items():
        versions.sort(key=lambda item: (getattr(item, "source_chapter", 0) or 0, getattr(item, "version", 0) or 0))
        latest = versions[-1]
        latest_data = _as_dict(getattr(latest, "data", {}))
        latest_patch_data = _as_dict(latest_data.get("data"))
        transitions = []
        for item in versions:
            item_data = _as_dict(getattr(item, "data", {}))
            item_patch_data = _as_dict(item_data.get("data"))
            transitions.append({
                "chapter": getattr(item, "source_chapter", None),
                "version": getattr(item, "version", None),
                "operation": item_data.get("operation", "") or "",
                "statement": getattr(item, "statement", "") or "",
                "source_ref": getattr(item, "source_ref", "") or "",
                "state": item_patch_data.get("state") or item_patch_data.get("status") or "",
            })
        ledger.append({
            "memory_key": memory_key,
            "name": memory_key.split(":", 1)[-1],
            "current_statement": getattr(latest, "statement", "") or "",
            "current_state": latest_patch_data.get("state") or latest_patch_data.get("status") or "",
            "source_chapter": getattr(latest, "source_chapter", None),
            "source_ref": getattr(latest, "source_ref", "") or "",
            "authority": getattr(latest, "authority", "") or "accepted",
            "transitions": transitions,
        })
    return sorted(ledger, key=lambda item: (item.get("source_chapter") or 0, item["memory_key"]))


def build_inherited_state_ledger(atoms: list[Any]) -> list[dict[str, Any]]:
    """Build the previous chapter's accepted state as a current-state ledger.

    ``state_changes`` is useful as narrative history, but it does not tell the
    next Planner whether a statement is already true at chapter start.  This
    ledger gives downstream agents an explicit inherited/current scope without
    making another model call.
    """
    ledger: dict[str, dict[str, Any]] = {}
    for atom in atoms:
        if getattr(atom, "status", None) != ATOM_STATUS_ACCEPTED:
            continue
        data = _as_dict(getattr(atom, "data", {}))
        patch_data = _as_dict(data.get("data"))
        memory_key = str(getattr(atom, "memory_key", "") or "")
        if not memory_key:
            continue
        candidate = {
            "memory_key": memory_key,
            "statement": str(getattr(atom, "statement", "") or ""),
            "state": patch_data.get("state") or patch_data.get("status") or "",
            "scope": "inherited_current",
            "authority": getattr(atom, "authority", "") or "accepted",
            "source_chapter": getattr(atom, "source_chapter", None),
            "source_ref": getattr(atom, "source_ref", "") or "",
            "rule": "本章开场已经成立；只有明确的本章动作或新周期才能改变它。",
        }
        version = (
            getattr(atom, "source_chapter", 0) or 0,
            getattr(atom, "version", 0) or 0,
        )
        previous = ledger.get(memory_key)
        if previous is None or version >= previous["_version"]:
            candidate["_version"] = version
            ledger[memory_key] = candidate

    result = []
    for item in ledger.values():
        item.pop("_version", None)
        result.append(item)
    return sorted(result, key=lambda item: (item.get("source_chapter") or 0, item["memory_key"]))


def _evidence_kind(atom: Any, data: dict[str, Any], statement: str) -> str | None:
    """Classify accepted propositions that are commonly over-claimed by LLMs."""
    rule_type = str(data.get("rule_type") or "").lower()
    key = str(getattr(atom, "memory_key", "") or "").lower()
    text = f"{key} {statement}".lower()
    if rule_type == "item" or any(term in text for term in ("物品", "证物", "封存", "钥匙", "接口片")):
        return "item"
    if rule_type in {"capability", "ability", "function"} or any(
        term in text for term in ("能力", "权限", "中继", "功能", "可用", "运行")
    ):
        return "capability"
    if any(term in text for term in ("署名", "身份", "自称", "本人", "归属", "执行者", "来源", "留下")):
        return "attribution"
    return None


def build_evidence_state_ledger(atoms: list[Any]) -> list[dict[str, Any]]:
    """Build a compact ledger for propositions prone to evidence escalation."""
    latest: dict[str, Any] = {}
    for atom in atoms:
        if getattr(atom, "status", None) != ATOM_STATUS_ACCEPTED:
            continue
        data = _as_dict(getattr(atom, "data", {}))
        patch_data = _as_dict(data.get("data"))
        statement = str(getattr(atom, "statement", "") or "")
        kind = _evidence_kind(atom, {**data, **patch_data}, statement)
        if kind is None:
            continue
        key = str(getattr(atom, "memory_key", "") or "")
        current = latest.get(key)
        version = (getattr(atom, "source_chapter", 0) or 0, getattr(atom, "version", 0) or 0)
        if current is None or version >= current[0]:
            latest[key] = (version, {
                "evidence_kind": kind,
                "memory_key": key,
                "subject": key.split(":", 1)[-1],
                "proposition": statement,
                "status": getattr(atom, "status", "accepted") or "accepted",
                "authority": getattr(atom, "authority", "accepted") or "accepted",
                "source_chapter": getattr(atom, "source_chapter", None),
                "source_ref": getattr(atom, "source_ref", "") or "",
                "allowed_claim": "只能复述当前命题或描写核对/观察，不得升级为身份、归属、执行、能力或因果确认。",
            })
    return sorted((value for _, value in latest.values()), key=lambda item: (item.get("source_chapter") or 0, item["memory_key"]))


def _assemble_chapter_handoff(
    *,
    previous,
    atoms: list[Any],
    evidence_atoms: list[Any],
    scenes: list[Any],
    outline: dict[str, Any],
    previous_index: int,
    ending: str,
) -> ChapterHandoff:
    """由上一章行 + 记忆/场景行装配交接包(纯函数,DB 查询留在调用方)。"""
    end_scene = {}
    open_questions: list[Any] = []
    scene_sources: list[dict[str, Any]] = []
    for scene in scenes:
        if not end_scene:
            end_scene = {
                "scope_type": scene.scope_type,
                "scope_key": scene.scope_key,
                "current_state": scene.current_state or {},
                "recent_changes": scene.recent_changes or [],
            }
        open_questions.extend(scene.open_questions or [])
        scene_sources.append({
            "type": "scene_block",
            "source_ref": scene.source_ref,
            "chapter": scene.source_chapter,
            "scope": f"{scene.scope_type}/{scene.scope_key}",
        })

    state_changes: list[str] = []
    foreshadowing: list[str] = []
    atom_sources: list[dict[str, Any]] = []
    for atom in atoms:
        if atom.atom_type == "foreshadowing":
            foreshadowing.append(atom.statement)
        else:
            state_changes.append(atom.statement)
        atom_sources.append({
            "type": "atom",
            "source_ref": atom.source_ref,
            "chapter": atom.source_chapter,
            "memory_key": atom.memory_key,
            "authority": atom.authority,
        })

    characters_present = _first_value(
        outline,
        "characters_present",
        "characters_involved",
        "involved_characters",
        "本章角色",
    ) or []
    next_hook = _first_value(
        outline,
        "end_state",
        "next_hook",
        "ending_hook",
        "chapter_hook",
        "结尾钩子",
    )
    open_questions = list(dict.fromkeys(map(str, open_questions)))
    if not open_questions:
        open_questions = [
            item for item in _as_list(_first_value(outline, "open_questions", "unresolved_questions", "开放问题"))
            if item not in (None, "")
        ]

    if not end_scene:
        end_scene = _as_dict(_first_value(outline, "end_scene", "scene_state", "场景状态"))

    previous_terminal_state = {
        key: value
        for key, value in {
            "narrative_stage": _first_value(outline, "narrative_stage", "stage", "剧情阶段"),
            "end_state": _first_value(outline, "end_state", "terminal_state", "结尾状态"),
            "next_hook": next_hook,
            "scene": {
                key: end_scene.get(key)
                for key in ("scope_type", "scope_key", "current_state")
                if end_scene.get(key) not in (None, "", [], {})
            },
        }.items()
        if value not in (None, "", [], {})
    }
    completed_event_ledger = build_completed_event_ledger(
        outline,
        atoms,
        source_chapter=previous_index,
        end_scene=end_scene,
    )

    unknown_boundary = [
        "除交接包、角色卡、已接受记忆和本章大纲明确给出的内容外，不得推断未来事实。",
    ]
    evidence_boundaries = [
        "证据的关联、相似、指向或同源迹象，不等于人物归属、亲自执行、已确认身份或已确认因果。",
        "物品账本中的当前状态和历史转移优先于正文中的模糊回忆；不得重复开封、转移或恢复已完成的转移。",
        "若账本没有记录某个物品的状态，只能描写观察、保管、核对或调查，不得补写持有者和操作结果。",
        "能力、权限、中继和运行状态只代表当前证据命题；不得从一次响应推断永久能力、执行者或因果来源。",
        "署名、来源、相似身份和时间相邻只代表证据关联；不得写成本人留下、本人执行或身份已核验。",
    ]
    if not end_scene:
        unknown_boundary.append("上一章结尾的地点、时间和场景状态未被结构化记录。")
    if not characters_present:
        unknown_boundary.append("上一章结尾在场角色未被结构化记录。")
    if not next_hook:
        unknown_boundary.append("上一章没有明确记录下一章钩子，只能依据结尾原文自然承接。")

    return ChapterHandoff(
        previous_chapter=previous_index,
        previous_title=previous.title or "",
        exact_ending=ending,
        end_scene=end_scene,
        characters_present=_as_list(characters_present),
        inherited_state=build_inherited_state_ledger(atoms),
        state_changes=state_changes,
        completed_event_ledger=completed_event_ledger,
        previous_terminal_state=previous_terminal_state,
        open_questions=open_questions,
        foreshadowing=foreshadowing,
        next_hook=next_hook,
        item_state_ledger=build_item_state_ledger(evidence_atoms),
        evidence_state_ledger=build_evidence_state_ledger(evidence_atoms),
        evidence_boundaries=evidence_boundaries,
        unknown_boundary=unknown_boundary,
        sources=atom_sources + scene_sources + [{
            "type": "chapter",
            "source_ref": chapter_source_ref(previous_index),
            "chapter": previous_index,
        }],
    )


async def build_chapter_handoff(
    db: AsyncSession,
    project_id,
    chapter_index: int,
    *,
    previous_ending: str = "",
) -> ChapterHandoff:
    previous_index = chapter_index - 1
    if previous_index < 1:
        return ChapterHandoff(
            previous_chapter=0,
            exact_ending="",
            unknown_boundary=["这是第一章，没有可承接的上一章事实。"],
        )

    previous = await db.scalar(
        select(Chapter).where(
            Chapter.novel_id == project_id,
            Chapter.chapter_index == previous_index,
        )
    )
    if previous is None:
        return ChapterHandoff(
            previous_chapter=previous_index,
            exact_ending=previous_ending or "",
            unknown_boundary=["上一章记录不存在，只能使用当前可见的结尾片段。"],
        )

    outline = _as_dict(previous.outline)
    content = previous.content or previous.edited_content or previous.draft_content or ""
    ending = previous_ending or content[-1800:]

    atoms = list((await db.scalars(
        select(NovelMemoryAtom).where(
            NovelMemoryAtom.project_id == project_id,
            NovelMemoryAtom.branch_id.is_(None),
            NovelMemoryAtom.storyline_id == STORYLINE_MAIN,
            NovelMemoryAtom.status == ATOM_STATUS_ACCEPTED,
            NovelMemoryAtom.source_chapter == previous_index,
        ).order_by(NovelMemoryAtom.version.desc()).limit(30)
    )).all())
    evidence_atoms = list((await db.scalars(
        select(NovelMemoryAtom).where(
            NovelMemoryAtom.project_id == project_id,
            NovelMemoryAtom.branch_id.is_(None),
            NovelMemoryAtom.storyline_id == STORYLINE_MAIN,
            NovelMemoryAtom.status == ATOM_STATUS_ACCEPTED,
            NovelMemoryAtom.atom_type.in_(("world_rule", "character_state", "plot_thread")),
        ).order_by(NovelMemoryAtom.source_chapter.asc(), NovelMemoryAtom.version.asc()).limit(120)
    )).all())
    scenes = list((await db.scalars(
        select(NovelSceneBlock).where(
            NovelSceneBlock.project_id == project_id,
            NovelSceneBlock.branch_id.is_(None),
            NovelSceneBlock.storyline_id == STORYLINE_MAIN,
            NovelSceneBlock.source_chapter == previous_index,
        ).order_by(NovelSceneBlock.version.desc()).limit(8)
    )).all())

    return _assemble_chapter_handoff(
        previous=previous,
        atoms=atoms,
        evidence_atoms=evidence_atoms,
        scenes=scenes,
        outline=outline,
        previous_index=previous_index,
        ending=ending,
    )
