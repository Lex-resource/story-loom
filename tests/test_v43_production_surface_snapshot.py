"""V43 生产表面黄金快照。

在把版本分派从生产代码里移出之前建立基线。重构之后，V43 的渲染结果必须与本快照
逐字节一致——这是"生产行为没变"的唯一硬证据。

两条路径都要快照并互相比对：

* **无 ExperimentContext** —— 普通生产运行，版本由 ``settings.NOVEL_CONTINUITY_PROMPT_VERSION`` 决定
* **显式 pin V43 的 ExperimentContext** —— 研究复现 A28 时走的路径

两者必须完全一致，否则 ``research/`` 覆盖层无法复现 A28。

重新生成基线（只应在有意修改生产提示词时执行，并在提交说明里给出理由）::

    V43_SNAPSHOT_UPDATE=1 .venv/Scripts/python.exe -m pytest tests/test_v43_production_surface_snapshot.py
"""
from __future__ import annotations

import asyncio
import dataclasses
import inspect
import json
import os
import re
from pathlib import Path

import pytest

from agents import prompt_hints
from services.chapter_continuity import ChapterHandoff
from services.context_compaction import context_budget_for
from services.continuity_contract import (
    build_chapter_contract,
    build_dramatic_turn_projection,
    contract_prompt,
    prompt_outline_for_agent,
    sanitize_outline_for_contract,
)
from services.experiment_recorder import ExperimentContext, activate, deactivate
from worker_support import generation_validator_policy as vpolicy

FIXTURE = Path(__file__).parent / "fixtures" / "v43_production_surface.json"
UPDATE = os.environ.get("V43_SNAPSHOT_UPDATE") == "1"

AGENT_TYPES = ("planner", "writer", "editor", "validator", "extractor")


# ---------------------------------------------------------------------------
# 固定输入（不含随机值、时间戳或路径，保证快照可复现）
# ---------------------------------------------------------------------------

HANDOFF = ChapterHandoff(
    previous_chapter=2,
    previous_title="潮声",
    exact_ending="林照停在白塔门前，等待设备侧回执。",
    end_scene={"location": "白塔门前", "time": "退潮后"},
    characters_present=["林照", "周岑"],
    inherited_state=[{"memory_key": "access:tower", "current_statement": "门禁授权已到期"}],
    state_changes=["林照取得第九次潮汐记录副本"],
    completed_event_ledger=[{"event": "调阅潮汐登记", "source_chapter": 2}],
    previous_terminal_state={"stage": "等待回执", "position": "白塔门前"},
    open_questions=["第十次潮汐是否会重复该异常"],
    foreshadowing=["白色灯塔的功能尚未确认"],
    next_hook="设备侧回执迟迟未到。",
    item_state_ledger=[
        {
            "memory_key": "item:R2",
            "name": "R2 证物袋",
            "current_state": "二次封存",
            "source_chapter": 2,
            "authority": "accepted",
            "transitions": [{"from": "原封", "to": "二次封存"}],
            "source_ref": "chapter:2:extractor",
        }
    ],
    evidence_state_ledger=[
        {
            "evidence_kind": "attribution",
            "memory_key": "identity:sender",
            "subject": "异常声线",
            "proposition": "发送源字段缺失，现实发送者未知。",
            "status": "accepted",
            "authority": "accepted",
            "source_chapter": 2,
            "source_ref": "chapter:2:extractor",
        }
    ],
    evidence_boundaries=["关联不等于身份确认。"],
    unknown_boundary=["现实发送者未知。"],
)

OUTLINE = {
    "chapter_index": 3,
    "title": "回执",
    "summary": "林照追查设备侧回执的来源。",
    "key_events": ["确认录音是林砚的语音", "进入档案室查找来源"],
    "required_events": ["核对第九次潮汐登记的来源字段"],
    "uncertain_events": ["待核对异常声线的归属"],
    "continuity_from_previous": ["承接白塔门前的等待状态"],
    "state_changes": ["林照取得档案室的临时授权"],
    "foreshadowing_actions": ["核验白色灯塔的实际功能"],
    "forbidden_deviations": ["不得新增证物副本数量"],
    "unknown_boundary": ["不能确认声音属于林砚本人"],
    "beats": ["进入档案室", "比对来源字段"],
    "emotional_arc": "怀疑到决心",
}

