from __future__ import annotations

from typing import Optional

from services.living_docs_parsers import parse_bullet_points, parse_character_state
from services.vector_chroma import (
    add_to_collection,
    get_client,
    get_or_create_collection,
    query_collection,
    reset_chroma_state,
    upsert_to_collection,
)
from services.vector_retrieval import (
    retrieve_setting_context as retrieve_setting_context_with_query,
    search_knowledge_items as search_knowledge_items_with_query,
)
from services.vector_settings_sync import (
    index_settings,
    invalidate_settings_index_cache,
    reset_settings_index_cache,
    sync_settings_index,
)


def reset_vector_store_state() -> None:
    reset_chroma_state()
    reset_settings_index_cache()


async def retrieve_setting_context(
    project_id: str,
    query_text: str,
    character_state_txt: str,
    world_state_txt: str,
    foreshadowing_txt: str,
    plot_threads_txt: str,
    characters_involved_hint: Optional[list[str]] = None,
    protagonist_name: Optional[str] = None,
    current_chapter: Optional[int] = None,
    foreshadowing_items=None,
) -> dict:
    return await retrieve_setting_context_with_query(
        project_id,
        query_text,
        character_state_txt,
        world_state_txt,
        foreshadowing_txt,
        plot_threads_txt,
        query_collection,
        characters_involved_hint=characters_involved_hint,
        protagonist_name=protagonist_name,
        current_chapter=current_chapter,
        foreshadowing_items=foreshadowing_items,
    )


async def search_knowledge_items(project_id: str, query: str, item_type: Optional[str] = None, n: int = 5) -> dict:
    return await search_knowledge_items_with_query(
        project_id, query, query_collection, item_type=item_type, n=n
    )
