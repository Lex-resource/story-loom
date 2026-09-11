from agents.prompt_utils import safe_format
from research.prompt_versions.hints import (
    v7_continuity_state_hint_gated,
    v32_prompt_surface_hint_gated,
    v33_memory_update_protocol_hint_gated,
    v34_context_ownership_hint_gated,
    v35_writer_narrative_hint_gated,
    v36_artifact_commitment_hint_gated,
    v37_observation_interpretation_hint_gated,
    v38_scene_motion_hint_gated,
    v39_single_evidence_delta_hint_gated,
    v40_contract_state_hint_gated,
    v41_narrative_escalation_hint_gated,
    v42_authority_locked_progression_hint_gated,
    v43_bounded_hypothesis_progression_hint_gated,
)
from agents.prompt_hints import (
    previous_ending_for_prompt,
    v32_prompt_surface_hint,
    v33_memory_update_protocol_hint,
    v34_context_ownership_hint,
    v35_writer_narrative_hint,
    v36_artifact_commitment_hint,
    v37_observation_interpretation_hint,
    v38_scene_motion_hint,
    v39_single_evidence_delta_hint,
    v40_contract_state_hint,
    v41_narrative_escalation_hint,
    v42_authority_locked_progression_hint,
)
from research.prompt_versions.hints import (
    v10_context_compaction_hint,
    v12_evidence_surface_hint,
    v13_narrative_density_hint,
    v14_continuity_language_hint,
    v15_compact_evidence_and_character_action_hint,
    v27_narrative_first_hint,
    v28_action_ownership_hint,
    v29_compact_narrative_hint,
    v31_evidence_ordered_continuity_hint,
    v6_continuity_quality_hint,
    v9_temporal_evidence_hint,
)
from services.experiment_recorder import ExperimentContext, activate, deactivate


def test_safe_format_preserves_literal_json_objects():
    template = '输出合法 JSON：{"updates":[{"character_name":"角色名"}]}\n第{chapter_index}章'

    result = safe_format(template, chapter_index=4)

    assert '{"updates":[{"character_name":"角色名"}]}' in result
    assert "第4章" in result


def test_safe_format_still_empties_missing_named_placeholders():
    assert safe_format("before {missing} after") == "before  after"


