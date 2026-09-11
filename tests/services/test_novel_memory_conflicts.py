from types import SimpleNamespace
import uuid

import pytest
from sqlalchemy.dialects import postgresql

from services.novel_memory_atoms import (
    AtomCandidateReview,
    _is_safe_atom_progression,
    atom_conflict_issue,
    promote_reviewed_atom_candidates,
    reject_atom_candidates,
    reject_conflicting_atom_candidates,
)
from services.novel_memory_conflicts import (
    AUTO_EXTRACTOR_REVIEWER,
    build_conflict_hash,
    is_hard_extractor_issue,
    record_hard_conflicts,
    resolve_conflicts_automatically,
)


class _ConflictSession:
    def __init__(self):
        self.statements = []
        self.conflict = SimpleNamespace(id=uuid.uuid4())

    async def execute(self, statement):
        self.statements.append(statement)

    async def scalar(self, _statement):
        return self.conflict


def _atom(
    *,
    status="candidate",
    statement="新事实",
    operation="upsert",
    atom_type="world_rule",
    memory_key="world_rule:门禁",
    authority="generated",
    payload=None,
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        branch_id=None,
        storyline_id="main",
        memory_key=memory_key,
        atom_type=atom_type,
        source_ref="chapter:2:extractor",
        status=status,
        authority=authority,
        statement=statement,
        data={"operation": operation, "data": payload or {}},
    )


def test_soft_extractor_notes_do_not_enter_hard_conflict_queue():
    assert not is_hard_extractor_issue(
        {"severity": "high", "category": "foreshadowing", "description": "动机不明，待后续确认"}
    )
    assert is_hard_extractor_issue(
        {"severity": "high", "category": "frozen_fact", "description": "与已发布事实直接矛盾"}
    )


def test_conflicting_candidate_is_not_promoted():
    candidate = _atom()
    accepted = _atom(status="accepted", statement="旧事实")
    review = AtomCandidateReview(candidate, accepted, True)

    assert atom_conflict_issue(review)["conflicts_with"] == "旧事实"
    assert promote_reviewed_atom_candidates([review]) == []
    assert candidate.status == "candidate"


def test_automatic_review_rejects_conflicting_candidates_without_overwrite():
    candidate = _atom()
    accepted = _atom(status="accepted", statement="旧事实")
    review = AtomCandidateReview(candidate, accepted, True)

    rejected = reject_conflicting_atom_candidates([review])

    assert rejected == [candidate]
    assert candidate.status == "rejected"
    assert accepted.status == "accepted"


def test_automatic_review_can_reject_an_entire_unmapped_batch():
    candidates = [_atom(), _atom(memory_key="world_rule:门禁2")]

    rejected = reject_atom_candidates(candidates)

    assert rejected == candidates
    assert all(atom.status == "rejected" for atom in candidates)


def test_automatic_review_resolves_conflict_records():
    conflict = SimpleNamespace(
        status="open",
        resolved_by=None,
        resolved_at=None,
    )

    resolved = resolve_conflicts_automatically([conflict])

    assert resolved == [conflict]
    assert conflict.status == "resolved"
    assert conflict.resolved_by == AUTO_EXTRACTOR_REVIEWER
    assert conflict.resolved_at is not None
    assert conflict.resolved_at.tzinfo is None


def test_explicit_progress_can_supersede_previous_accepted_atom():
    candidate = _atom(operation="resolve")
    accepted = _atom(status="accepted", statement="旧事实")
    review = AtomCandidateReview(candidate, accepted, False)

    assert promote_reviewed_atom_candidates([review]) == [candidate]
    assert candidate.status == "accepted"
    assert accepted.status == "superseded"


def test_generated_character_merge_is_treated_as_dynamic_progress():
    candidate = _atom(
        statement="本章人物状态",
        operation="merge",
        atom_type="character_state",
        memory_key="character:林默",
        payload={"attributes": {"current_state": "仍在调查"}},
    )
    accepted = _atom(
        status="accepted",
        statement="上一章人物状态",
        atom_type="character_state",
        memory_key="character:林默",
        payload={"attributes": {"current_state": "刚到现场"}},
    )

    review = AtomCandidateReview(candidate, accepted, False)

    assert promote_reviewed_atom_candidates([review]) == [candidate]
    assert candidate.status == "accepted"
    assert accepted.status == "superseded"


def test_observational_world_rule_merge_is_not_a_hard_conflict():
    candidate = _atom(
        statement="设备新增可观察反馈",
        operation="merge",
        payload={
            "rule_type": "rule",
            "confirmed": True,
            "observed_records": ["新增残缺反馈"],
        },
    )
    accepted = _atom(
        status="accepted",
        statement="设备既有反馈",
        payload={
            "rule_type": "rule",
            "confirmed": True,
            "observed_records": ["既有反馈"],
        },
    )

    review = AtomCandidateReview(candidate, accepted, False)

    assert atom_conflict_issue(review) is None
    assert promote_reviewed_atom_candidates([review]) == [candidate]