VALIDATOR_ISSUES = [
    {"type": "hard_fact_conflict", "detail": "第九次潮汐记录的来源字段与已接受事实冲突。"},
    {"type": "timeline", "detail": "远程倒计时与现场校准窗口无法形成一致关系。"},
    {"type": "item_state", "detail": "R2 证物袋被重复开封。"},
    {"type": "evidence_language", "detail": "把未校准观察写成了确定因果。"},
    {"type": "observation_language", "detail": "界面读取被写成实体状态改变。"},
    {"type": "bounded_hypothesis", "detail": "假设未标注为待核实。"},
    {"type": "contract_alignment", "detail": "章节契约的措辞与正文略有偏差。"},
    {"type": "action_surface", "detail": "本章缺少一个可观察的角色选择。"},
    {"type": "style", "detail": "技术字段连续堆叠，读起来像说明书。"},
]


# ---------------------------------------------------------------------------
# Agent prompt 捕获（桩掉数据库模板与 LLM 调用）
# ---------------------------------------------------------------------------

SYSTEM_TEMPLATE = "<<SYSTEM_TEMPLATE>>"
USER_TEMPLATE = "<<USER_TEMPLATE>>"


def _pipeline_context():
    from agents.pipeline_context import PipelineContext

    return PipelineContext.from_memory(
        "00000000-0000-0000-0000-000000000000",
        3,
        {
            "novel_format": "long_webnovel",
            "genre": "悬疑",
            "style": "冷峻",
            "global_outline": {"volumes": []},
            "chapter_outline": OUTLINE,
            "world_state": "白塔门禁授权已到期。",
            "character_state": "林照持有第九次潮汐记录副本。",
            "foreshadowing": "白色灯塔的功能尚未确认。",
            "plot_threads": "追查设备侧回执来源。",
            "previous_ending": "林照停在白塔门前。",
            "chapter_handoff_context": HANDOFF.to_compact_prompt(),
            "chapter_contract_context": contract_prompt(build_chapter_contract(OUTLINE, HANDOFF.to_dict())),
            "novel_memory_context": "【已接受事实】发送源字段缺失。",
            "character_manifest_context": "林照：调查者。",
            "narrative_index_context": "第 2 章：调阅潮汐登记。",
            "issue_summaries": "",
            "intervention": "",
            "reference_style": "",
            "vector_context": "",
            "draft_content": "林照推开档案室的门。",
            "chapter_content": "林照推开档案室的门。",
            "content": "林照推开档案室的门。",
            "title": "回执",
            "word_count": 3000,
        },
    )


def _capture_agent_prompts(agent, method_name: str, **kwargs) -> dict[str, str]:
    """跑一次 agent 方法，捕获它实际组合出的 system/user prompt。"""
    captured: dict[str, str] = {}

    async def _fake_get_prompt_template(name, *, category):
        captured["prompt_name"] = f"{name} ({category})"
        return SYSTEM_TEMPLATE, USER_TEMPLATE

    async def _fake_call_llm(system_prompt, user_prompt, *a, **kw):
        captured["system_prompt"] = system_prompt
        captured["user_prompt"] = user_prompt
        return "{}"

    async def _fake_call_llm_json(system_prompt, user_prompt, *a, **kw):
        captured["system_prompt"] = system_prompt
        captured["user_prompt"] = user_prompt
        return {}

    agent.get_prompt_template = _fake_get_prompt_template
    agent.call_llm = _fake_call_llm
    agent.call_llm_json = _fake_call_llm_json

    asyncio.run(getattr(agent, method_name)(**kwargs))
    return captured


