"""低版本（V10/V12/V19/V29）的契约与交接包渲染断言。

生产冻结在 A28/V43，这些分支已移入 `research/prompt_versions/`。用例本身逐字保留，
只是从 `tests/` 迁到 `tests/research/`——它们断言的是研究版本的语义，不是生产行为。
"""
import json

from services.chapter_continuity import ChapterHandoff
from services.continuity_contract import (
    build_chapter_contract,
    contract_prompt,
    prompt_outline_for_agent,
    sanitize_outline_for_contract,
)
from services.context_compaction import context_budget_for
from services.experiment_recorder import ExperimentContext, activate, deactivate


def test_v10_handoff_preserves_accepted_evidence_under_budget(tmp_path):
    """V10 的交接包渲染保留已接受证据。

    这份断言针对 V10 分支的键名 `evidence_state_ledger`；生产冻结在 V43，
    走 V30 投影（键名为 `evidence_states`），因此必须显式 pin V10。
    """
    token = activate(
        ExperimentContext(
            run_id="v10-handoff-evidence",
            prompt_version="V10",
            variant="context-compaction",
            project_id="project-test",
            chapter_index=3,
            root_dir=tmp_path,
        )
    )
    try:
        handoff = ChapterHandoff(
            previous_chapter=2,
            exact_ending="林照停在白塔门前，等待设备侧回执。",
            evidence_state_ledger=[{
                "evidence_kind": "attribution",
                "memory_key": "identity:sender",
                "proposition": "发送源字段缺失，现实发送者未知。" + ("补充描述" * 200),
                "status": "accepted",
                "authority": "accepted",
                "source_chapter": 2,
                "source_ref": "chapter:2:extractor",
            }],
            evidence_boundaries=["关联不等于身份确认。"],
            unknown_boundary=["现实发送者未知。"],
        )

        rendered = handoff.to_compact_prompt(max_chars=2200)
        parsed = json.loads(rendered)

        assert len(rendered) <= 2200
        assert "evidence_state_ledger" in parsed
        assert "发送源字段缺失" in parsed["evidence_state_ledger"][0]["proposition"]
        assert parsed["unknown_boundary"] == ["现实发送者未知。"]
    finally:
        deactivate(token)


def test_v10_contract_omits_handoff_ledgers_but_keeps_executable_rules(tmp_path):
    context = ExperimentContext(
        run_id="v10-contract",
        prompt_version="V10",
        variant="context-compaction",
        project_id="project",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        result = json.loads(contract_prompt({
            "required_events": ["完成核对"],
            "end_state": "保留未知发送者",
            "evidence_state_ledger": [{"proposition": "不得重复注入"}],
            "item_state_ledger": [{"current_state": "封存"}],
            "unknown_boundary": ["发送者未知"],
        }))
    finally:
        deactivate(token)

    assert result["required_events"] == ["完成核对"]
    assert result["end_state"] == "保留未知发送者"
    assert "evidence_state_ledger" not in result
    assert "item_state_ledger" not in result
    assert "unknown_boundary" not in result
    assert "boundary_reference" in result


def test_v29_contract_keeps_execution_fields_without_repeating_backend_rules(tmp_path):
    context = ExperimentContext(
        run_id="v29-contract",
        prompt_version="V29",
        variant="ariadne-A14-v29-compact-narrative",
        project_id="project",
        chapter_index=2,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        result = json.loads(contract_prompt({
            "required_events": ["角色在门前观察并决定暂不进入"],
            "continuity_from_previous": ["承接上一章的只读回执"],
            "state_changes": ["角色离开控制台"],
            "foreshadowing_actions": ["推进等待对象线索"],
            "end_state": "门仍关闭，角色转向下一步调查",
            "unknown_boundary": ["发送者身份未知"],
            "forbidden_deviations": ["不得把界面确认写成开门"],
            "state_boundary_rules": [{"state": "must_not_render", "rule": "后台规则"}],
            "evidence_surface_rules": [{"surface": "must_not_render"}],
        }))
    finally:
        deactivate(token)

    assert result["required_events"] == ["角色在门前观察并决定暂不进入"]
    assert len(result["execution_boundaries"]) == 3
    assert "backend_boundary" in result
    assert "state_boundary_rules" not in result
    assert "evidence_surface_rules" not in result


def test_v19_makes_countdown_monotonic_against_previous_handoff(tmp_path):
    context = ExperimentContext(
        run_id="v19-countdown",
        prompt_version="V19",
        variant="cross-chapter-state-hygiene",
        project_id="project-test",
        chapter_index=10,
        root_dir=tmp_path,
    )
    outline = {"key_events": ["控制区启动时倒计时只剩三分钟，随后倒计时跳到三分十一秒。"]}
    handoff = {"exact_ending": "上一章结尾倒计时为三分十一秒。"}
    original = outline["key_events"][:]
    token = activate(context)
    try:
        safe_outline, contract = sanitize_outline_for_contract(
            outline, handoff, enforce_authority=True
        )
    finally:
        deactivate(token)

    assert outline["key_events"] == original
    downstream = " ".join(contract["required_events"])
    assert "倒计时跳到两分五十九秒" in downstream
    assert "倒计时跳到三分十一秒" not in downstream
    assert any(rule["state"] == "countdown_monotonic" for rule in contract["state_boundary_rules"])
    assert safe_outline["key_events"] == contract["required_events"]


def test_v12_separates_evidence_surfaces_and_post_closure_state(tmp_path):
    context = ExperimentContext(
        run_id="v12-contract",
        prompt_version="V12",
        variant="evidence-surfaces",
        project_id="project-test",
        chapter_index=10,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        _, contract = sanitize_outline_for_contract(
            {
                "end_state": "关闭执行登记完成后，保留只读监测并出现新的九秒帧，来源字段未知",
                "foreshadowing_actions": ["形成阶段性结论"],
            },
            {
                "evidence_boundaries": ["设备侧执行回执缺失"],
                "unknown_boundary": ["实体影响未知"],
            },
            enforce_authority=True,
        )
    finally:
        deactivate(token)

    rules = contract["evidence_surface_rules"]
    assert any(rule["surface"] == "evidence_source_surfaces" for rule in rules)
    assert any(rule["surface"] == "post_transition_read_only_observation" for rule in rules)
    assert {"read_path_source", "frame_source_field", "device_execution_source", "physical_effect"}.issubset(
        rules[0]
    )
    assert any("共同校准脉冲" in claim for claim in contract["evidence_surface_claims"])