def test_display_observation_merge_from_a_real_extractor_shape_is_not_blocked():
    candidate = _atom(
        statement="B-17显示新增分层结构",
        operation="merge",
        payload={
            "rule_type": "confirmed",
            "visible_structure": ["门", "未", "回到白塔"],
            "layout": "可见内容与遮蔽字段分开显示",
            "adjacent_element": "无标注竖向空栏",
            "current_status": "查询后仍保持分层排列",
        },
    )
    accepted = _atom(
        status="accepted",
        statement="B-17存在读取缺损",
        payload={
            "rule_type": "confirmed",
            "visible_fields": ["B-17", "门", "未", "回到白塔"],
            "obscured_fields": ["发送者", "时间"],
            "status": "已调取但读取缺损",
        },
    )

    review = AtomCandidateReview(candidate, accepted, False)

    assert atom_conflict_issue(review) is None
    assert promote_reviewed_atom_candidates([review]) == [candidate]


def test_observation_merge_with_changed_hard_marker_stays_blocked():
    candidate = _atom(
        statement="B-17改变规则类型",
        operation="merge",
        payload={
            "rule_type": "rule",
            "visible_structure": ["门", "未"],
        },
    )
    accepted = _atom(
        status="accepted",
        statement="B-17是确认记录",
        payload={
            "rule_type": "confirmed",
            "visible_fields": ["B-17"],
        },
    )

    review = AtomCandidateReview(candidate, accepted, True)

    assert atom_conflict_issue(review)["conflicts_with"] == "B-17是确认记录"
    assert promote_reviewed_atom_candidates([review]) == []


def test_existing_upsert_without_replacement_marker_stays_blocked():
    candidate = _atom(
        statement="替换后的门禁",
        operation="upsert",
        payload={"rule_type": "rule", "observed_state": "新状态"},
    )
    accepted = _atom(
        status="accepted",
        statement="原门禁",
        payload={"rule_type": "rule", "observed_state": "原状态"},
    )
    review = AtomCandidateReview(candidate, accepted, True)

    assert atom_conflict_issue(review)["conflicts_with"] == "原门禁"
    assert promote_reviewed_atom_candidates([review]) == []


def test_explicit_generated_replacement_is_allowed():
    candidate = _atom(
        statement="明确替换后的门禁",
        operation="merge",
        payload={"replacement": True, "rule_type": "rule", "observed_state": "新状态"},
    )
    accepted = _atom(
        status="accepted",
        statement="原门禁",
        payload={"rule_type": "rule", "observed_state": "原状态"},
    )
    review = AtomCandidateReview(candidate, accepted, False)

    assert promote_reviewed_atom_candidates([review]) == [candidate]


def test_protected_authority_cannot_be_replaced_by_generated_merge():
    candidate = _atom(
        statement="覆盖冻结设定",
        operation="merge",
        atom_type="character_state",
        memory_key="character:林默",
        payload={"attributes": {"current_state": "新状态"}},
    )
    accepted = _atom(
        status="accepted",
        statement="冻结设定",
        atom_type="character_state",
        memory_key="character:林默",
        authority="frozen",
        payload={"attributes": {"current_state": "冻结状态"}},
    )
    review = AtomCandidateReview(candidate, accepted, True)

    assert promote_reviewed_atom_candidates([review]) == []


def test_changed_world_rule_marker_stays_blocked_even_as_progress():
    candidate = _atom(
        statement="改变规则类型",
        operation="append_progress",
        payload={"rule_type": "restriction", "confirmed": True},
    )
    accepted = _atom(
        status="accepted",
        statement="原规则类型",
        payload={"rule_type": "rule", "confirmed": True},
    )
    review = AtomCandidateReview(candidate, accepted, True)

    assert promote_reviewed_atom_candidates([review]) == []


def test_generated_rule_type_alias_is_state_progression_not_conflict():
    candidate = _atom(
        statement="设备状态已演进为熄灭",
        operation="merge",
        payload={
            "rule_type": "rule",
            "confirmed_behavior": "接触门面后停止显示",
        },
    )
    accepted = _atom(
        status="accepted",
        statement="设备可返回历史回执",
        payload={
            "rule_type": "confirmed",
            "displayed_receipt": "门前的人，不是第一个",
        },
    )
    review = AtomCandidateReview(candidate, accepted, False)

    assert _is_safe_atom_progression(candidate, accepted)
    assert atom_conflict_issue(review) is None
    assert promote_reviewed_atom_candidates([review]) == [candidate]


def test_conflict_hash_is_deterministic_and_scope_sensitive():
    project_id = uuid.uuid4()
    issue = {"category": "world_rule", "description": "冲突"}
    first = build_conflict_hash(
        project_id=project_id,
        chapter_index=2,
        source_ref="chapter:2:extractor:conflict",
        issue=issue,
    )
    same = build_conflict_hash(
        project_id=project_id,
        chapter_index=2,
        source_ref="chapter:2:extractor:conflict",
        issue=issue,
    )
    other_chapter = build_conflict_hash(
        project_id=project_id,
        chapter_index=3,
        source_ref="chapter:3:extractor:conflict",
        issue=issue,
    )
    assert first == same
    assert first != other_chapter
    assert len(first) == 64


@pytest.mark.asyncio
async def test_hard_conflict_insert_is_idempotent_shape():
    db = _ConflictSession()
    await record_hard_conflicts(
        db,
        project_id=uuid.uuid4(),
        chapter_index=2,
        issues=[{"category": "frozen_fact", "severity": "high", "description": "冲突"}],
    )

    assert len(db.statements) == 1
    compiled = db.statements[0].compile(dialect=postgresql.dialect())
    assert "ON CONFLICT DO NOTHING" in str(compiled)
    assert compiled.params["status"] == "open"