def _agent_surfaces() -> dict[str, dict[str, str]]:
    from agents.writing.editor import EditorAgent
    from agents.writing.extractor import ExtractorAgent
    from agents.writing.planner import PlannerAgent
    from agents.writing.validator_agent import ValidatorAgent
    from agents.writing.writer import WriterAgent

    context = _pipeline_context()
    return {
        "planner": _capture_agent_prompts(
            PlannerAgent(), "generate_chapter_outline", context=context, total_chapters=100
        ),
        "writer": _capture_agent_prompts(WriterAgent(), "write_chapter", context=context),
        "editor": _capture_agent_prompts(EditorAgent(), "review_chapter", context=context),
        "validator": _capture_agent_prompts(ValidatorAgent(), "validate_content", context=context),
        "extractor": _capture_agent_prompts(ExtractorAgent(), "extract_changes", context=context),
    }


# ---------------------------------------------------------------------------
# 快照构建
# ---------------------------------------------------------------------------

_VERSIONED_HINT = re.compile(r"^v\d+_.*_hint$")


def _hint_surfaces() -> dict[str, dict[str, str]]:
    """全部版本化 hint 函数 × 5 个 agent 角色。

    同时从生产模块与研究覆盖层取函数，使"哪些留在生产、哪些移入 research"的重构
    不改变快照集合——leaf 文本的逐字节保证因此在迁移前后都成立。
    """
    from research.prompt_versions import hints as research_hints

    surfaces: dict[str, dict[str, str]] = {}
    for module in (prompt_hints, research_hints):
        for name in sorted(dir(module)):
            if not _VERSIONED_HINT.match(name) or name in surfaces:
                continue
            func = getattr(module, name)
            if not inspect.isfunction(func):
                continue
            surfaces[name] = {agent: func(agent) for agent in AGENT_TYPES}
    return surfaces


def _contract_surfaces() -> dict[str, object]:
    contract = build_chapter_contract(OUTLINE, HANDOFF.to_dict())
    safe_outline, sanitized_contract = sanitize_outline_for_contract(OUTLINE, HANDOFF.to_dict())
    return {
        "build_chapter_contract": contract,
        "sanitize_outline_for_contract": {
            "outline": safe_outline,
            "contract": sanitized_contract,
        },
        "contract_prompt": {agent: contract_prompt(contract, agent_type=agent) for agent in AGENT_TYPES},
        "prompt_outline_for_agent": {
            agent: prompt_outline_for_agent(OUTLINE, agent_type=agent) for agent in AGENT_TYPES
        },
        "build_dramatic_turn_projection": build_dramatic_turn_projection(contract),
    }


def _validator_policy_surfaces() -> dict[str, object]:
    from research.prompt_versions import validator_policy as research_vpolicy

    # 生产侧只剩 A28/V43 真正使用的两类；V49–V65 的分类器已移入研究覆盖层。
    # 两侧一起快照，使"哪些留在生产"的迁移不改变快照集合。
    classifiers = {
        "is_bounded_hypothesis_issue": vpolicy.is_bounded_hypothesis_issue,
        "is_soft_contract_alignment_issue": vpolicy.is_soft_contract_alignment_issue,
        "is_v54_action_surface_issue": research_vpolicy.is_v54_action_surface_issue,
        "is_v50_minimal_observation_issue": research_vpolicy.is_v50_minimal_observation_issue,
        "is_v65_evidence_boundary_issue": research_vpolicy.is_v65_evidence_boundary_issue,
        "is_v49_observation_language_issue": research_vpolicy.is_v49_observation_language_issue,
    }
    per_issue = {}
    for index, issue in enumerate(VALIDATOR_ISSUES):
        per_issue[f"{index}:{issue['type']}"] = {
            name: bool(fn(issue)) for name, fn in sorted(classifiers.items())
        }

    retry_cases = {
        "passed_no_issues": {"passed": True, "issues": []},
        "failed_hard_fact": {"passed": False, "issues": [VALIDATOR_ISSUES[0]]},
        "failed_timeline": {"passed": False, "issues": [VALIDATOR_ISSUES[1]]},
        "failed_style_only": {"passed": False, "issues": [VALIDATOR_ISSUES[8]]},
        "failed_all_issues": {"passed": False, "issues": VALIDATOR_ISSUES},
        "missing_passed_field": {"issues": [VALIDATOR_ISSUES[0]]},
        "empty_dict": {},
    }
    # hard_issues 才是重试判定读取的字段；issues 保留以覆盖字段缺失的情形。
    hard_cases = {
        name: ({**case, "hard_issues": case["issues"]} if "issues" in case else case)
        for name, case in retry_cases.items()
    }
    return {
        "classifiers": per_issue,
        "requires_content_retry": {
            name: bool(vpolicy.requires_content_retry(case)) for name, case in sorted(hard_cases.items())
        },
        "has_fact_conflict": {
            name: bool(vpolicy.has_fact_conflict(case)) for name, case in sorted(hard_cases.items())
        },
    }


