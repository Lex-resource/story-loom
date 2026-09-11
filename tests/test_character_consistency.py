from types import SimpleNamespace

from models.characters import CharacterCard
from services.character_manifest_service import build_manifest_data
from services.character_schemas import normalize_current_state
from services.character_constants import normalize_character_status
from services.character_card_service import stable_card_data_for_update
from services.character_card_serialization import diff_values, merge_card_relationships
from services.character_types import CharacterCardUpdate
from agents.providers import resolve_backup_provider
from agents.usage import agent_usage_payload
from services.validation_constants import is_fact_conflict_issue
from worker_support.generation_validator_policy import has_fact_conflict


def test_normalize_current_state_collapses_aliases():
    state = normalize_current_state({
        "位置": "旧地点",
        "current_location": "新地点",
        "等级": "凡境",
        "cultivation": "灵境一层",
    })

    assert state == {"location": "新地点", "cultivation": "灵境一层"}


def test_extractor_cannot_update_stable_card_data():
    extractor_update = CharacterCardUpdate(
        character_name="青冥",
        card_data_updates={"personality": {"性格": "冲动"}},
    )
    initial_update = extractor_update.model_copy(update={"card_data_authority": "initial"})

    assert stable_card_data_for_update(extractor_update) == {}
    assert stable_card_data_for_update(initial_update) == {
        "personality": {"性格": "冲动"}
    }


def test_character_serialization_helpers_keep_sparse_diffs_and_merge_relationships():
    fields, patch = diff_values({"state": {"mood": "平静"}}, {"state": {"mood": "紧张"}})
    assert fields == ["state.mood"]
    assert patch["state.mood"] == {"old": "平静", "new": "紧张"}
    merged = merge_card_relationships(
        [{"target_name": "林默", "relation_type": "同事", "trust": "低"}],
        [{"target_name": "林默", "relation_type": "同事", "trust": "中"}],
    )
    assert merged == [{"target_name": "林默", "relation_type": "同事", "trust": "中"}]


def test_character_status_normalizes_model_and_legacy_values():
    assert normalize_character_status("已销毁") == "deceased"
    assert normalize_character_status("alive") == "active"
    assert normalize_character_status("未知模型状态") is None


def test_character_update_drops_unknown_status_and_normalizes_known_status():
    assert CharacterCardUpdate(character_name="甲", status="已销毁").status == "deceased"
    assert CharacterCardUpdate(character_name="乙", status="未知模型状态").status is None


def test_manifest_reads_chinese_card_fields():
    card = CharacterCard(
        name="青冥",
        card_data={
            "identity": {"身份": "护道者"},
            "personality": {"性格": "古怪毒舌"},
            "growth_route": {"当前阶段": "观察者"},
        },
        current_state={"位置": "藏经阁", "目标": "引导叶尘"},
    )

    manifest = build_manifest_data(card)

    assert "护道者" in manifest["role_summary"]
    assert "古怪毒舌" in manifest["personality_summary"]
    assert manifest["current_location"] == "藏经阁"
    assert manifest["current_goal"] == "引导叶尘"


def test_backup_provider_is_explicit_opt_in():
    settings = {
        "active_provider_id": "primary",
        "providers": [
            {"id": "primary", "name": "主模型", "model": "main"},
            {"id": "other", "name": "其他模型", "model": "other"},
        ],
    }

    switched, _ = resolve_backup_provider(settings, "url", "key", "main")
    assert switched is False

    settings["backup_provider_id"] = "other"
    switched, backup = resolve_backup_provider(settings, "url", "key", "main")
    assert switched is True
    assert backup.model == "other"


def test_usage_prefers_model_used_by_last_call():
    agent = SimpleNamespace(
        last_input_tokens=1,
        last_output_tokens=2,
        last_model_name="fallback-model",
        model="configured-model",
    )

    assert agent_usage_payload(agent, "project", 1, "writer")["model_name"] == "fallback-model"


def test_fact_conflicts_are_always_blocking():
    issue = {
        "category": "timeline",
        "error_type": "时间线矛盾",
        "severity": "warning",
    }

    assert is_fact_conflict_issue(issue)
    assert has_fact_conflict({"hard_issues": [issue]})
