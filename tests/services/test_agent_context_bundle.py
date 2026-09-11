import json

from agents.context_bundle import (
    AgentContextBundle,
    ContextSection,
    ContextSource,
    build_agent_context_bundle,
)
from agents.pipeline_context import PipelineContext


def test_context_section_keeps_provenance_and_serializes_cleanly():
    section = ContextSection(
        section_id="chapter_handoff",
        title="上一章交接",
        content="林默停在门前。",
        sources=(
            ContextSource(
                source_ref="chapter:2:handoff",
                source_chapter=2,
                authority="accepted",
                version=3,
            ),
        ),
    )

    payload = section.to_dict()

    assert payload["section_id"] == "chapter_handoff"
    assert payload["sources"][0]["source_ref"] == "chapter:2:handoff"
    assert payload["sources"][0]["authority"] == "accepted"
    assert json.loads(json.dumps(payload, ensure_ascii=False))["sources"]


def test_bundle_selects_different_sections_for_planner_and_writer():
    memory = {
        "agent_type": "planner",
        "global_outline": {"title": "总纲"},
        "chapter_outline": {"title": "当前章"},
        "character_manifest_context": "角色卡",
        "novel_memory_context": "主线和伏笔",
        "chapter_handoff_context": "上一章结尾",
        "character_card_context": "角色当前状态",
        "vector_context": "向量召回",
    }

    planner = build_agent_context_bundle(memory, agent_type="planner")
    writer = build_agent_context_bundle(memory, agent_type="writer")

    assert planner.agent_type == "planner"
    assert planner.section_ids == (
        "global_outline",
        "character_manifest",
        "novel_memory",
        "chapter_handoff",
    )
    assert writer.section_ids == (
        "chapter_outline",
        "character_card",
        "novel_memory",
        "chapter_handoff",
        "vector_context",
    )
    assert "character_card" not in planner.section_ids
    assert "character_manifest" not in writer.section_ids


def test_bundle_render_is_bounded_without_mutating_source_sections():
    bundle = AgentContextBundle(
        agent_type="writer",
        project_id="project",
        chapter_index=4,
        sections=(
            ContextSection(
                section_id="novel_memory",
                title="分层记忆",
                content="事实" * 1000,
            ),
        ),
    )

    rendered = bundle.render(max_chars=180)

    assert len(rendered) <= 180
    assert "【分层记忆】" in rendered
    assert len(bundle.sections[0].content) == 2000


def test_pipeline_context_from_memory_keeps_flat_compatibility_and_bundle():
    context = PipelineContext.from_memory(
        "project",
        3,
        {
            "agent_type": "validator",
            "novel_format": "long_webnovel",
            "chapter_handoff_context": "上一章结尾",
            "novel_memory_context": "已确认事实",
            "world_state": "硬规则",
            "context_sources": {
                "novel_memory_context": {
                    "source_ref": "novel_memory:recall",
                    "authority": "accepted_with_candidate_boundary",
                },
            },
        },
    )

    assert context.novel_memory_context == "已确认事实"
    assert context.context_bundle is not None
    assert context.context_bundle.agent_type == "validator"
    assert context.context_bundle.get("chapter_handoff").content == "上一章结尾"
    assert context.context_bundle.get("novel_memory").content == "已确认事实"
    assert context.get_context_bundle().get("novel_memory").sources[0].authority == "accepted_with_candidate_boundary"
