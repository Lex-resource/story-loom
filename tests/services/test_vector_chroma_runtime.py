import pytest

import services.vector_chroma as vector_chroma
from services.issues import _normalize_summaries
from services import vector_settings_sync


def test_normalize_summaries_accepts_array_and_string_items():
    result = _normalize_summaries([
        {"summary": "人物动机前后不一致", "category": "consistency"},
        "时间线需要继续核对",
    ])

    assert result[0]["summary"] == "人物动机前后不一致"
    assert result[1] == {
        "summary": "时间线需要继续核对",
        "category": "consistency",
        "severity": "medium",
    }


def test_sanitize_metadata_omits_nulls_and_serializes_nested_values():
    result = vector_chroma._sanitize_metadata({
        "source": "extractor",
        "chapter_index": 2,
        "optional": None,
        "characters": ["林默", "苏晚"],
    })

    assert result["source"] == "extractor"
    assert result["chapter_index"] == 2
    assert "optional" not in result
    assert result["characters"] == '["林默", "苏晚"]'


@pytest.mark.asyncio
async def test_empty_collection_check_does_not_initialize_embedding(monkeypatch):
    class EmptyCollection:
        def count(self):
            return 0

    class Client:
        def get_collection(self, _name):
            return EmptyCollection()

    monkeypatch.setattr(vector_chroma, "get_client", lambda: Client())
    assert await vector_chroma.has_collection_documents("project-empty") is False


@pytest.mark.asyncio
async def test_vector_write_uses_database_provider_embedding_without_static_env(monkeypatch):
    captured = {}

    async def fake_embeddings(texts):
        assert texts == ["事实内容"]
        return [[0.1, 0.2]], 7

    async def fake_log(*args, **kwargs):
        return None

    class Collection:
        def upsert(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(vector_chroma, "get_embeddings_from_api", fake_embeddings)
    monkeypatch.setattr(vector_chroma, "log_embedding_tokens", fake_log)
    monkeypatch.setattr(vector_chroma, "get_or_create_collection", lambda _name: Collection())

    await vector_chroma.upsert_to_collection(
        "project-test",
        ["atom-1"],
        ["事实内容"],
        [{"chapter_index": 1, "source": None}],
    )

    assert captured["embeddings"] == [[0.1, 0.2]]
    assert captured["metadatas"] == [{"chapter_index": 1}]


@pytest.mark.asyncio
async def test_settings_index_does_not_cache_hash_when_orphan_delete_fails(monkeypatch):
    project_id = "project-settings"
    vector_settings_sync.reset_settings_index_cache()

    async def run_inline(fn, *_args, **_kwargs):
        return fn()

    monkeypatch.setattr(vector_settings_sync, "run_with_chroma", run_inline)

    class Collection:
        def get(self, **_kwargs):
            return {"ids": ["stale-setting"]}

        def delete(self, **_kwargs):
            raise RuntimeError("delete failed")

    monkeypatch.setattr(
        vector_settings_sync,
        "get_or_create_collection",
        lambda _name: Collection(),
    )

    with pytest.raises(RuntimeError):
        await vector_settings_sync.sync_settings_index(
            project_id, "", "- rule", "", ""
        )

    assert project_id not in vector_settings_sync._settings_index_hashes


@pytest.mark.asyncio
async def test_chroma_delete_where_propagates_unexpected_errors(monkeypatch):
    class Collection:
        def delete(self, **_kwargs):
            raise RuntimeError("disk failure")

    class Client:
        def get_collection(self, _name):
            return Collection()

    monkeypatch.setattr(vector_chroma, "get_client", lambda: Client())

    with pytest.raises(RuntimeError, match="disk failure"):
        await vector_chroma.delete_collection_where("project-test", {"chapter_index": 2})
