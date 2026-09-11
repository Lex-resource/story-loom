from agents.prompt_hints import (
    compact_layered_prompt,
)
from research.prompt_versions.hints import (
    v44_compact_input_surface_hint,
)
from services.context_compaction import context_budget_for
from services.continuity_contract import prompt_outline_for_agent
from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate


def _context(tmp_path):
    return ExperimentContext(
        run_id="v44-input-surface",
        prompt_version="V44",
        variant="ariadne-a29-v44-compact-input-surface",
        project_id="project",
        chapter_index=3,
        root_dir=tmp_path,
    )


def test_v44_uses_compact_role_surface_and_smaller_budgets(tmp_path):
    token = activate(_context(tmp_path))
    try:
        assert prompt_version_at_least("V44")
        assert "V44 输入面压缩与上下文所有权" in v44_compact_input_surface_hint("editor")
        assert context_budget_for("editor").contract_chars < 3000
    finally:
        deactivate(token)


def test_v44_removes_empty_legacy_blocks_but_keeps_nonempty_content(tmp_path):
    token = activate(_context(tmp_path))
    try:
        prompt = (
            "【世界状态】\n<user_content>\n\n</user_content>\n\n"
            "【当前场景块】\n<user_content>\n白塔门前\n</user_content>"
        )
        compacted = compact_layered_prompt(prompt)
    finally:
        deactivate(token)

    assert "【世界状态】" not in compacted
    assert "白塔门前" in compacted


def test_v44_projects_execution_outline_without_audit_contract(tmp_path):
    token = activate(_context(tmp_path))
    try:
        projected = prompt_outline_for_agent(
            {
                "chapter_index": 3,
                "title": "第三章",
                "summary": "推进调查",
                "required_events": ["观察现场"],
                "end_state": "保持未知",
                "continuity_contract": {"evidence_boundaries": ["不要推断"]},
                "evidence_surface_rules": [{"surface": "audit-only"}],
            },
            agent_type="editor",
        )
    finally:
        deactivate(token)

    assert projected == {
        "chapter_index": 3,
        "title": "第三章",
        "summary": "推进调查",
        "required_events": ["观察现场"],
        "end_state": "保持未知",
    }
