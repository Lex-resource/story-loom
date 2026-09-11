import asyncio

from agents.pipeline import PlannerNode
from agents.pipeline_context import PipelineContext


class _CapturingPlannerAgent:
    async def generate_chapter_outline(self, *, context, total_chapters, on_chunk):
        self.context = context
        return {
            "chapter_index": context.chapter_index,
            "summary": "captured",
        }


def test_planner_node_preserves_custom_chapter_instruction():
    agent = _CapturingPlannerAgent()
    node = PlannerNode(agent=agent)
    context = PipelineContext.from_memory(
        "project-id",
        4,
        {
            "novel_format": "long_webnovel",
            "intervention": "用户本章要求：保留上一章的录音机线索",
        },
    )

    asyncio.run(node.run(context, {"skeleton": {}, "issue_summaries": ""}))

    assert agent.context.intervention == "用户本章要求：保留上一章的录音机线索"
from agents.writing_schemas import PlannerChapterOutlineResponse
from services.continuity_contract import (
    build_chapter_contract,
    contract_prompt,
    sanitize_outline_for_contract,
)
from services.continuity_sanitizers import sanitize_contract_text
from services.experiment_recorder import ExperimentContext, activate, deactivate


def test_planner_outline_coerces_provider_stringified_contract_fields():
    result = PlannerChapterOutlineResponse.model_validate(
        {
            "chapter_index": 2,
            "title": "潮声",
            "summary": "林照追查记录。",
            "key_events": "发现一份异常记录",
            "emotional_arc": "怀疑到决心",
            "continuity_from_previous": "必须承接上一章的白色灯塔线索",
            "unknown_boundary": "不能推断父亲当时仍然存活",
            "uncertain_events": "待核对父亲是否仍然存活",
            "continuity_contract": "Writer 不得新增副本数量",
            "beats": "进入档案室",
        }
    )

    assert result.key_events == ["发现一份异常记录"]
    assert result.required_events == []
    assert result.continuity_from_previous == ["必须承接上一章的白色灯塔线索"]
    assert result.unknown_boundary == ["不能推断父亲当时仍然存活"]
    assert result.uncertain_events == ["待核对父亲是否仍然存活"]
    assert result.continuity_contract == {"statement": "Writer 不得新增副本数量"}
    assert result.beats == ["进入档案室"]


def test_v3_contract_does_not_promote_unknown_identity_to_required_event():
    outline = {
        "key_events": ["确认录音是林砚的语音", "进入档案室查找来源"],
        "unknown_boundary": ["不能确认声音属于林砚本人"],
    }
    safe_outline, contract = sanitize_outline_for_contract(outline, enforce_authority=True)

    assert "确认录音是林砚的语音" not in contract["required_events"]
    assert "确认录音是林砚的语音" in contract["uncertain_events"]
    assert "进入档案室查找来源" in contract["required_events"]
    assert safe_outline["key_events"] == ["进入档案室查找来源"]
    assert contract["authority_policy"]["clue_only_levels"] == ["candidate", "generated"]


def test_v3_contract_prefers_explicit_required_events_over_descriptive_key_events():
    outline = {
        "key_events": [
            "发现档案显示死者姓名为林越",
            "确认记录由林越本人上传",
        ],
        "required_events": [
            "核验档案时间戳和潮位校验码",
            "复制并保存白色灯塔图像",
        ],
        "unknown_boundary": ["不能确认记录是否由林越本人上传"],
    }

    safe_outline, contract = sanitize_outline_for_contract(outline, enforce_authority=True)

    assert contract["required_events"] == outline["required_events"]
    assert contract["uncertain_events"] == []
    assert safe_outline["key_events"] == outline["key_events"]


