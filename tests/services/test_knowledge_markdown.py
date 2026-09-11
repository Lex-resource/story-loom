from services.document_constants import MARKDOWN_DOC_TYPES
from services.knowledge_markdown import (
    knowledge_from_markdown,
    knowledge_to_markdown,
    legacy_json_to_markdown,
)
from services.knowledge_types import CharacterKnowledge, WorldRuleKnowledge


def test_authoring_markdown_doc_types_cover_outline_and_core_settings():
    assert MARKDOWN_DOC_TYPES == (
        "global_outline",
        "act_outline",
        "character_state",
        "world_state",
    )


def test_character_markdown_round_trip_preserves_attributes_and_relationships():
    source = CharacterKnowledge(
        name="林默",
        body="主角，沉默寡言。",
        attributes={
            "身份": "流浪剑客",
            "relationships": [
                {"to": "苏晚", "label": "盟友", "description": "互相救过命"},
            ],
        },
    )

    markdown = knowledge_to_markdown("character_state", [source])
    parsed = knowledge_from_markdown("character_state", markdown)[0]

    assert "## 林默" in markdown
    assert "- **身份**: 流浪剑客" in markdown
    assert parsed.name == source.name
    assert parsed.body == source.body
    assert parsed.attributes["身份"] == "流浪剑客"
    assert parsed.attributes["relationships"] == source.attributes["relationships"]


def test_world_rule_markdown_round_trip_preserves_rule_type_and_attributes():
    source = WorldRuleKnowledge(
        name="境界体系",
        body="修行者通过灵脉晋升。",
        rule_type="rule",
        attributes={"限制": "每次晋升必须闭关"},
    )

    markdown = knowledge_to_markdown("world_state", [source])
    parsed = knowledge_from_markdown("world_state", markdown)[0]

    assert "## 境界体系" in markdown
    assert "- **规则类型**: rule" in markdown
    assert parsed.name == source.name
    assert parsed.body == source.body
    assert parsed.rule_type == "rule"
    assert parsed.attributes["限制"] == "每次晋升必须闭关"


def test_legacy_world_json_is_converted_to_authoring_markdown():
    source = '[{"name": "备用节点", "body": "位于深海。", "rule_type": "location", "attributes": {"chapter": 17}}]'

    markdown = legacy_json_to_markdown("world_state", source)

    assert markdown == "## 备用节点\n\n位于深海。\n\n- **规则类型**: location\n- **chapter**: 17"