def test_v6_continuity_quality_hint_is_role_specific(tmp_path):
    context = ExperimentContext(
        run_id="v6-hints",
        prompt_version="V6",
        variant="boundary-language",
        project_id="project-test",
        chapter_index=1,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = v6_continuity_quality_hint("writer")
        validator = v6_continuity_quality_hint("validator")
        assert "证据语言闸门" in writer
        assert "每段最多集中呈现一组技术字段" in writer
        assert "无限定确认句" in validator
        assert "warning" in validator
    finally:
        deactivate(token)


def test_v6_continuity_quality_hint_is_empty_for_v5(tmp_path):
    context = ExperimentContext(
        run_id="v5-hints",
        prompt_version="V5",
        variant="boundary-language",
        project_id="project-test",
        chapter_index=1,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        assert v6_continuity_quality_hint("writer") == ""
    finally:
        deactivate(token)


def test_v9_temporal_hint_requires_calibrated_clock_for_ordering(tmp_path):
    context = ExperimentContext(
        run_id="v9-hints",
        prompt_version="V9",
        variant="temporal-boundary",
        project_id="project-test",
        chapter_index=2,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = v9_temporal_evidence_hint("writer")
        validator = v9_temporal_evidence_hint("validator")
        assert "未校准" in writer
        assert "之前/之后" in writer
        assert "必须引用正文和时间源冲突并阻断" in validator
    finally:
        deactivate(token)


def test_v10_context_hint_uses_handoff_as_single_ending_source(tmp_path):
    context = ExperimentContext(
        run_id="v10-hints",
        prompt_version="V10",
        variant="context-compaction",
        project_id="project-test",
        chapter_index=2,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        hint = v10_context_compaction_hint("writer")
        ending = previous_ending_for_prompt("上一章原文", "交接包")
    finally:
        deactivate(token)

    assert "单一来源" in hint
    assert ending == ""


def test_v12_evidence_surface_hint_is_role_specific(tmp_path):
    context = ExperimentContext(
        run_id="v12-hints",
        prompt_version="V12",
        variant="evidence-surfaces",
        project_id="project-test",
        chapter_index=10,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        hint = v12_evidence_surface_hint("writer")
    finally:
        deactivate(token)

    assert "帧内来源字段" in hint
    assert "控制链未重新开放" in hint
    assert "共同校准脉冲" in hint


def test_a7_evidence_surface_hint_does_not_invent_calibration_claim(tmp_path):
    context = ExperimentContext(
        run_id="a7-hints",
        prompt_version="V12",
        variant="ariadne-A7-v12-contract-hygiene",
        project_id="project-test",
        chapter_index=2,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        hint = v12_evidence_surface_hint("writer")
    finally:
        deactivate(token)

    assert "共同校准脉冲" not in hint


def test_a10_evidence_surface_hint_does_not_invent_calibration_claim(tmp_path):
    context = ExperimentContext(
        run_id="a10-hints",
        prompt_version="V25",
        variant="ariadne-A10-v25-explicit-artifact-boundary-no-polisher",
        project_id="project-test",
        chapter_index=2,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        hint = v12_evidence_surface_hint("writer")
    finally:
        deactivate(token)

    assert "共同校准脉冲" not in hint


def test_v27_narrative_first_hint_removes_report_pressure(tmp_path):
    context = ExperimentContext(
        run_id="v27-hints",
        prompt_version="V27",
        variant="ariadne-A12-v27-narrative-first",
        project_id="project-test",
        chapter_index=2,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        planner = v27_narrative_first_hint("planner")
        writer = v27_narrative_first_hint("writer")
        validator = v27_narrative_first_hint("validator")
    finally:
        deactivate(token)

    assert "幕后约束" in planner
    assert "不是要求正文逐项复述的报告模板" in writer
    assert "缺少证据清单不等于失败" in validator


def test_v28_action_ownership_hint_separates_ui_and_physical_actions(tmp_path):
    context = ExperimentContext(
        run_id="v28-hints",
        prompt_version="V28",
        variant="ariadne-A13-v28-action-ownership",
        project_id="project-test",
        chapter_index=2,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = v28_action_ownership_hint("writer")
        validator = v28_action_ownership_hint("validator")
    finally:
        deactivate(token)

    assert "界面动作与实体动作" in writer
    assert "硬动作归属冲突" in validator


def test_v29_compact_narrative_hint_replaces_prompt_accumulation(tmp_path):
    context = ExperimentContext(
        run_id="v29-hints",
        prompt_version="V29",
        variant="ariadne-A14-v29-compact-narrative",
        project_id="project-test",
        chapter_index=2,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = v29_compact_narrative_hint("writer")
        planner = v29_compact_narrative_hint("planner")
    finally:
        deactivate(token)

    assert "幕后执行简报" in writer
    assert "角色目标" in planner
    assert "账本" in writer


def test_v31_evidence_ordered_hint_separates_observation_and_claims(tmp_path):
    context = ExperimentContext(
        run_id="v31-hints",
        prompt_version="V31",
        variant="ariadne-A16-v31-evidence-ordered-continuity",
        project_id="project-test",
        chapter_index=2,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        planner = v31_evidence_ordered_continuity_hint("planner")
        writer = v31_evidence_ordered_continuity_hint("writer")
        editor = v31_evidence_ordered_continuity_hint("editor")
        validator = v31_evidence_ordered_continuity_hint("validator")
    finally:
        deactivate(token)

    assert "四栏" in planner
    assert "承接可观察状态" in writer
    assert "最小句子/从句" in editor
    assert "硬冲突" in validator


def test_v31_evidence_ordered_hint_is_gated_for_v30(tmp_path):
    context = ExperimentContext(
        run_id="v30-no-v31-hints",
        prompt_version="V30",
        variant="ariadne-A15-v30-handoff-compression",
        project_id="project-test",
        chapter_index=2,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        assert v31_evidence_ordered_continuity_hint("writer") == ""
    finally:
        deactivate(token)


def test_v32_replaces_accumulated_rulebook_with_role_specific_surface(tmp_path):
    context = ExperimentContext(
        run_id="v32-hints",
        prompt_version="V32",
        variant="prompt-surface",
        project_id="project-test",
        chapter_index=2,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = v32_prompt_surface_hint("writer")
        editor = v32_prompt_surface_hint("editor")
        validator = v32_prompt_surface_hint("validator")
        extractor = v32_prompt_surface_hint("extractor")
    finally:
        deactivate(token)

    assert "V32 精简连续性提示面" in writer
    assert "自然场景" in writer
    assert "最小句子" in editor
    assert "才 block" in validator
    assert "inherited_current" in extractor
    assert "V31 证据顺序" not in writer


def test_v32_prompt_surface_is_gated_for_v31(tmp_path):
    context = ExperimentContext(
        run_id="v31-no-v32-surface",
        prompt_version="V31",
        variant="prompt-surface",
        project_id="project-test",
        chapter_index=2,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        assert v32_prompt_surface_hint_gated("writer") == ""
    finally:
        deactivate(token)


def test_v33_memory_update_protocol_is_extractor_specific(tmp_path):
    context = ExperimentContext(
        run_id="v33-memory-protocol",
        prompt_version="V33",
        variant="memory-update-protocol",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        extractor = v33_memory_update_protocol_hint_gated("extractor")
        writer = v33_memory_update_protocol_hint_gated("writer")
    finally:
        deactivate(token)

    assert "V33 记忆更新协议" in extractor
    assert "append_progress" in extractor
    assert '"replacement": true' in extractor
    assert writer == ""


def test_v34_context_ownership_hint_is_role_specific(tmp_path):
    context = ExperimentContext(
        run_id="v34-context-ownership",
        prompt_version="V34",
        variant="context-ownership-current-state",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = v34_context_ownership_hint("writer")
        extractor = v34_context_ownership_hint("extractor")
    finally:
        deactivate(token)

    assert "V34 上下文所有权与当前状态投影" in writer
    assert "角色卡只用于角色事实" in writer
    assert "append_progress" in extractor


def test_v35_writer_narrative_hint_replaces_v34_writer_surface(tmp_path):
    context = ExperimentContext(
        run_id="v35-writer-surface",
        prompt_version="V35",
        variant="writer-execution-brief",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = v35_writer_narrative_hint_gated("writer")
        planner = v35_writer_narrative_hint_gated("planner")
    finally:
        deactivate(token)

    assert "V35 叙事执行模式" in writer
    assert "不是需要逐项复述的清单" in writer
    assert planner == ""


def test_v36_artifact_commitment_hint_is_role_specific_and_gated(tmp_path):
    context = ExperimentContext(
        run_id="v36-artifact-boundary",
        prompt_version="V36",
        variant="writer-recording-commitment",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = v36_artifact_commitment_hint_gated("writer")
        planner = v36_artifact_commitment_hint_gated("planner")
        validator = v36_artifact_commitment_hint_gated("validator")
    finally:
        deactivate(token)

    assert "V36 记录动作与实体承诺边界" in writer
    assert "界面内记录、口述复述、纯观察" in writer
    assert "无新增实体物品" in planner
    assert "硬 item_state 冲突" in validator

    old_context = ExperimentContext(
        run_id="v35-no-artifact-boundary",
        prompt_version="V35",
        variant="writer-execution-brief",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(old_context)
    try:
        assert v36_artifact_commitment_hint_gated("writer") == ""
    finally:
        deactivate(token)


def test_v37_observation_interpretation_hint_is_role_specific_and_gated(tmp_path):
    context = ExperimentContext(
        run_id="v37-observation-boundary",
        prompt_version="V37",
        variant="writer-observation-boundary",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = v37_observation_interpretation_hint_gated("writer")
        planner = v37_observation_interpretation_hint_gated("planner")
        validator = v37_observation_interpretation_hint_gated("validator")
    finally:
        deactivate(token)

    assert "V37 观察与解释边界" in writer
    assert "observed" in writer
    assert "下一份回执已待取回" in writer
    assert "三类" in planner
    assert "越界" in validator

    old_context = ExperimentContext(
        run_id="v36-no-observation-boundary",
        prompt_version="V36",
        variant="writer-recording-commitment",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(old_context)
    try:
        assert v37_observation_interpretation_hint_gated("writer") == ""
    finally:
        deactivate(token)


def test_v38_scene_motion_hint_is_role_specific_and_gated(tmp_path):
    context = ExperimentContext(
        run_id="v38-scene-motion",
        prompt_version="V38",
        variant="scene-motion",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = v38_scene_motion_hint_gated("writer")
        planner = v38_scene_motion_hint_gated("planner")
        validator = v38_scene_motion_hint_gated("validator")
        extractor = v38_scene_motion_hint_gated("extractor")
    finally:
        deactivate(token)


    assert "V38 场景推进与重复信息压缩" in writer
    assert "动作或选择" in writer
    assert "阻力或新信息" in planner
    assert "不得单独触发重写" in validator
    assert "不创建新的 memory_key" in extractor

    old_context = ExperimentContext(
        run_id="v37-no-scene-motion",
        prompt_version="V37",
        variant="observation-boundary",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(old_context)
    try:
        assert v38_scene_motion_hint_gated("writer") == ""
    finally:
        deactivate(token)


def test_v39_single_evidence_delta_hint_is_role_specific_and_gated(tmp_path):
    context = ExperimentContext(
        run_id="v39-single-evidence-delta",
        prompt_version="V39",
        variant="single-evidence-delta",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = v39_single_evidence_delta_hint_gated("writer")
        planner = v39_single_evidence_delta_hint_gated("planner")
        validator = v39_single_evidence_delta_hint_gated("validator")
        extractor = v39_single_evidence_delta_hint_gated("extractor")
    finally:
        deactivate(token)

    assert "V39 单次证据读取与状态增量" in writer
    assert "只完整呈现一次" in writer
    assert "唯一的 state_delta" in planner
    assert "标为 warning" in validator
    assert "不生成 patch" in extractor

    old_context = ExperimentContext(
        run_id="v38-no-single-evidence-delta",
        prompt_version="V38",
        variant="scene-motion",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(old_context)
    try:
        assert v39_single_evidence_delta_hint_gated("writer") == ""
    finally:
        deactivate(token)


def test_v40_contract_state_hint_is_role_specific_and_gated(tmp_path):
    context = ExperimentContext(
        run_id="v40-contract-state",
        prompt_version="V40",
        variant="terminal-state-boundary",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = v40_contract_state_hint_gated("writer")
        planner = v40_contract_state_hint_gated("planner")
        validator = v40_contract_state_hint_gated("validator")
        extractor = v40_contract_state_hint_gated("extractor")
    finally:
        deactivate(token)

    assert "V40 终态边界" in writer
    assert "end_state 是本章最终落点" in writer
    assert "最后已经成立" in planner
    assert "不构成硬冲突" in validator
    assert "真实状态" in extractor

    old_context = ExperimentContext(
        run_id="v39-no-contract-state",
        prompt_version="V39",
        variant="single-evidence-delta",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(old_context)
    try:
        assert v40_contract_state_hint_gated("writer") == ""
    finally:
        deactivate(token)


def test_v41_narrative_escalation_hint_is_role_specific_and_gated(tmp_path):
    context = ExperimentContext(
        run_id="v41-narrative-escalation",
        prompt_version="V41",
        variant="narrative-escalation",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        planner = v41_narrative_escalation_hint_gated("planner")
        writer = v41_narrative_escalation_hint_gated("writer")
        validator = v41_narrative_escalation_hint_gated("validator")
        extractor = v41_narrative_escalation_hint_gated("extractor")
    finally:
        deactivate(token)

    assert "V41 叙事升级与策略改变" in writer
    assert "策略改变" in planner
    assert "不能单独触发 Writer 重写" in validator
    assert "source_chapter" in extractor

    old_context = ExperimentContext(
        run_id="v40-no-narrative-escalation",
        prompt_version="V40",
        variant="terminal-state-boundary",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(old_context)
    try:
        assert v41_narrative_escalation_hint_gated("writer") == ""
    finally:
        deactivate(token)


def test_v42_authority_locked_progression_hint_is_role_specific_and_gated(tmp_path):
    context = ExperimentContext(
        run_id="v42-authority-locked-progression",
        prompt_version="V42",
        variant="authority-locked-progression",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        planner = v42_authority_locked_progression_hint_gated("planner")
        writer = v42_authority_locked_progression_hint_gated("writer")
        validator = v42_authority_locked_progression_hint_gated("validator")
        extractor = v42_authority_locked_progression_hint_gated("extractor")
    finally:
        deactivate(token)

    assert "V42 权威锁定的可观察推进" in writer
    assert "不能用新一章的猜测反转既有状态" in planner
    assert "必须按正文证据与权威来源报告硬冲突" in validator
    assert "candidate/unknown" in extractor

    old_context = ExperimentContext(
        run_id="v41-no-authority-lock",
        prompt_version="V41",
        variant="narrative-escalation",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(old_context)
    try:
        assert v42_authority_locked_progression_hint_gated("writer") == ""
    finally:
        deactivate(token)


def test_v13_narrative_density_hint_is_role_specific_and_gated(tmp_path):
    context = ExperimentContext(
        run_id="v13-hints",
        prompt_version="V13",
        variant="narrative-density",
        project_id="project-test",
        chapter_index=1,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = v13_narrative_density_hint("writer")
        validator = v13_narrative_density_hint("validator")
    finally:
        deactivate(token)

    assert "谁因此做了什么" in writer
    assert "不得触发内容重试" in validator

    old_context = ExperimentContext(
        run_id="v12-no-v13",
        prompt_version="V12",
        variant="narrative-density",
        project_id="project-test",
        chapter_index=1,
        root_dir=tmp_path,
    )
    token = activate(old_context)
    try:
        assert v13_narrative_density_hint("writer") == ""
    finally:
        deactivate(token)


def test_v14_continuity_language_hint_separates_fields_and_closures(tmp_path):
    context = ExperimentContext(
        run_id="v14-hints",
        prompt_version="V14",
        variant="continuity-language",
        project_id="project-test",
        chapter_index=1,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = v14_continuity_language_hint("writer")
        validator = v14_continuity_language_hint("validator")
    finally:
        deactivate(token)

    assert "来源元数据字段" in writer
    assert "帧内来源字段" in writer
    assert "作者式报告收束" in writer
    assert "具体术语歧义" in validator

    old_context = ExperimentContext(
        run_id="v13-no-v14",
        prompt_version="V13",
        variant="continuity-language",
        project_id="project-test",
        chapter_index=1,
        root_dir=tmp_path,
    )
    token = activate(old_context)
    try:
        assert v14_continuity_language_hint("writer") == ""
    finally:
        deactivate(token)


def test_v15_compact_evidence_and_character_action_hint_is_gated(tmp_path):
    context = ExperimentContext(
        run_id="v15-hints",
        prompt_version="V15",
        variant="compact-evidence-character-action",
        project_id="project-test",
        chapter_index=1,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = v15_compact_evidence_and_character_action_hint("writer")
        validator = v15_compact_evidence_and_character_action_hint("validator")
    finally:
        deactivate(token)

    assert "四项清单" in writer
    assert writer.count("来源元数据字段") == 1
    assert writer.count("帧内来源字段") == 1
    assert "目标、选择、后果" in writer
    assert "不得单独阻断" in validator

    old_context = ExperimentContext(
        run_id="v14-no-v15",
        prompt_version="V14",
        variant="compact-evidence-character-action",
        project_id="project-test",
        chapter_index=1,
        root_dir=tmp_path,
    )
    token = activate(old_context)
    try:
        assert v15_compact_evidence_and_character_action_hint("writer") == ""
    finally:
        deactivate(token)