def test_v3_boundary_keeps_observation_events_and_blocks_direct_relation_claims():
    outline = {
        "key_events": [
            "观察白色灯塔图像并记录其出现位置",
            "确认录音是林砚的语音",
        ],
        "unknown_boundary": [
            "不能确认声音属于林砚本人，白色灯塔的拍摄地点当前未知",
        ],
    }

    safe_outline, contract = sanitize_outline_for_contract(outline, enforce_authority=True)

    assert contract["required_events"] == ["观察白色灯塔图像并记录其出现位置"]
    assert contract["uncertain_events"] == ["确认录音是林砚的语音"]
    assert safe_outline["key_events"] == contract["required_events"]


def test_v36_contract_makes_empty_ledger_recording_mode_explicit(tmp_path):
    context = ExperimentContext(
        run_id="v36-recording-contract",
        prompt_version="V36",
        variant="writer-recording-commitment",
        project_id="project",
        chapter_index=2,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        _, contract = sanitize_outline_for_contract(
            {"required_events": ["记录设备显示的新反馈"]},
            {"item_state_ledger": []},
        )
    finally:
        deactivate(token)

    rules = contract["recording_action_rules"]
    assert rules["mode"] == "no_new_physical_record_artifact"
    assert "界面内记录" in rules["allowed_default"]
    assert "笔记本" in rules["requires_matching_ledger"]


def test_v37_contract_separates_observation_interpretation_and_investigation(tmp_path):
    context = ExperimentContext(
        run_id="v37-observation-contract",
        prompt_version="V37",
        variant="writer-observation-boundary",
        project_id="project",
        chapter_index=2,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        _, contract = sanitize_outline_for_contract(
            {"required_events": ["查询下一份回执"]},
            {"unknown_boundary": ["残缺回执的历史性质和取回条件未知"]},
        )
    finally:
        deactivate(token)

    rules = contract["interpretation_boundary_rules"]
    assert rules["observed"]
    assert rules["tentative"]
    assert rules["investigation"]
    assert any("已发生历史" in item for item in rules["forbidden_upgrades"])
    assert any("设备意图" in item for item in contract["forbidden_deviations"])


def test_v11_marks_revoked_permissions_as_historical_scope(tmp_path):
    context = ExperimentContext(
        run_id="v11-boundary",
        prompt_version="V11",
        variant="boundary-contract",
        project_id="project",
        chapter_index=5,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        _, contract = sanitize_outline_for_contract(
            {
                "start_state": "访问窗口权限为十分钟只读，但上一章已记录授权撤回。",
                "state_changes": ["完成封存"],
                "foreshadowing_actions": ["保留阶段性结论"],
                "unknown_boundary": ["发送者未知"],
            },
            {
                "state_changes": ["深层索引已锁定，访问权限已关闭"],
                "unknown_boundary": ["实际操作者未知"],
            },
            enforce_authority=True,
        )
    finally:
        deactivate(token)

    rules = contract["state_boundary_rules"]
    assert any(rule["state"] == "authorization" for rule in rules)
    assert any("历史权限范围不得写成当前" in rule["rule"] for rule in rules)


def test_v11_marks_countdown_cycle_and_stage_claim_boundaries(tmp_path):
    context = ExperimentContext(
        run_id="v11-cycle",
        prompt_version="V11",
        variant="boundary-contract",
        project_id="project",
        chapter_index=10,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        _, contract = sanitize_outline_for_contract(
            {
                "end_state": "形成同一异常事件链的阶段性结论，并出现新的九秒帧周期。",
                "foreshadowing_actions": ["形成阶段性结论"],
                "unknown_boundary": ["完整链路和具体因果未知"],
            },
            {
                "exact_ending": "九秒计数器从九跳到八。",
                "unknown_boundary": ["发送者未知"],
            },
            enforce_authority=True,
        )
    finally:
        deactivate(token)

    rules = contract["state_boundary_rules"]
    assert any(rule["state"] == "countdown_cycle" for rule in rules)
    assert any("阶段性结论必须明确" in rule for rule in contract["claim_boundary_rules"])




def test_a7_does_not_require_missing_calibration_evidence(tmp_path):
    context = ExperimentContext(
        run_id="a7-contract",
        prompt_version="V12",
        variant="ariadne-A7-v12-contract-hygiene",
        project_id="project-test",
        chapter_index=2,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        _, contract = sanitize_outline_for_contract(
            {"end_state": "来源字段仍未知，保留只读监测", "required_changes": ["核对来源字段"]},
            {"evidence_boundaries": ["共同校准脉冲未提供"]},
            enforce_authority=True,
        )
    finally:
        deactivate(token)

    assert not any("阶段性证据链必须" in claim for claim in contract["evidence_surface_claims"])


def test_a10_does_not_reintroduce_missing_calibration_evidence(tmp_path):
    context = ExperimentContext(
        run_id="a10-contract",
        prompt_version="V25",
        variant="ariadne-A10-v25-explicit-artifact-boundary-no-polisher",
        project_id="project-test",
        chapter_index=2,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        _, contract = sanitize_outline_for_contract(
            {"end_state": "来源字段仍未知，保留只读监测"},
            {"evidence_boundaries": ["共同校准脉冲未提供"]},
            enforce_authority=True,
        )
    finally:
        deactivate(token)

    assert not any("阶段性证据链必须" in claim for claim in contract["evidence_surface_claims"])


def test_v16_sanitizes_mechanical_evidence_contradictions_without_mutating_input(tmp_path):
    context = ExperimentContext(
        run_id="v16-contract",
        prompt_version="V16",
        variant="contract-hygiene",
        project_id="project-test",
        chapter_index=1,
        root_dir=tmp_path,
    )
    outline = {
        "key_events": [
            "三类潮位记录分别为一百八十厘米、二百七十厘米、九十厘米，最大差值九十厘米。",
            "实体影响为旧维护区出现一次继电器声。",
        ],
        "unknown_boundary": ["继电器吸合声的具体设备、来源和地点未知"],
    }
    original = outline["key_events"][:]
    token = activate(context)
    try:
        safe_outline, contract = sanitize_outline_for_contract(outline, enforce_authority=True)
    finally:
        deactivate(token)

    assert outline["key_events"] == original
    downstream = "\n".join(contract["required_events"])
    assert "最大差值为一百八十厘米" in downstream
    assert "最大差值九十厘米" not in downstream
    assert "无法定位来源的继电器吸合声" in downstream
    assert "旧维护区出现一次继电器声" not in downstream
    assert safe_outline["unknown_boundary"] == outline["unknown_boundary"]


def test_v17_aligns_relative_seconds_with_adjacent_absolute_times_without_mutating_input(tmp_path):
    context = ExperimentContext(
        run_id="v17-contract",
        prompt_version="V17",
        variant="temporal-contract-hygiene",
        project_id="project-test",
        chapter_index=2,
        root_dir=tmp_path,
    )
    outline = {
        "key_events": ["03:24:50开始读取影像，三十五秒后系统刷新为03:25:00。"],
    }
    original = outline["key_events"][:]
    token = activate(context)
    try:
        safe_outline, contract = sanitize_outline_for_contract(outline, enforce_authority=True)
    finally:
        deactivate(token)

    assert outline["key_events"] == original
    downstream = " ".join(contract["required_events"])
    assert "十秒后" in downstream
    assert "三十五秒后" not in downstream
    assert safe_outline["key_events"] == ["03:24:50开始读取影像，十秒后系统刷新为03:25:00。"]


def test_continuity_sanitizer_is_available_as_a_pure_helper():
    result = sanitize_contract_text("08:00:00开始，10秒后到达08:00:20。", [])
    assert "二十秒后" in result


def test_v17_keeps_consistent_relative_seconds_unchanged(tmp_path):
    context = ExperimentContext(
        run_id="v17-consistent",
        prompt_version="V17",
        variant="temporal-contract-hygiene",
        project_id="project-test",
        chapter_index=2,
        root_dir=tmp_path,
    )
    outline = {"key_events": ["03:24:50开始读取影像，十秒后系统刷新为03:25:00。"]}
    token = activate(context)
    try:
        _, contract = sanitize_outline_for_contract(outline, enforce_authority=True)
    finally:
        deactivate(token)
    assert "十秒后" in " ".join(contract["required_events"])


def test_v18_prefers_explicit_order_over_same_event_simultaneous_wording(tmp_path):
    context = ExperimentContext(
        run_id="v18-contract",
        prompt_version="V18",
        variant="event-order-contract-hygiene",
        project_id="project-test",
        chapter_index=1,
        root_dir=tmp_path,
    )
    outline = {
        "key_events": [
            "主潮位仪的数字同时跃升，许岑先确认主潮位仪先跳变才记录闸门动作。"
        ]
    }
    original = outline["key_events"][:]
    token = activate(context)
    try:
        safe_outline, contract = sanitize_outline_for_contract(outline, enforce_authority=True)
    finally:
        deactivate(token)

    downstream = " ".join(contract["required_events"])
    assert "同时跃升" not in downstream
    assert "先跃升" in downstream
    assert outline["key_events"] == original
    assert safe_outline["key_events"] != original


def test_v18_leaves_unambiguous_event_order_unchanged(tmp_path):
    context = ExperimentContext(
        run_id="v18-consistent",
        prompt_version="V18",
        variant="event-order-contract-hygiene",
        project_id="project-test",
        chapter_index=1,
        root_dir=tmp_path,
    )
    outline = {"key_events": ["主潮位仪先跳变，随后闸门动作。"]}
    token = activate(context)
    try:
        _, contract = sanitize_outline_for_contract(outline, enforce_authority=True)
    finally:
        deactivate(token)
    assert "主潮位仪先跳变，随后闸门动作。" in contract["required_events"]


def test_v19_does_not_close_a_read_window_that_handoff_already_closed(tmp_path):
    context = ExperimentContext(
        run_id="v19-window",
        prompt_version="V19",
        variant="cross-chapter-state-hygiene",
        project_id="project-test",
        chapter_index=10,
        root_dir=tmp_path,
    )
    outline = {"key_events": ["林照关掉ACL-LEGACY-07读取窗口，保留只读摘要和关联编号。"]}
    handoff = {"exact_ending": "林照关掉ACL-LEGACY-07读取窗口，保留只读摘要和关联编号。"}
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
    assert "关掉ACL-LEGACY-07读取窗口" not in downstream
    assert "读取窗口仍处于只读封存状态" in downstream
    assert any(rule["state"] == "post_closure_window" for rule in contract["state_boundary_rules"])
    assert safe_outline["key_events"] == contract["required_events"]




def test_v22_keeps_one_precise_countdown_per_cycle(tmp_path):
    context = ExperimentContext(
        run_id="v22-single-countdown",
        prompt_version="V22",
        variant="single-precise-countdown",
        project_id="project-test",
        chapter_index=1,
        root_dir=tmp_path,
    )
    outline = {
        "key_events": [
            "倒计时剩余三十七分钟，随后倒计时从三十三分钟变为三十二分钟。"
        ]
    }
    token = activate(context)
    try:
        safe_outline, contract = sanitize_outline_for_contract(
            outline, enforce_authority=True
        )
    finally:
        deactivate(token)

    downstream = " ".join(contract["required_events"])
    assert "倒计时剩余三十七分钟" in downstream
    assert "倒计时从三十三分钟变为三十二分钟" not in downstream
    assert "倒计时继续递减" in downstream
    assert any(rule["state"] == "single_precise_countdown" for rule in contract["state_boundary_rules"])
    assert safe_outline["key_events"] == contract["required_events"]


def test_v23_replaces_unmapped_relative_minutes(tmp_path):
    context = ExperimentContext(
        run_id="v23-temporal-anchor",
        prompt_version="V23",
        variant="temporal-anchor",
        project_id="project-test",
        chapter_index=1,
        root_dir=tmp_path,
    )
    outline = {
        "key_events": [
            "03:17:44接到电话，四十分钟后抵达，现场终端显示03:22:18。"
        ]
    }
    token = activate(context)
    try:
        _, contract = sanitize_outline_for_contract(outline, enforce_authority=True)
    finally:
        deactivate(token)

    downstream = " ".join(contract["required_events"])
    assert "四十分钟后" not in downstream
    assert "随后抵达" in downstream


def test_v24_keeps_inherited_identifier_from_being_written_as_new_change(tmp_path):
    context = ExperimentContext(
        run_id="v24-inherited-state",
        prompt_version="V24",
        variant="inherited-state-boundary",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    outline = {
        "key_events": [
            "屏幕没有出现执行时间，只有目标字段从之前的短编号变成了：TASK-0002 / TARGET：GATE-02。"
        ]
    }
    handoff = {
        "inherited_state": [
            {
                "memory_key": "plot:task-0002",
                "statement": "TASK-0002目标指向GATE-02，但无执行时间。",
                "scope": "inherited_current",
            }
        ],
        "exact_ending": "上一章结尾已记录 TASK-0002 / TARGET：GATE-02。",
    }
    token = activate(context)
    try:
        safe_outline, contract = sanitize_outline_for_contract(
            outline, handoff, enforce_authority=True
        )
    finally:
        deactivate(token)

    downstream = " ".join(contract["required_events"])
    assert "从之前的短编号变成了" not in downstream
    assert "目标字段仍保持：TASK-0002 / TARGET：GATE-02" in downstream
    assert any(rule["state"] == "inherited_current_state" for rule in contract["state_boundary_rules"])
    assert safe_outline["key_events"] == contract["required_events"]


def test_v24_allows_explicit_new_cycle_to_change_inherited_state(tmp_path):
    context = ExperimentContext(
        run_id="v24-new-cycle",
        prompt_version="V24",
        variant="inherited-state-boundary",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    outline = {
        "key_events": [
            "控制柜重置后，目标字段从之前的短编号变成了：TASK-0002 / TARGET：GATE-02。"
        ]
    }
    handoff = {
        "inherited_state": [{"statement": "TASK-0002 / TARGET：GATE-02"}],
        "exact_ending": "上一章已记录 TASK-0002 / TARGET：GATE-02。",
    }
    token = activate(context)
    try:
        _, contract = sanitize_outline_for_contract(
            outline, handoff, enforce_authority=True
        )
    finally:
        deactivate(token)

    downstream = " ".join(contract["required_events"])
    assert "从之前的短编号变成了" in downstream


def test_v25_explicitly_blocks_unregistered_artifacts_and_reopened_windows(tmp_path):
    context = ExperimentContext(
        run_id="v25-artifact-boundary",
        prompt_version="V25",
        variant="artifact-boundary",
        project_id="project-test",
        chapter_index=2,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        _, contract = sanitize_outline_for_contract(
            {"key_events": ["展开仍保留的只读监测列表"]},
            {
                "item_state_ledger": [],
                "exact_ending": "设备保持关闭，只保留只读监测列表。",
            },
            enforce_authority=True,
        )
    finally:
        deactivate(token)

    rules = {rule["state"] for rule in contract["item_state_rules"]}
    assert rules == {"unregistered_physical_artifact", "closed_read_only_window"}
    assert any("未登记实体物品" in item for item in contract["forbidden_deviations"])
    assert any("重新开放" in item for item in contract["forbidden_deviations"])


def test_v40_contract_projects_terminal_end_state_boundary(tmp_path):
    context = ExperimentContext(
        run_id="v40-terminal-contract",
        prompt_version="V40",
        variant="terminal-state-boundary",
        project_id="project-test",
        chapter_index=2,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        _, contract = sanitize_outline_for_contract(
            {
                "end_state": "林默停在门槛前，等待下一条提示。",
                "state_changes": ["林默完成现场观察并作出等待决定。"],
            },
            enforce_authority=True,
        )
        rendered = contract_prompt(contract, agent_type="validator")
    finally:
        deactivate(token)

    assert contract["end_state_boundary"]["authority"] == "terminal_chapter_state"
    assert contract["end_state_boundary"]["final_state"] == "林默停在门槛前，等待下一条提示。"
    assert "end_state_boundary" in rendered
    assert "正文推进到该状态之后" in rendered