def _build_snapshot() -> dict[str, object]:
    return {
        "hints": _hint_surfaces(),
        "agents": _agent_surfaces(),
        "handoff_compact_prompt": {
            str(budget): HANDOFF.to_compact_prompt(max_chars=budget)
            for budget in (9000, 3000, 2200, 1200)
        },
        "contract": _contract_surfaces(),
        "validator_policy": _validator_policy_surfaces(),
        "context_budget": {
            agent: dataclasses.asdict(context_budget_for(agent)) for agent in AGENT_TYPES
        },
    }


def _snapshot_with_context(tmp_path, *, variant: str, version: str = "V43") -> dict[str, object]:
    token = activate(
        ExperimentContext(
            run_id="v43-production-surface-snapshot",
            prompt_version=version,
            variant=variant,
            project_id="00000000-0000-0000-0000-000000000000",
            chapter_index=3,
            root_dir=tmp_path,
        )
    )
    try:
        return _build_snapshot()
    finally:
        deactivate(token)


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def _diff_paths(a: object, b: object, path: str = "") -> list[str]:
    """收集两份表面之间所有不同的路径（用于锁住已知的生产/A28 偏差集合）。"""
    diffs: list[str] = []
    if type(a) is not type(b):
        return [path or "<root>"]
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                diffs.append(f"{path}.{key}")
            else:
                diffs.extend(_diff_paths(a[key], b[key], f"{path}.{key}"))
    elif isinstance(a, list):
        if len(a) != len(b):
            diffs.append(path)
        else:
            for index, (left, right) in enumerate(zip(a, b)):
                diffs.extend(_diff_paths(left, right, f"{path}[{index}]"))
    elif a != b:
        diffs.append(path)
    return diffs


# 生产默认（无 ExperimentContext）与 A28/V43 实验之间的行为偏差——**应为空**。
#
# 曾经不为空：代码里有两条独立分派轴，版本轴（prompt_version）已正确设为 V43，但
# 变体轴（ExperimentContext.variant 匹配 ariadne-a<N>）在生产下是空串，导致
# Ariadne A>=7 / A28 的分支全部落空。生产因此拿不到 PRODUCTION.md 验证过的
# A28/V43 行为——最严重的一处是 `is_bounded_hypothesis_issue` 恒为 False，
# 使有界假设措辞问题触发 Writer 重写，而 A28 的招牌指标正是零内容重试。
#
# 现在生产已冻结为完整 A28/V43：变体轴判据内联为 A28 语义，`ariadne_series()`
# 在无上下文时返回生产冻结序号 28。这个集合必须保持为空。
KNOWN_PRODUCTION_VS_A28_DIVERGENCE: set[str] = set()


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------


