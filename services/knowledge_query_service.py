import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select
from models.novel import Novel
from services.knowledge_character_graph import build_character_domain_graph
from services.novel_memory_views import (
    DEFAULT_KNOWLEDGE_VIEW_LIMIT,
    build_foreshadowing_view,
    build_plot_tracks_view,
    build_world_rules_view,
)
from services.community_service import CommunityService

DEFAULT_CHARACTER_GRAPH_LIMIT = 1000
MAX_CHARACTER_GRAPH_LIMIT = 5000


def _bounded_character_graph_limit(limit: int) -> int:
    return min(max(int(limit), 1), MAX_CHARACTER_GRAPH_LIMIT)


def _project_uuid(project_id: uuid.UUID | str) -> uuid.UUID:
    return project_id if isinstance(project_id, uuid.UUID) else uuid.UUID(project_id)


async def get_community_summary(project_id: uuid.UUID, db: AsyncSession):
    graph = await get_character_graph(project_id, db)
    project_uuid = _project_uuid(project_id)
    novel_res = await db.execute(select(Novel).where(Novel.id == project_uuid))
    novel = novel_res.scalar_one_or_none()
    novel_format = novel.novel_format if novel else None
    return await CommunityService.generate_community_summaries(graph["nodes"], graph["edges"], novel_format)

async def get_character_graph(
    project_id: uuid.UUID,
    db: AsyncSession,
    *,
    limit: int = DEFAULT_CHARACTER_GRAPH_LIMIT,
):
    from models.characters import CharacterCard, CharacterManifest, CharacterRelationship

    project_uuid = _project_uuid(project_id)
    bounded_limit = _bounded_character_graph_limit(limit)
    domain_cards = await db.execute(
        select(CharacterCard)
        .where(CharacterCard.project_id == project_uuid)
        .order_by(CharacterCard.name, CharacterCard.id.asc())
        .limit(bounded_limit)
    )
    cards = list(domain_cards.scalars().all())
    if cards:
        card_ids = [card.id for card in cards]
        relationships_result = await db.execute(
            select(CharacterRelationship)
            .where(
                CharacterRelationship.project_id == project_uuid,
                CharacterRelationship.source_character_id.in_(card_ids),
                CharacterRelationship.target_character_id.in_(card_ids),
            )
            .order_by(CharacterRelationship.created_at.asc(), CharacterRelationship.id.asc())
            .limit(bounded_limit)
        )
        manifests_result = await db.execute(
            select(CharacterManifest)
            .where(
                CharacterManifest.project_id == project_uuid,
                CharacterManifest.character_id.in_(card_ids),
            )
            .order_by(CharacterManifest.updated_at.desc(), CharacterManifest.id.asc())
            .limit(bounded_limit)
        )
        return build_character_domain_graph(
            cards,
            relationships_result.scalars().all(),
            manifests_result.scalars().all(),
        )
    return {"nodes": [], "edges": [], "details": {}}

async def get_world_rules_tree(
    project_id: uuid.UUID,
    db: AsyncSession,
    *,
    limit: int = DEFAULT_KNOWLEDGE_VIEW_LIMIT,
):
    return await build_world_rules_view(db, project_id, limit=limit)

async def get_foreshadowing_timeline(
    project_id: uuid.UUID,
    db: AsyncSession,
    *,
    limit: int = DEFAULT_KNOWLEDGE_VIEW_LIMIT,
):
    return await build_foreshadowing_view(db, project_id, limit=limit)

async def get_plot_tracks(
    project_id: uuid.UUID,
    db: AsyncSession,
    *,
    limit: int = DEFAULT_KNOWLEDGE_VIEW_LIMIT,
):
    return await build_plot_tracks_view(db, project_id, limit=limit)
