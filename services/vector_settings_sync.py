from __future__ import annotations

from services.vector_chroma import get_or_create_collection, run_with_chroma, upsert_to_collection
from services.vector_constants import VECTOR_COLLECTION_PREFIX, VECTOR_SOURCE_SETTING
from services.vector_settings_index import build_setting_entries, settings_content_hash


import logging

logger = logging.getLogger(__name__)

_settings_index_hashes: dict[str, str] = {}


def reset_settings_index_cache() -> None:
    _settings_index_hashes.clear()


def invalidate_settings_index_cache(project_id: str) -> None:
    _settings_index_hashes.pop(project_id, None)


async def sync_settings_index(
    project_id: str,
    character_state: str,
    world_state: str,
    foreshadowing: str,
    plot_threads: str,
    *,
    force: bool = False,
) -> bool:
    content_hash = settings_content_hash(
        character_state, world_state, foreshadowing, plot_threads
    )
    if not force and _settings_index_hashes.get(project_id) == content_hash:
        return False

    collection_name = f"{VECTOR_COLLECTION_PREFIX}{project_id}"
    entries = build_setting_entries(
        character_state, world_state, foreshadowing, plot_threads
    )
    desired_ids = {entry[0] for entry in entries}

    existing_ids: set[str] = set()

    def get_existing():
        collection = get_or_create_collection(collection_name)
        return collection.get(where={"source": VECTOR_SOURCE_SETTING}, include=[])

    try:
        existing = await run_with_chroma(get_existing)
        existing_ids = set(existing.get("ids") or [])
    except Exception as exc:
        # A failed read means we cannot prove that stale setting vectors were
        # removed. Do not advance the in-process hash cache in that case.
        logger.warning(f"[VectorStore] Failed to list setting ids: {exc}")
        raise

    to_delete = list(existing_ids - desired_ids)
    if to_delete:
        try:
            def delete_orphans():
                collection = get_or_create_collection(collection_name)
                collection.delete(ids=to_delete)

            await run_with_chroma(delete_orphans)
        except Exception as exc:
            logger.warning(f"[VectorStore] Failed to delete orphan setting ids: {exc}")
            raise

    if entries:
        ids, docs, metas = zip(*entries)
        await upsert_to_collection(
            collection_name, list(ids), list(docs), list(metas)
        )

    _settings_index_hashes[project_id] = content_hash
    return True


async def index_settings(
    project_id: str,
    character_state: str,
    world_state: str,
    foreshadowing: str,
    plot_threads: str,
) -> None:
    try:
        await sync_settings_index(
            project_id, character_state, world_state, foreshadowing, plot_threads
        )
    except Exception as exc:
        logger.error(f"[VectorStore ERROR] index_settings failed: {exc}")