def test_research_layer_yields_at_frozen_point(tmp_path):
    """在生产冻结点上，研究覆盖层必须对每个已注册表面让路。

    这是 pin A28/V43 的研究复现能走生产同一条代码路径的机制保证——覆盖层不会
    悄悄给出一份可能漂移的副本。
    """
    from research.prompt_versions import registered_surfaces, resolve
    from services.version_surface import NO_OVERRIDE

    surfaces = registered_surfaces()
    assert surfaces, "研究覆盖层没有注册任何表面，说明注册没有生效"

    # 无 ExperimentContext（普通生产运行）
    for surface in surfaces:
        assert resolve(surface, "writer") is NO_OVERRIDE, surface

    # 显式 pin 生产冻结点
    token = activate(
        ExperimentContext(
            run_id="frozen-point",
            prompt_version="V43",
            variant="ariadne-a28-v43-bounded-hypothesis-no-polisher",
            project_id="00000000-0000-0000-0000-000000000000",
            chapter_index=3,
            root_dir=tmp_path,
        )
    )
    try:
        for surface in surfaces:
            assert resolve(surface, "writer") is NO_OVERRIDE, surface
    finally:
        deactivate(token)


def test_research_layer_takes_over_beyond_frozen_point(tmp_path):
    """偏离冻结点的研究版本必须真正拿到覆盖，证明这是"分离"而非"删除"。"""
    from research.prompt_versions import resolve
    from services.version_surface import NO_OVERRIDE

    for version in ("V50", "V66"):
        token = activate(
            ExperimentContext(
                run_id=f"{version.lower()}-takeover",
                prompt_version=version,
                variant=f"ariadne-a40-{version.lower()}",
                project_id="00000000-0000-0000-0000-000000000000",
                chapter_index=3,
                root_dir=tmp_path,
            )
        )
        try:
            hints = resolve("generation_hints", "writer")
            assert hints is not NO_OVERRIDE, version
            assert hints, version
        finally:
            deactivate(token)


def test_production_default_matches_a28_v43_exactly(tmp_path):
    """生产默认必须与 A28/V43 逐字节一致。

    生产的 ``NOVEL_CONTINUITY_PROMPT_VERSION`` 早已是 V43，但曾经存在第二条
    **变体轴**：`ExperimentContext.variant` 匹配 `ariadne-a<N>` 才生效的分支在
    生产下（variant 为空）全部落空，导致生产行为 != PRODUCTION.md 验证过的
    A28/V43。最严重的一处会让有界假设措辞触发 Writer 重写，而 A28 的招牌指标
    正是零内容重试。

    生产现已冻结为完整 A28/V43，因此这个偏差集合必须为空。
    """
    default_surface = _build_snapshot()
    a28_surface = _snapshot_with_context(
        tmp_path, variant="ariadne-a28-v43-bounded-hypothesis-no-polisher"
    )

    diffs = set(_diff_paths(default_surface, a28_surface))

    assert diffs == KNOWN_PRODUCTION_VS_A28_DIVERGENCE, (
        "生产默认与 A28/V43 的行为出现偏差。\n"
        f"新增：{sorted(diffs - KNOWN_PRODUCTION_VS_A28_DIVERGENCE)}"
    )


def test_v43_production_surface_matches_golden_snapshot(tmp_path):
    """V43 生产表面与基线逐字节一致。

    同时记录生产默认与 A28/V43 两条路径，使重构后两者都可比对。
    """
    current = {
        "production_default": _build_snapshot(),
        "a28_v43": _snapshot_with_context(
            tmp_path, variant="ariadne-a28-v43-bounded-hypothesis-no-polisher"
        ),
    }
    rendered = _dump(current)

    if UPDATE or not FIXTURE.exists():
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(rendered, encoding="utf-8")
        if not UPDATE:
            pytest.fail(
                f"基线不存在，已写入 {FIXTURE}。请检查内容后重新运行以确认基线。"
            )
        return

    expected = FIXTURE.read_text(encoding="utf-8")
    assert rendered == expected, (
        "V43 生产表面与黄金快照不一致。若这是有意的提示词修改，"
        "用 V43_SNAPSHOT_UPDATE=1 重新生成并在提交说明里给出理由。"
    )
