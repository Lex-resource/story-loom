import json
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.providers import resolve_active_provider
from config import DEFAULT_CONTINUITY_PROMPT_VERSION, Settings
from services.chapter_continuity import (
    ChapterHandoff,
    build_chapter_handoff,
    build_evidence_state_ledger,
    build_item_state_ledger,
)
from research.prompt_versions.version_order import prompt_version_at_least
from services.experiment_recorder import ExperimentContext, activate, deactivate, record_chapter_finished, record_content_retry, record_json_recovery, record_llm_attempt, record_prompt_template, record_published_chapter
from services.quality_metrics import meets_quality_gate, quality_summary
from worker_support.generation_editor_policy import resolve_editor_decision_from_result
from worker_support.generation_validator_policy import (
    is_soft_contract_alignment_issue,
    requires_content_retry,
    validation_errors_text,
)
from worker_support import generate_job_runner


def test_production_continuity_profile_defaults_to_a28_v43():
    assert DEFAULT_CONTINUITY_PROMPT_VERSION == "V43"
    assert Settings.model_fields["NOVEL_CONTINUITY_PROMPT_VERSION"].default == "V43"


def test_in_job_retries_share_one_experiment_completion_record(monkeypatch, tmp_path):
    experiment = {
        "run_id": "run-shared-retry-context",
        "prompt_version": "V12",
        "variant": "production-regression",
        "root_dir": str(tmp_path),
    }
    job = SimpleNamespace(
        params={"experiment": experiment},
        status="running",
    )
    novel = SimpleNamespace(id="project-test", status="generating")
    seen_context_ids = []

    async def fake_load_settings():
        return {
            "active_provider_id": "openai-main",
            "providers": [{"id": "openai-main", "name": "OpenAI", "model": "gpt-test"}],
            "backup_provider_id": None,
        }

    async def fake_process(_db, _job, _novel, chapter_index, attempt=1, *, experiment=None):
        seen_context_ids.append(id(experiment))
        if attempt == 1:
            return await generate_job_runner.process_single_chapter(
                _db,
                _job,
                _novel,
                chapter_index,
                attempt + 1,
                _experiment=experiment,
            )
        return {"status": "ok"}

    monkeypatch.setattr(generate_job_runner, "load_settings", fake_load_settings)
    monkeypatch.setattr(generate_job_runner, "_process_single_chapter", fake_process)

    asyncio.run(
        generate_job_runner.process_single_chapter(
            None,
            job,
            novel,
            1,
        )
    )

    events = [
        json.loads(line)
        for line in (tmp_path / experiment["run_id"] / "events" / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    finished = [event for event in events if event["event"] == "chapter_finished"]
    assert len(seen_context_ids) == 2
    assert len(set(seen_context_ids)) == 1
    assert len(finished) == 1
    assert finished[0]["status"] == "completed"


def test_openai_provider_resolution_includes_embedding_model(monkeypatch):
    selected = resolve_active_provider(
        {
            "active_provider_id": "openai-main",
            "providers": [
                {
                    "id": "openai-main",
                    "name": "OpenAI",
                    "base_url": "https://example.test/v1",
                    "api_key": "secret",
                    "model": "gpt-test",
                    "embedding_model": "text-embedding-test",
                }
            ],
        }
    )
    assert selected.provider_name == "OpenAI"
    assert selected.model == "gpt-test"
    assert selected.embedding_model == "text-embedding-test"


def test_experiment_recorder_writes_prompt_and_metrics(tmp_path):
    context = ExperimentContext(
        run_id="run-test",
        prompt_version="V5",
        variant="retry-policy",
        project_id="project-test",
        chapter_index=3,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        assert prompt_version_at_least("V4")
        record_prompt_template(
            name="writer",
            category="long_webnovel",
            system_prompt="system",
            user_prompt_template="user {chapter_outline}",
        )
        record_llm_attempt(
            agent_name="writer",
            prompt_name="writer (long_webnovel)",
            system_prompt="system",
            user_prompt="user",
            provider_name="OpenAI",
            model="gpt-test",
            base_url="https://example.test/v1",
            attempt=0,
            is_fallback=False,
            response="正文",
        )
        record_json_recovery("invalid json")
        record_content_retry("hard conflict", "repair state")
    finally:
        deactivate(token)

    template = tmp_path / "run-test" / "templates" / "V5" / "long_webnovel" / "writer.json"
    snapshot_files = list((tmp_path / "run-test" / "prompts" / "chapter-0003").glob("*.json"))
    events = (tmp_path / "run-test" / "events" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert template.exists()
    assert snapshot_files
    assert {json.loads(item)["event"] for item in events} == {"llm_attempt", "json_recovery", "content_retry"}


def test_experiment_recorder_writes_chapter_finished_once(tmp_path):
    context = ExperimentContext(
        run_id="run-finished",
        prompt_version="V6",
        variant="continuity",
        project_id="project-test",
        chapter_index=10,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        record_chapter_finished(status="completed", rewrite_count=0)
        record_chapter_finished(status="error", rewrite_count=1)
    finally:
        deactivate(token)

    events = [
        json.loads(item)
        for item in (tmp_path / "run-finished" / "events" / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [event["event"] for event in events] == ["chapter_finished"]
    assert events[0]["status"] == "completed"


def test_published_chapter_reconciles_paused_history_once(tmp_path):
    experiment = {
        "run_id": "run-published-reconcile",
        "prompt_version": "V9",
        "variant": "continuity",
        "root_dir": str(tmp_path),
    }
    context = ExperimentContext(
        run_id=experiment["run_id"],
        prompt_version=experiment["prompt_version"],
        variant=experiment["variant"],
        project_id="project-test",
        chapter_index=4,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        record_llm_attempt(
            agent_name="writer",
            prompt_name="writer",
            system_prompt="system",
            user_prompt="user",
            provider_name="OpenAI",
            model="gpt-test",
            base_url="https://example.test/v1",
            attempt=0,
            is_fallback=False,
            response="正文",
            input_tokens=100,
            output_tokens=50,
            memory_context_chars=1200,
        )
        record_llm_attempt(
            agent_name="writer",
            prompt_name="writer",
            system_prompt="system",
            user_prompt="user",
            provider_name="OpenAI",
            model="gpt-test",
            base_url="https://example.test/v1",
            attempt=1,
            is_fallback=False,
            error="502",
            input_tokens=80,
            output_tokens=0,
            memory_context_chars=1000,
        )
        record_content_retry("hard conflict", "repair state")
        record_chapter_finished(status="paused", rewrite_count=1)
    finally:
        deactivate(token)

    assert record_published_chapter(
        experiment,
        project_id="project-test",
        chapter_index=4,
        publication_source="reviewed_extractor_publish",
    )
    assert not record_published_chapter(
        experiment,
        project_id="project-test",
        chapter_index=4,
        publication_source="reviewed_extractor_publish",
    )

    events = [
        json.loads(item)
        for item in (tmp_path / experiment["run_id"] / "events" / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    finished = [event for event in events if event["event"] == "chapter_finished"]
    assert len(finished) == 2
    reconciled = finished[-1]
    assert reconciled["status"] == "completed"
    assert reconciled["reconciled_from_events"] is True
    assert reconciled["content_retry_count"] == 1
    assert reconciled["api_retry_count"] == 1
    assert reconciled["llm_call_count"] == 1
    assert reconciled["llm_attempt_count"] == 2
    assert reconciled["input_tokens"] == 180
    assert reconciled["output_tokens"] == 50
    assert reconciled["memory_context_chars_min"] == 1000
    assert reconciled["memory_context_chars_max"] == 1200


def test_active_resumed_publication_reconciles_prior_paused_segment(tmp_path):
    experiment = {
        "run_id": "run-active-resume-reconcile",
        "prompt_version": "V9",
        "variant": "continuity",
        "root_dir": str(tmp_path),
    }
    paused_context = ExperimentContext(
        run_id=experiment["run_id"],
        prompt_version=experiment["prompt_version"],
        variant=experiment["variant"],
        project_id="project-test",
        chapter_index=7,
        root_dir=tmp_path,
    )
    token = activate(paused_context)
    try:
        record_llm_attempt(
            agent_name="writer",
            prompt_name="writer",
            system_prompt="system",
            user_prompt="paused",
            provider_name="OpenAI",
            model="gpt-test",
            base_url="https://example.test/v1",
            attempt=0,
            is_fallback=False,
            response="暂停前正文",
            input_tokens=100,
            output_tokens=50,
            memory_context_chars=1200,
        )
        record_content_retry("hard conflict", "repair state")
        record_chapter_finished(status="paused", rewrite_count=1)
    finally:
        deactivate(token)

    resumed_context = ExperimentContext(
        run_id=experiment["run_id"],
        prompt_version=experiment["prompt_version"],
        variant=experiment["variant"],
        project_id="project-test",
        chapter_index=7,
        root_dir=tmp_path,
    )
    token = activate(resumed_context)
    try:
        record_llm_attempt(
            agent_name="validator",
            prompt_name="validator",
            system_prompt="system",
            user_prompt="resumed",
            provider_name="OpenAI",
            model="gpt-test",
            base_url="https://example.test/v1",
            attempt=1,
            is_fallback=False,
            response="通过",
            input_tokens=80,
            output_tokens=20,
            memory_context_chars=1000,
        )
        assert record_published_chapter(
            experiment,
            project_id="project-test",
            chapter_index=7,
            publication_source="post_processing",
        )
        record_chapter_finished(status="error", rewrite_count=99)
    finally:
        deactivate(token)

    events = [
        json.loads(item)
        for item in (tmp_path / experiment["run_id"] / "events" / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    finished = [event for event in events if event["event"] == "chapter_finished"]
    assert len(finished) == 2
    reconciled = finished[-1]
    assert reconciled["status"] == "completed"
    assert reconciled["reconciled_from_events"] is True
    assert reconciled["prior_statuses"] == ["paused"]
    assert reconciled["segment_count"] == 2
    assert reconciled["content_retry_count"] == 1
    assert reconciled["api_retry_count"] == 1
    assert reconciled["llm_call_count"] == 1
    assert reconciled["llm_attempt_count"] == 2
    assert reconciled["input_tokens"] == 180
    assert reconciled["output_tokens"] == 70
    assert reconciled["memory_context_chars_min"] == 1000
    assert reconciled["memory_context_chars_max"] == 1200
    assert reconciled["wall_clock_seconds"] >= finished[0]["wall_clock_seconds"]


def test_published_chapter_closes_active_context_without_duplicate(tmp_path):
    experiment = {
        "run_id": "run-active-publication",
        "prompt_version": "V9",
        "variant": "continuity",
        "root_dir": str(tmp_path),
    }
    context = ExperimentContext(
        run_id=experiment["run_id"],
        prompt_version=experiment["prompt_version"],
        variant=experiment["variant"],
        project_id="project-test",
        chapter_index=2,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        assert record_published_chapter(
            experiment,
            project_id="project-test",
            chapter_index=2,
            publication_source="post_processing",
        )
        record_chapter_finished(status="error", rewrite_count=1)
    finally:
        deactivate(token)

    events = [
        json.loads(item)
        for item in (tmp_path / experiment["run_id"] / "events" / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    finished = [event for event in events if event["event"] == "chapter_finished"]
    assert len(finished) == 1
    assert finished[0]["status"] == "completed"
    assert finished[0]["publication_source"] == "post_processing"


def test_first_chapter_handoff_is_explicitly_unknown():
    handoff = asyncio.run(build_chapter_handoff(None, "project", 1))
    assert isinstance(handoff, ChapterHandoff)
    assert handoff.previous_chapter == 0
    assert handoff.unknown_boundary


def test_v7_item_ledger_keeps_only_accepted_transitions():
    def atom(*, status, chapter, version, state, statement):
        return SimpleNamespace(
            status=status,
            atom_type="world_rule",
            memory_key="world_rule:证物R2",
            source_chapter=chapter,
            version=version,
            source_ref=f"chapter:{chapter}:extractor",
            authority="generated",
            statement=statement,
            data={
                "category": "world_rule",
                "operation": "merge",
                "data": {"rule_type": "item", "state": state},
            },
        )

    ledger = build_item_state_ledger([
        atom(status="accepted", chapter=1, version=1, state="封存", statement="证物R2已封存"),
        atom(status="accepted", chapter=2, version=2, state="已开封", statement="证物R2在核验中开封"),
        atom(status="candidate", chapter=3, version=3, state="已转移", statement="证物R2已转移给林渡"),
    ])

    assert len(ledger) == 1
    assert ledger[0]["current_state"] == "已开封"
    assert [item["chapter"] for item in ledger[0]["transitions"]] == [1, 2]
    assert "林渡" not in ledger[0]["current_statement"]


def test_v8_evidence_ledger_preserves_kind_and_forbids_escalation():
    def atom(memory_key, statement, rule_type="", chapter=2, status="accepted"):
        return SimpleNamespace(
            status=status,
            atom_type="world_rule",
            memory_key=memory_key,
            source_chapter=chapter,
            version=1,
            source_ref=f"chapter:{chapter}:extractor",
            authority="accepted",
            statement=statement,
            data={"data": {"rule_type": rule_type}},
        )

    ledger = build_evidence_state_ledger([
        atom("world_rule:旧中继", "旧中继当前只返回历史回执", "capability"),
        atom("world_rule:林晦记录", "记录署名林晦，作者身份待核"),
        atom("world_rule:接口片", "接口片已封存", "item"),
        atom("world_rule:候选", "候选执行者是周岑", "", chapter=3, status="candidate"),
    ])

    assert {item["evidence_kind"] for item in ledger} == {"capability", "attribution", "item"}
    assert all("不得升级" in item["allowed_claim"] for item in ledger)
    assert all(item["subject"] != "候选" for item in ledger)


def test_v8_compact_handoff_drops_transition_provenance_noise():
    handoff = ChapterHandoff(
        previous_chapter=3,
        exact_ending="结尾" * 1000,
        item_state_ledger=[{
            "memory_key": "world_rule:R2",
            "current_state": "封存",
            "transitions": [{"chapter": 1, "operation": "open"}],
            "source_ref": "chapter:1:extractor",
        }],
        evidence_state_ledger=[{"evidence_kind": "capability", "proposition": "只返回历史回执"}],
    )
    compact = handoff.to_compact_prompt(8000)
    assert "transitions" not in compact
    assert "source_ref" not in compact
    assert "evidence_states" in compact
    assert json.loads(compact)["evidence_states"]


def test_quality_gate_requires_all_seven_dimensions():
    evaluations = {
        dimension: {"score": 9, "reason": "evidence"}
        for dimension in (
            "plot_progression",
            "character_portrayal",
            "world_consistency",
            "writing_quality",
            "logical_coherence",
            "chapter_continuity",
            "foreshadowing_payoff",
        )
    }
    summary = quality_summary(evaluations)
    assert summary["complete"] is True
    assert meets_quality_gate(summary) is True


def test_long_form_research_editor_schema_requires_continuity_scores():
    from agents.writing_schemas import EditorResearchResponse

    payload = {
        "decision": "proceed",
        "edited_content": "正文",
        "evaluations": {
            "plot_progression": {"score": 9, "reason": "a"},
            "character_portrayal": {"score": 9, "reason": "b"},
            "world_consistency": {"score": 9, "reason": "c"},
            "writing_quality": {"score": 9, "reason": "d"},
            "logical_coherence": {"score": 9, "reason": "e"},
        },
    }
    with pytest.raises(Exception):
        EditorResearchResponse.model_validate(payload)


def test_v19_editor_quality_contract_covers_all_long_form_editor_modes():
    from agents.writing.editor import _apply_long_form_quality_contract

    context = ExperimentContext(
        run_id="run-v19-quality-contract",
        prompt_version="V19",
        variant="quality-contract",
        project_id="project-test",
        chapter_index=1,
        root_dir=".",
    )
    token = activate(context)
    try:
        for template in ("旧五维审阅模板", "旧五维强制精修模板", "旧五维去腔模板"):
            prompt = _apply_long_form_quality_contract(template, "long_webnovel")
            assert "chapter_continuity" in prompt
            assert "foreshadowing_payoff" in prompt
            assert "禁止省略后两项" in prompt
    finally:
        deactivate(token)

    assert _apply_long_form_quality_contract("短篇模板", "zhihu_short") == "短篇模板"


def test_experiment_recorder_can_capture_bootstrap_phase_events(tmp_path):
    context = ExperimentContext(
        run_id="run-bootstrap",
        prompt_version="V3",
        variant="authority-boundary",
        project_id="project-test",
        chapter_index=0,
        root_dir=tmp_path,
    )
    token = activate(context)
    try:
        from services.experiment_recorder import record_event

        record_event("bootstrap_finished", {"status": "continue"})
    finally:
        deactivate(token)

    event = json.loads(
        (tmp_path / "run-bootstrap" / "events" / "events.jsonl")
        .read_text(encoding="utf-8")
        .strip()
    )
    assert event["event"] == "bootstrap_finished"
    assert event["chapter_index"] == 0


def test_process_single_chapter_records_normal_completion_once(monkeypatch, tmp_path):
    async def fake_settings():
        return {"active_provider_id": "provider", "providers": []}

    async def fake_process(*_args, **_kwargs):
        return "ok"

    monkeypatch.setattr(generate_job_runner, "load_settings", fake_settings)
    monkeypatch.setattr(generate_job_runner, "_process_single_chapter", fake_process)
    job = SimpleNamespace(
        params={
            "experiment": {
                "run_id": "run-wrapper-success",
                "prompt_version": "V6",
                "variant": "continuity",
                "root_dir": str(tmp_path),
            }
        },
        status="running",
    )
    novel = SimpleNamespace(id="project-test", status="generating")

    asyncio.run(generate_job_runner.process_single_chapter(None, job, novel, 1))

    events = [
        json.loads(item)
        for item in (tmp_path / "run-wrapper-success" / "events" / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    finished = [event for event in events if event["event"] == "chapter_finished"]
    assert len(finished) == 1
    assert finished[0]["status"] == "completed"
    assert "recording_fallback" not in finished[0]


def test_process_single_chapter_records_exception_once(monkeypatch, tmp_path):
    async def fake_settings():
        return {"active_provider_id": "provider", "providers": []}

    async def fake_process(*_args, **_kwargs):
        raise RuntimeError("test failure")

    monkeypatch.setattr(generate_job_runner, "load_settings", fake_settings)
    monkeypatch.setattr(generate_job_runner, "_process_single_chapter", fake_process)
    job = SimpleNamespace(
        params={
            "experiment": {
                "run_id": "run-wrapper-error",
                "prompt_version": "V6",
                "variant": "continuity",
                "root_dir": str(tmp_path),
            }
        },
        status="running",
    )
    novel = SimpleNamespace(id="project-test", status="generating")

    with pytest.raises(RuntimeError, match="test failure"):
        asyncio.run(generate_job_runner.process_single_chapter(None, job, novel, 1))

    events = [
        json.loads(item)
        for item in (tmp_path / "run-wrapper-error" / "events" / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    finished = [event for event in events if event["event"] == "chapter_finished"]
    assert len(finished) == 1
    assert finished[0]["status"] == "error"


def test_process_single_chapter_records_pause_without_marking_error(monkeypatch, tmp_path):
    async def fake_settings():
        return {"active_provider_id": "provider", "providers": []}

    async def fake_process(*_args, **_kwargs):
        raise generate_job_runner.JobPausedException("paused by user")

    monkeypatch.setattr(generate_job_runner, "load_settings", fake_settings)
    monkeypatch.setattr(generate_job_runner, "_process_single_chapter", fake_process)
    job = SimpleNamespace(
        params={
            "experiment": {
                "run_id": "run-wrapper-paused",
                "prompt_version": "V12",
                "variant": "continuity",
                "root_dir": str(tmp_path),
            }
        },
        status="paused",
    )
    novel = SimpleNamespace(id="project-test", status="paused")

    with pytest.raises(generate_job_runner.JobPausedException, match="paused by user"):
        asyncio.run(generate_job_runner.process_single_chapter(None, job, novel, 1))

    events = [
        json.loads(item)
        for item in (tmp_path / "run-wrapper-paused" / "events" / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    finished = [event for event in events if event["event"] == "chapter_finished"]
    assert len(finished) == 1
    assert finished[0]["status"] == "paused"


def test_v5_editor_policy_accepts_a_complete_edited_result():
    context = ExperimentContext(
        run_id="run-policy",
        prompt_version="V5",
        variant="retry-policy",
        project_id="project-test",
        chapter_index=1,
        root_dir=".",
    )
    token = activate(context)
    try:
        decision = resolve_editor_decision_from_result(
            {"evaluations": {"writing_quality": {"score": 7}, "edited_content": "完整正文"}},
            rewrite_count=0,
        )
    finally:
        deactivate(token)

    assert decision == "proceed"


def test_v5_editor_policy_rewrites_only_for_explicit_hard_issue():
    context = ExperimentContext(
        run_id="run-policy-hard",
        prompt_version="V5",
        variant="retry-policy",
        project_id="project-test",
        chapter_index=1,
        root_dir=".",
    )
    token = activate(context)
    try:
        decision = resolve_editor_decision_from_result(
            {
                "decision": "rewrite",
                "raw_issues": [{"category": "timeline", "severity": "block", "description": "硬冲突"}],
            },
            rewrite_count=0,
        )
    finally:
        deactivate(token)

    assert decision == "rewrite"


def test_v5_retry_policy_requires_structural_evidence():
    local_issue = {
        "passed": False,
        "errors": ["措辞重复"],
        "hard_issues": [{"category": "style", "description": "局部措辞重复"}],
    }
    hard_issue = {
        "passed": False,
        "errors": ["时间线冲突"],
        "hard_issues": [{
            "category": "timeline",
            "error_type": "时间线矛盾",
            "description": "第2章提前出现尚未获得的证据",
            "evidence": "正文片段",
            "conflicts_with": "第1章交接包",
            "fix_suggestion": "改为调查动作",
        }],
    }

    assert requires_content_retry(local_issue) is False
    assert requires_content_retry(hard_issue) is True
    details = validation_errors_text(hard_issue)
    assert "正文片段" in details
    assert "第1章交接包" in details
    assert "改为调查动作" in details


def test_v20_does_not_retry_local_evidence_surface_wording_issue():
    context = ExperimentContext(
        run_id="v20-retry-policy",
        prompt_version="V20",
        variant="low-retry-state",
        project_id="project",
        chapter_index=1,
        root_dir=Path("."),
    )
    token = activate(context)
    try:
        result = {
            "passed": False,
            "hard_issues": [{
                "category": "consistency",
                "error_type": "其他",
                "description": "来源字段未登记完整，证据清单不完整，建议补充证明范围",
            }],
        }
        assert requires_content_retry(result) is False
    finally:
        deactivate(token)


def test_v25_is_recognized_as_a_prompt_version():
    context = ExperimentContext(
        run_id="v25-version",
        prompt_version="V25",
        variant="artifact-boundary",
        project_id="project",
        chapter_index=1,
        root_dir=Path("."),
    )
    token = activate(context)
    try:
        assert prompt_version_at_least("V24") is True
        assert prompt_version_at_least("V25") is True
    finally:
        deactivate(token)


def test_v29_is_recognized_as_a_prompt_version():
    context = ExperimentContext(
        run_id="v29-version",
        prompt_version="V29",
        variant="compact-narrative",
        project_id="project",
        chapter_index=1,
        root_dir=Path("."),
    )
    token = activate(context)
    try:
        assert prompt_version_at_least("V28") is True
        assert prompt_version_at_least("V29") is True
    finally:
        deactivate(token)


def test_v31_is_recognized_as_a_prompt_version():
    context = ExperimentContext(
        run_id="v31-version",
        prompt_version="V31",
        variant="evidence-ordered-continuity",
        project_id="project",
        chapter_index=1,
        root_dir=Path("."),
    )
    token = activate(context)
    try:
        assert prompt_version_at_least("V30") is True
        assert prompt_version_at_least("V31") is True
    finally:
        deactivate(token)


def test_v32_is_recognized_as_a_prompt_version():
    context = ExperimentContext(
        run_id="v32-version",
        prompt_version="V32",
        variant="prompt-surface",
        project_id="project",
        chapter_index=1,
        root_dir=Path("."),
    )
    token = activate(context)
    try:
        assert prompt_version_at_least("V31") is True
        assert prompt_version_at_least("V32") is True
    finally:
        deactivate(token)


def test_v33_is_recognized_as_a_prompt_version():
    context = ExperimentContext(
        run_id="v33-version",
        prompt_version="V33",
        variant="memory-update-protocol",
        project_id="project",
        chapter_index=1,
        root_dir=Path("."),
    )
    token = activate(context)
    try:
        assert prompt_version_at_least("V32") is True
        assert prompt_version_at_least("V33") is True
    finally:
        deactivate(token)


def test_v34_is_recognized_as_a_prompt_version():
    context = ExperimentContext(
        run_id="v34-version",
        prompt_version="V34",
        variant="context-ownership-current-state",
        project_id="project",
        chapter_index=1,
        root_dir=Path("."),
    )
    token = activate(context)
    try:
        assert prompt_version_at_least("V33") is True
        assert prompt_version_at_least("V34") is True
    finally:
        deactivate(token)


def test_v35_is_recognized_as_a_prompt_version():
    context = ExperimentContext(
        run_id="v35-version",
        prompt_version="V35",
        variant="writer-execution-brief",
        project_id="project",
        chapter_index=1,
        root_dir=Path("."),
    )
    token = activate(context)
    try:
        assert prompt_version_at_least("V34") is True
        assert prompt_version_at_least("V35") is True
    finally:
        deactivate(token)


def test_v36_is_recognized_as_a_prompt_version():
    context = ExperimentContext(
        run_id="v36-version",
        prompt_version="V36",
        variant="writer-recording-commitment",
        project_id="project",
        chapter_index=1,
        root_dir=Path("."),
    )
    token = activate(context)
    try:
        assert prompt_version_at_least("V35") is True
        assert prompt_version_at_least("V36") is True
    finally:
        deactivate(token)


def test_v37_is_recognized_as_a_prompt_version():
    context = ExperimentContext(
        run_id="v37-version",
        prompt_version="V37",
        variant="writer-observation-boundary",
        project_id="project",
        chapter_index=1,
        root_dir=Path("."),
    )
    token = activate(context)
    try:
        assert prompt_version_at_least("V36") is True
        assert prompt_version_at_least("V37") is True
    finally:
        deactivate(token)


def test_v38_is_recognized_as_a_prompt_version():
    context = ExperimentContext(
        run_id="v38-version",
        prompt_version="V38",
        variant="scene-motion",
        project_id="project",
        chapter_index=1,
        root_dir=Path("."),
    )
    token = activate(context)
    try:
        assert prompt_version_at_least("V37") is True
        assert prompt_version_at_least("V38") is True
    finally:
        deactivate(token)


def test_v40_is_recognized_as_a_prompt_version():
    context = ExperimentContext(
        run_id="v40-version",
        prompt_version="V40",
        variant="terminal-state-boundary",
        project_id="project",
        chapter_index=1,
        root_dir=Path("."),
    )
    token = activate(context)
    try:
        assert prompt_version_at_least("V39") is True
        assert prompt_version_at_least("V40") is True
    finally:
        deactivate(token)


def test_v41_is_recognized_as_a_prompt_version():
    context = ExperimentContext(
        run_id="v41-version",
        prompt_version="V41",
        variant="narrative-escalation",
        project_id="project",
        chapter_index=1,
        root_dir=Path("."),
    )
    token = activate(context)
    try:
        assert prompt_version_at_least("V40") is True
        assert prompt_version_at_least("V41") is True
    finally:
        deactivate(token)


def test_v42_is_recognized_as_a_prompt_version():
    context = ExperimentContext(
        run_id="v42-version",
        prompt_version="V42",
        variant="authority-locked-progression",
        project_id="project",
        chapter_index=1,
        root_dir=Path("."),
    )
    token = activate(context)
    try:
        assert prompt_version_at_least("V41") is True
        assert prompt_version_at_least("V42") is True
    finally:
        deactivate(token)


def test_v40_soft_contract_alignment_does_not_retry_writer(tmp_path):
    context = ExperimentContext(
        run_id="v40-soft-contract",
        prompt_version="V40",
        variant="terminal-state-boundary",
        project_id="project",
        chapter_index=2,
        root_dir=tmp_path,
    )
    issue = {
        "category": "consistency",
        "error_type": "其他",
        "description": "契约对章节结尾位置存在轻微表述歧义，但不构成硬冲突。",
        "fix_suggestion": "统一章节结尾状态。",
    }
    token = activate(context)
    try:
        assert is_soft_contract_alignment_issue(issue) is True
        assert requires_content_retry({"passed": False, "hard_issues": [issue]}) is False
        hard_issue = {
            **issue,
            "description": "正文与已接受事实冲突，且契约对章节结尾位置存在轻微表述歧义。",
        }
        assert is_soft_contract_alignment_issue(hard_issue) is False
        assert requires_content_retry({"passed": False, "hard_issues": [hard_issue]}) is True
    finally:
        deactivate(token)


def test_await_io_work_times_out_and_releases_waiter(monkeypatch):
    """io executor 挂死时等待方有界放行:超时返回 None,不无限排队。"""
    import time as _time

    from services import experiment_recorder as er

    monkeypatch.setattr(er._io, "_IO_AWAIT_TIMEOUT_SECONDS", 0.05)

    async def _hang():
        await asyncio.sleep(5)
        return "done-late"

    async def _run():
        started = _time.monotonic()
        result = await er._await_io_work(_hang())
        return result, _time.monotonic() - started

    result, elapsed = asyncio.run(_run())
    assert result is None  # 超时放行:等待方拿到 None 而不是陪挂 5s
    assert elapsed < 1.0


def test_await_io_work_shield_keeps_work_running_after_timeout(monkeypatch):
    """超时后 shield 保证后台写不被取消:工作延迟完成而非丢弃。"""
    from services import experiment_recorder as er

    monkeypatch.setattr(er._io, "_IO_AWAIT_TIMEOUT_SECONDS", 0.05)
    completed = []

    async def _slow_write():
        await asyncio.sleep(0.15)
        completed.append("written")
        return "ok"

    async def _run():
        result = await er._await_io_work(_slow_write())
        await asyncio.sleep(0.2)  # 等后台写跑完再收尾
        return result

    assert asyncio.run(_run()) is None
    assert completed == ["written"]  # 放行的是"等待",不是"写"本身


def test_adeactivate_flush_survives_cancellation(monkeypatch):
    """rewrite 双重取消打断 adeactivate 的等待时,shield 保证后台落盘不丢。"""
    import concurrent.futures
    import time as _time

    from services import experiment_recorder as er

    completed = []

    def _slow_flush():
        _time.sleep(0.15)
        completed.append("flushed")

    monkeypatch.setattr(er._context, "_flush_pending_writes", _slow_flush)
    # 一个永不完成的排队 future,让 adeactivate 判定"有排队写盘"走 flush 路径
    pending = concurrent.futures.Future()
    er._pending_writes.add(pending)
    try:

        async def _run():
            # activate 与 adeactivate 必须在同一任务里(与真实 runner 路径一致),
            # 分开 create_task 会拷贝 context 导致 token 跨 Context。
            async def _worker():
                token = er.activate(None)
                await er.adeactivate(token)

            task = asyncio.create_task(_worker())
            await asyncio.sleep(0.02)  # 等任务进入 flush 等待
            task.cancel()  # 模拟取消风暴打断 finally 里的 await
            with pytest.raises(asyncio.CancelledError):
                await task
            await asyncio.sleep(0.3)  # 等后台 flush 完成

        asyncio.run(_run())
    finally:
        er._pending_writes.discard(pending)

    assert completed == ["flushed"]
