import json
from pathlib import Path
from types import SimpleNamespace

from research.prompt_versions.hints import (
    v53_cross_chapter_stage_hint,
)
from agents.writing_schemas import PlannerChapterOutlineResponse
from services.chapter_continuity import (
    ChapterHandoff,
    build_completed_event_ledger,
)
from services.continuity_contract import build_chapter_contract, contract_prompt
from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate


def _context(tmp_path):
    return ExperimentContext(
        run_id="v53-cross-chapter-stage-ledger",
        prompt_version="V53",
        variant="ariadne-a39-v53-cross-chapter-stage-ledger",
        project_id="project",
        chapter_index=3,
        root_dir=Path(tmp_path),
    )


def test_v53_registers_version_and_reaches_all_writing_agents(tmp_path):
    token = activate(_context(tmp_path))
    try:
        assert prompt_version_at_least("V52")
        assert prompt_version_at_least("V53")
        for agent_type in ("planner", "writer", "editor", "validator", "extractor"):
            hint = v53_cross_chapter_stage_hint(agent_type)
            assert "V53 跨章阶段账本" in hint
            assert "completed_event_ledger" in hint
            assert "new_stage_delta" in hint
    finally:
        deactivate(token)


def test_completed_event_ledger_is_deterministic_and_deduplicated():
    atom = SimpleNamespace(atom_type="plot_thread", statement="林默关闭读取窗口")
    ledger = build_completed_event_ledger(
        {
            "required_events": ["林默关闭读取窗口"],
            "state_changes": ["调查入口转为只读"],
            "beats": [{"action": "不应从非事件字段读取"}],
        },
        [atom],
        source_chapter=2,
        end_scene={"recent_changes": ["调查入口转为只读"]},
    )

    assert [item["event"] for item in ledger] == [
        "林默关闭读取窗口",
        "调查入口转为只读",
    ]
    assert all(item["status"] == "completed" for item in ledger)


def test_v53_contract_requires_new_stage_delta_and_exposes_prior_progress(tmp_path):
    token = activate(_context(tmp_path))
    try:
        handoff = {
            "completed_event_ledger": [
                {"event": "关闭读取窗口", "status": "completed", "source_chapter": 2}
            ],
            "previous_terminal_state": {
                "narrative_stage": "调查入口",
                "end_state": "入口保持只读",
            },
        }
        contract = build_chapter_contract(
            {
                "required_events": ["前往新的调查入口"],
                "new_stage_delta": ["从界面核对转入现场追踪"],
                "end_state": "锁定新的现场追踪方向",
            },
            handoff,
            enforce_authority=True,
        )
        rendered = json.loads(contract_prompt(contract, agent_type="writer"))
    finally:
        deactivate(token)

    assert contract["new_stage_delta"] == ["从界面核对转入现场追踪"]
    assert contract["previous_progress"]["completed_event_ledger"][0]["event"] == "关闭读取窗口"
    assert "completed_event_ledger" in json.dumps(rendered, ensure_ascii=False)
    assert "new_stage_delta" in rendered
    assert any("不得把 completed_event_ledger" in item for item in contract["forbidden_deviations"])


def test_outline_schema_accepts_stage_delta_as_string_or_list():
    outline = PlannerChapterOutlineResponse(
        chapter_index=3,
        title="转入现场",
        summary="从界面调查转向现场追踪",
        emotional_arc="谨慎转为决断",
        new_stage_delta="从界面核对转入现场追踪",
    )

    assert outline.new_stage_delta == ["从界面核对转入现场追踪"]


def test_handoff_compact_prompt_contains_previous_terminal_state(tmp_path):
    token = activate(_context(tmp_path))
    try:
        handoff = ChapterHandoff(
            previous_chapter=2,
            completed_event_ledger=[{"event": "完成初次核对", "status": "completed"}],
            previous_terminal_state={"end_state": "入口保持只读"},
        )
        payload = json.loads(handoff.to_compact_prompt())
    finally:
        deactivate(token)

    assert payload["completed_event_ledger"][0]["event"] == "完成初次核对"
    assert payload["previous_terminal_state"]["end_state"] == "入口保持只读"
