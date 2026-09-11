import json
from types import SimpleNamespace

from agents.pipeline_context import PipelineContext
from services.chapter_continuity import ChapterHandoff, writer_execution_brief
from services.context_compaction import (
    compact_json,
    context_budget_for,
    memory_context_breakdown,
)
from services.continuity_contract import contract_prompt, prompt_outline_for_agent
from services.experiment_recorder import ExperimentContext, activate, deactivate


def test_compact_json_is_valid_and_bounded():
    result = compact_json({"facts": ["事实" * 1000], "sources": ["source"]}, 500)

    assert len(result) <= 500
    assert json.loads(result)




def test_v34_contract_assigns_inherited_state_to_handoff(tmp_path):
    context = ExperimentContext(
        run_id="v34-contract",
        prompt_version="V34",
        variant="context-ownership-current-state",
        project_id="project",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        result = json.loads(contract_prompt({
            "required_events": ["角色核对门前回执"],
            "continuity_from_previous": ["上一章已在门前"],
            "state_changes": ["记录新的字段缺口"],
            "foreshadowing_actions": ["推进发送者线索"],
            "end_state": "保留未知发送者",
            "unknown_boundary": ["发送者身份未知"],
            "uncertain_events": ["回执来源待核对"],
            "forbidden_deviations": ["不得把界面读取写成开门"],
            "evidence_state_ledger": [{"proposition": "不应重复注入"}],
        }, agent_type="writer"))
    finally:
        deactivate(token)

    assert result["required_events"] == ["角色核对门前回执"]
    assert "continuity_from_previous" not in result
    assert "evidence_state_ledger" not in result
    assert any(
        "上一章继承状态以交接包为准" in item
        for item in result["execution_boundaries"]
    )




def test_v10_prompt_outline_removes_nested_contract_without_mutating_saved_outline(tmp_path):
    outline = {
        "title": "第3章",
        "summary": "推进调查",
        "continuity_contract": {"evidence_state_ledger": ["large"]},
    }
    context = ExperimentContext(
        run_id="v10-outline",
        prompt_version="V10",
        variant="context-compaction",
        project_id="project",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        prompt_outline = prompt_outline_for_agent(outline)
    finally:
        deactivate(token)

    assert "continuity_contract" not in prompt_outline
    assert "continuity_contract" in outline


def test_v35_writer_outline_keeps_narrative_fields_and_drops_audit_fields(tmp_path):
    context = ExperimentContext(
        run_id="v35-writer-outline",
        prompt_version="V35",
        variant="writer-execution-brief",
        project_id="project",
        chapter_index=3,
        root_dir=tmp_path,
    )
    outline = {
        "title": "第3章",
        "summary": "推进调查",
        "key_events": ["角色观察设备"],
        "beats": ["从观察到选择"],
        "forbidden_changes": ["不得开门"],
        "unknown_boundary": ["来源未知"],
        "continuity_contract": {"required_events": ["重复字段"]},
    }
    token = activate(context)
    try:
        projected = prompt_outline_for_agent(outline, agent_type="writer")
    finally:
        deactivate(token)

    assert projected["key_events"] == ["角色观察设备"]
    assert projected["beats"] == ["从观察到选择"]
    assert "forbidden_changes" not in projected
    assert "unknown_boundary" not in projected
    assert outline["continuity_contract"]




def test_v30_handoff_keeps_execution_state_and_drops_transition_history(tmp_path):
    context = ExperimentContext(
        run_id="v30-handoff",
        prompt_version="V30",
        variant="ariadne-A15-v30-handoff-compression",
        project_id="project",
        chapter_index=5,
        root_dir=tmp_path,
    )
    handoff = ChapterHandoff(
        previous_chapter=4,
        previous_title="白塔门前",
        exact_ending="林默停在白塔门前，读取位置仍未展开，下一次读取指向内侧。",
        end_scene={"location": "白塔门前", "time": "夜间", "status": "门仍关闭"},
        characters_present=["林默", "记录员"],
        inherited_state=[{
            "memory_key": "gate:state",
            "statement": "白塔门仍关闭。",
            "state": "closed",
            "authority": "accepted",
            "source_chapter": 4,
            "rule": "本章开场已经成立；只有明确动作才能改变。",
        }],
        state_changes=["读取位置显示为内侧"],
        open_questions=["读取位置对应什么入口"],
        foreshadowing=["推进白塔内侧读取线索"],
        next_hook="下一次读取：请至内侧。",
        item_state_ledger=[{
            "memory_key": "item:record",
            "name": "残缺记录",
            "current_statement": "记录仍由林默保存。",
            "current_state": "held",
            "source_chapter": 4,
            "authority": "accepted",
            "transitions": [{"chapter": index, "statement": "history"} for index in range(20)],
        }],
        evidence_state_ledger=[{
            "evidence_kind": "attribution",
            "memory_key": "identity:sender",
            "subject": "sender",
            "proposition": "发送者身份未知。",
            "status": "accepted",
            "authority": "accepted",
            "source_chapter": 4,
            "allowed_claim": "不得升级为身份确认。",
        }],
        unknown_boundary=["发送者身份未知。"],
    )
    token = activate(context)
    try:
        rendered = handoff.to_compact_prompt(max_chars=1800)
    finally:
        deactivate(token)

    parsed = json.loads(rendered)
    assert len(rendered) <= 1800
    assert parsed["exact_ending"].startswith("林默停在")
    assert parsed["next_hook"] == "下一次读取：请至内侧。"
    assert parsed["item_states"][0]["current_state"] == "held"
    assert parsed["evidence_states"][0]["proposition"] == "发送者身份未知。"
    assert parsed["unknown_boundary"] == ["发送者身份未知。"]
    assert "transitions" not in rendered


def test_v30_uses_dedicated_handoff_budgets(tmp_path):
    context = ExperimentContext(
        run_id="v30-budget",
        prompt_version="V30",
        variant="ariadne-A15-v30-handoff-compression",
        project_id="project",
        chapter_index=5,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = context_budget_for("writer")
        extractor = context_budget_for("extractor")
    finally:
        deactivate(token)

    assert writer.handoff_chars == 3000
    assert extractor.handoff_chars == 2800


def test_v31_reuses_v30_budgets_to_isolate_prompt_guidance(tmp_path):
    context = ExperimentContext(
        run_id="v31-budget",
        prompt_version="V31",
        variant="ariadne-A16-v31-evidence-ordered-continuity",
        project_id="project",
        chapter_index=5,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = context_budget_for("writer")
        validator = context_budget_for("validator")
    finally:
        deactivate(token)

    assert writer.handoff_chars == 3000
    assert validator.handoff_chars == 3200


def test_v35_writer_execution_brief_merges_continuity_without_audit_ledgers(tmp_path):
    context = ExperimentContext(
        run_id="v35-writer-brief",
        prompt_version="V35",
        variant="writer-execution-brief",
        project_id="project",
        chapter_index=3,
        root_dir=tmp_path,
    )
    handoff = ChapterHandoff(
        previous_chapter=2,
        exact_ending="林默停在白塔门前，设备显示等待确认。",
        end_scene={"scope_key": "白塔门前", "current_state": {"door": "closed"}},
        characters_present=["林默"],
        inherited_state=[{
            "memory_key": "door:state",
            "statement": "白塔门仍关闭。",
            "state": "closed",
            "authority": "accepted",
        }],
        open_questions=["确认对象仍未知。"],
        unknown_boundary=["发送者身份未知。"],
        evidence_state_ledger=[{
            "memory_key": "identity:sender",
            "proposition": "发送者身份未知。",
        }],
    )
    contract = {
        "required_events": ["林默记录设备的新反馈。"],
        "state_changes": ["调查从界面操作转向现场核对。"],
        "foreshadowing_actions": ["推进确认机制，但不揭示发送者。"],
        "end_state": "留下新的现场调查入口。",
        "unknown_boundary": ["不得确认标记的来源。"],
        "forbidden_deviations": ["不得把界面读取写成开门。"],
    }
    token = activate(context)
    try:
        rendered = writer_execution_brief(handoff, contract, max_chars=2400)
    finally:
        deactivate(token)

    payload = json.loads(rendered)
    assert len(rendered) <= 2400
    assert payload["opening"]["previous_ending"].startswith("林默停在")
    assert payload["chapter_execution"]["required_actions"] == ["林默记录设备的新反馈。"]
    assert "evidence_state_ledger" not in rendered
    assert "发送者身份未知。" in rendered


def test_v36_writer_execution_brief_exposes_recording_boundary(tmp_path):
    context = ExperimentContext(
        run_id="v36-writer-brief",
        prompt_version="V36",
        variant="writer-recording-commitment",
        project_id="project",
        chapter_index=3,
        root_dir=tmp_path,
    )
    handoff = ChapterHandoff(
        previous_chapter=2,
        exact_ending="林默停在白塔门前，设备显示等待确认。",
        end_scene={"scope_key": "白塔门前", "current_state": {"door": "closed"}},
        item_state_ledger=[],
    )
    contract = {
        "required_events": ["林默记录设备的新反馈。"],
        "recording_action_rules": {
            "mode": "no_new_physical_record_artifact",
            "allowed_default": ["界面内记录", "口述复述", "纯观察"],
            "requires_matching_ledger": ["笔记本", "纸张"],
            "rule": "记录信息不得自动新增具体实体物品。",
        },
    }
    token = activate(context)
    try:
        rendered = writer_execution_brief(handoff, contract, max_chars=2400)
    finally:
        deactivate(token)

    payload = json.loads(rendered)
    assert payload["chapter_execution"]["recording_boundary"]["mode"] == "no_new_physical_record_artifact"
    assert "笔记本" in payload["chapter_execution"]["recording_boundary"]["requires_matching_ledger"]
    assert "writer_execution_brief_v36" not in rendered
    assert "记录信息不得自动新增具体实体物品。" in rendered


def test_v37_writer_execution_brief_exposes_interpretation_boundary(tmp_path):
    context = ExperimentContext(
        run_id="v37-writer-brief",
        prompt_version="V37",
        variant="writer-observation-boundary",
        project_id="project",
        chapter_index=3,
        root_dir=tmp_path,
    )
    handoff = ChapterHandoff(
        previous_chapter=2,
        exact_ending="林默停在白塔门前，设备显示等待确认。",
        end_scene={"scope_key": "白塔门前", "current_state": {"door": "closed"}},
    )
    contract = {
        "required_events": ["查询下一份回执。"],
        "interpretation_boundary_rules": {
            "observed": ["设备显示的原文"],
            "tentative": ["保留可能/无法判断"],
            "investigation": ["查询和核对动作"],
            "forbidden_upgrades": ["不得把提示升级为已发生历史或设备意图"],
            "rule": "先写观察，再写保留不确定性的猜测或调查。",
        },
    }
    token = activate(context)
    try:
        rendered = writer_execution_brief(handoff, contract, max_chars=2400)
    finally:
        deactivate(token)

    payload = json.loads(rendered)
    assert payload["interpretation_boundary"]["observed"] == ["设备显示的原文"]
    assert "已发生历史" in payload["interpretation_boundary"]["forbidden_upgrades"][0]
    assert "writer_execution_brief_v37" not in rendered


def test_v40_writer_execution_brief_exposes_terminal_state_boundary(tmp_path):
    context = ExperimentContext(
        run_id="v40-writer-brief",
        prompt_version="V40",
        variant="terminal-state-boundary",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    handoff = ChapterHandoff(
        previous_chapter=2,
        exact_ending="林默停在白塔门前，设备显示等待确认。",
        end_scene={"scope_key": "白塔门前", "current_state": {"door": "closed"}},
    )
    contract = {
        "end_state": "林默停在门槛前，等待下一条提示。",
        "end_state_boundary": {
            "authority": "terminal_chapter_state",
            "final_state": "林默停在门槛前，等待下一条提示。",
            "rule": "正文不得越过该终态。",
            "resolution": "轻微措辞差异由 Editor 局部统一。",
        },
    }
    token = activate(context)
    try:
        rendered = writer_execution_brief(handoff, contract, max_chars=2400)
    finally:
        deactivate(token)

    payload = json.loads(rendered)
    assert payload["chapter_execution"]["end_state_boundary"]["authority"] == "terminal_chapter_state"
    assert "不得越过该终态" in payload["chapter_execution"]["end_state_boundary"]["rule"]


def test_memory_context_breakdown_is_explicit():
    context = PipelineContext(
        project_id="project",
        chapter_index=3,
        novel_format="long_webnovel",
        novel_memory_context="记忆",
        narrative_index_context="索引",
        chapter_handoff_context="交接",
        chapter_contract_context="契约",
        character_card_context="角色卡",
    )

    breakdown = memory_context_breakdown(context)

    assert breakdown == {
        "novel_memory_context": 2,
        "narrative_index_context": 2,
        "chapter_handoff_context": 2,
        "chapter_contract_context": 2,
        "character_card_context": 3,
    }
    assert context_budget_for("writer").handoff_chars < 9000


def test_v19_uses_tighter_prompt_budgets_without_changing_v10_budgets(tmp_path):
    context = ExperimentContext(
        run_id="v19-budget",
        prompt_version="V19",
        variant="prompt-budget",
        project_id="project",
        chapter_index=4,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = context_budget_for("writer")
        validator = context_budget_for("validator")
    finally:
        deactivate(token)

    assert writer.memory_chars <= 3600
    assert writer.handoff_chars <= 4000
    assert writer.contract_chars <= 3600
    assert writer.character_chars <= 6500
    assert validator.memory_chars <= 4200
    assert validator.handoff_chars <= 4000


def test_v20_restores_v12_prompt_budgets_while_retaining_state_rules(tmp_path):
    context = ExperimentContext(
        run_id="v20-budget",
        prompt_version="V20",
        variant="low-retry-state",
        project_id="project",
        chapter_index=4,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = context_budget_for("writer")
        validator = context_budget_for("validator")
    finally:
        deactivate(token)

    assert writer.memory_chars == 5000
    assert writer.handoff_chars == 5200
    assert writer.contract_chars == 4800
    assert validator.memory_chars == 5500


def test_v18_keeps_previous_prompt_budget_contract(tmp_path):
    context = ExperimentContext(
        run_id="v18-budget",
        prompt_version="V18",
        variant="prompt-budget",
        project_id="project",
        chapter_index=4,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        writer = context_budget_for("writer")
    finally:
        deactivate(token)

    assert writer.memory_chars == 5000
    assert writer.handoff_chars == 5200
