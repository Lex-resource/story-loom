from types import SimpleNamespace
from uuid import UUID, uuid4

from agents.context_bundle import build_agent_context_bundle
from services.narrative_index import (
    NarrativeProjection,
    build_narrative_projections,
    deterministic_narrative_id,
    format_narrative_context,
)


def test_build_narrative_projections_is_deterministic_and_links_foreshadowing():
    outline = {
        "stage": "白塔调查",
        "plotline": "主线",
        "summary": "林默确认设备只返回历史回执。",
        "segments": ["抵达白塔", "读取回执"],
        "key_events": ["林默抵达白塔", "设备返回历史回执"],
        "related_foreshadowing": [{"name": "sender_identity", "description": "发送者身份仍未知"}],
    }

    first = build_narrative_projections(chapter_index=2, outline=outline)
    second = build_narrative_projections(chapter_index=2, outline=outline)

    assert first == second
    assert {item.entry_type for item in first} == {
        "stage_summary",
        "story_segment",
        "story_event",
        "foreshadowing_link",
    }
    link = next(item for item in first if item.entry_type == "foreshadowing_link")
    assert link.relation == "foreshadowing_to_event"
    assert link.target_key == "chapter:2:event:1"


def test_narrative_id_is_stable_for_same_scope_and_content():
    project_id = UUID("11111111-1111-1111-1111-111111111111")
    args = {
        "branch_id": None,
        "storyline_id": "main",
        "entry_type": "story_event",
        "entry_key": "chapter:2:event:1",
        "content_hash": "a" * 64,
    }
    assert deterministic_narrative_id(project_id, **args) == deterministic_narrative_id(project_id, **args)
    assert deterministic_narrative_id(project_id, **args) != deterministic_narrative_id(
        project_id, **{**args, "content_hash": "b" * 64}
    )


def test_format_narrative_context_excludes_candidates_and_obeys_budget():
    entries = [
        SimpleNamespace(status="candidate", is_active=True, entry_type="story_event", entry_key="candidate", relation="", content="不应出现"),
        SimpleNamespace(status="accepted", is_active=True, entry_type="story_event", entry_key="accepted", relation="event_to_chapter", content="已确认事件"),
    ]
    rendered = format_narrative_context(entries, max_chars=100)
    assert "已确认事件" in rendered
    assert "不应出现" not in rendered


def test_format_narrative_context_filters_role_irrelevant_segments_and_deduplicates():
    entries = [
        SimpleNamespace(status="accepted", is_active=True, entry_type="story_segment", entry_key="segment", relation="segment_to_stage", content="段落细节"),
        SimpleNamespace(status="accepted", is_active=True, entry_type="story_event", entry_key="event:1", relation="event_to_chapter", content="重复事件"),
        SimpleNamespace(status="accepted", is_active=True, entry_type="story_event", entry_key="event:2", relation="event_to_chapter", content="重复事件"),
    ]
    rendered = format_narrative_context(entries, agent_type="writer")
    assert "段落细节" not in rendered
    assert rendered.count("重复事件") == 1


def test_context_bundle_exposes_narrative_projection_only_when_present():
    empty = build_agent_context_bundle({"project_id": str(uuid4()), "chapter_index": 2}, agent_type="writer")
    assert empty.get("narrative_index") is None

    bundle = build_agent_context_bundle(
        {
            "project_id": "project",
            "chapter_index": 2,
            "narrative_index_context": "- story_event:chapter:2:event:1: 已确认事件",
            "context_sources": {
                "narrative_index_context": {
                    "source_ref": "narrative_index:accepted",
                    "source_chapter": 2,
                    "authority": "published_projection",
                }
            },
        },
        agent_type="writer",
    )
    section = bundle.get("narrative_index")
    assert section is not None
    assert section.sources[0].authority == "published_projection"


def test_projection_dataclass_preserves_candidate_status_for_future_proposals():
    projection = NarrativeProjection(
        entry_type="story_event",
        entry_key="candidate:event",
        content="待核对事件",
        status="candidate",
        authority="generated",
    )
    assert projection.status == "candidate"
    assert projection.authority == "generated"
