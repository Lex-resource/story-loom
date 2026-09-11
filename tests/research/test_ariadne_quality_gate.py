from pathlib import Path

from research.prompt_versions.quality_gate import assess_polisher_gate
from services.experiment_recorder import ExperimentContext, activate, deactivate


def _context(variant: str, root_dir: Path):
    return ExperimentContext(
        run_id="a5-test",
        prompt_version="V12",
        variant=variant,
        project_id="project",
        chapter_index=2,
        root_dir=root_dir,
    )


def test_a5_gate_is_disabled_for_v12_baseline(tmp_path):
    token = activate(_context("ariadne-A4-v12", tmp_path))
    try:
        result = assess_polisher_gate(
            {"passed": False, "hard_issues": [{"severity": "block", "category": "timeline"}]}
        )
    finally:
        deactivate(token)

    assert result["eligible"] is False
    assert result["reason"] == "experiment_disabled"


def test_a5_gate_only_opens_for_explicit_hard_continuity_issue(tmp_path):
    token = activate(_context("ariadne-A5-v12-gated-polisher", tmp_path))
    try:
        hard = assess_polisher_gate(
            {
                "passed": False,
                "hard_issues": [
                    {
                        "severity": "block",
                        "category": "timeline",
                        "error_type": "时间线矛盾",
                        "description": "角色在同一时刻出现在两个地点",
                    }
                ],
            }
        )
        local = assess_polisher_gate(
            {
                "passed": False,
                "hard_issues": [
                    {"severity": "warning", "category": "style", "description": "术语混用"}
                ],
            }
        )
    finally:
        deactivate(token)

    assert hard["eligible"] is True
    assert hard["reason"] == "hard_continuity_issue"
    assert local["eligible"] is False
    assert local["reason"] == "non_hard_or_local_issue"


def test_a7_gate_never_spends_an_extra_polisher_call(tmp_path):
    token = activate(_context("ariadne-A7-v12-contract-hygiene", tmp_path))
    try:
        result = assess_polisher_gate(
            {"passed": False, "hard_issues": [{"severity": "block", "category": "timeline"}]}
        )
    finally:
        deactivate(token)

    assert result["eligible"] is False
    assert result["reason"] == "a7_no_extra_polisher"
