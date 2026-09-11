"""Durable vector projection for persisted character manifests."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.characters import CharacterCard, CharacterManifest
from models.novel import VectorOutbox
from services.pipeline_types import VectorOutboxStatus
from services.vector_settings_index import build_character_manifest_vector_item


async def enqueue_character_manifest_vectors(
    db: AsyncSession,
    cards: Iterable[CharacterCard],
    *,
    chapter_index: int | None = None,
) -> int:
    unique_cards = {card.id: card for card in cards if card is not None}
    if not unique_cards:
        return 0

    result = await db.execute(
        select(CharacterManifest).where(
            CharacterManifest.character_id.in_(list(unique_cards))
        )
    )
    manifests = list(result.scalars().all())
    items = [
        build_character_manifest_vector_item(
            str(manifest.data.get("name") or unique_cards[manifest.character_id].name),
            manifest.data or {},
        )
        for manifest in manifests
    ]
    if not items:
        return 0

    project_id = next(iter(unique_cards.values())).project_id
    db.add(
        VectorOutbox(
            project_id=project_id,
            chapter_index=chapter_index,
            payload={"items": items},
            status=VectorOutboxStatus.PENDING,
        )
    )
    await db.flush()
    return len(items)
