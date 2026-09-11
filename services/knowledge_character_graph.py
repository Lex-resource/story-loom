from services.knowledge_constants import (
    CHARACTER_DISPLAY_ATTRIBUTE_KEYS,
    CHARACTER_GROUP_ANTAGONIST,
    CHARACTER_GROUP_PROTAGONIST,
    CHARACTER_GROUP_SUPPORTING,
)
from services.knowledge_patch_handlers import relationships_for_attributes
from services.character_constants import CHARACTER_IMPORTANCE_HIGH


def build_character_domain_graph(cards, relationships, manifests=None) -> dict:
    """Build graph nodes and edges from canonical character tables."""
    manifest_by_id = {
        manifest.character_id: manifest.data or {}
        for manifest in (manifests or [])
    }
    name_by_id = {card.id: card.name for card in cards}
    nodes = []
    details = {}
    for card in cards:
        data = card.card_data or {}
        identity = data.get("identity") or {}
        group = character_group_for_card(card)
        nodes.append({
            "id": card.name,
            "label": card.name,
            "group": group,
            "title": f"{card.name} ({group})",
        })
        manifest = manifest_by_id.get(card.id, {})
        details[card.name] = "\n".join(
            part for part in (
                f"身份: {manifest.get('role_summary', '')}",
                f"性格: {manifest.get('personality_summary', '')}",
                f"位置: {manifest.get('current_location', '')}",
                f"状态: {manifest.get('current_emotion', '')}",
            ) if part.split(": ", 1)[-1]
        ) or "暂无详细背景记录"

    edges = []
    for relationship in relationships:
        source = name_by_id.get(relationship.source_character_id)
        target = name_by_id.get(relationship.target_character_id)
        if not source or not target:
            continue
        edges.append({
            "from": source,
            "to": target,
            "label": relationship.relation_type,
        })
    return {"nodes": nodes, "edges": edges, "details": details}


def character_group_for_card(card) -> str:
    data = card.card_data or {}
    identity = data.get("identity") or {}
    role_text = " ".join(
        str(identity.get(key) or "")
        for key in ("role", "faction", "camp", "stance")
    )
    if CHARACTER_GROUP_PROTAGONIST in role_text or card.importance == CHARACTER_IMPORTANCE_HIGH:
        return CHARACTER_GROUP_PROTAGONIST
    if CHARACTER_GROUP_ANTAGONIST in role_text:
        return CHARACTER_GROUP_ANTAGONIST
    return CHARACTER_GROUP_SUPPORTING


def build_character_graph(items) -> dict:
    nodes = []
    edges = []
    details = {}
    for item in items:
        group = character_group_for(item)
        nodes.append({
            "id": item.name,
            "label": item.name,
            "group": group,
            "title": f"{item.name} ({group})",
        })
        edges.extend(character_relationship_edges(item))
        details[item.name] = character_detail_text(item)

    return {"nodes": nodes, "edges": edges, "details": details}


def character_group_for(item) -> str:
    stance = item.attributes.get("立场") or ""
    camp = item.attributes.get("阵营") or ""
    identity = item.attributes.get("身份") or ""

    if (
        CHARACTER_GROUP_PROTAGONIST in stance
        or CHARACTER_GROUP_PROTAGONIST in camp
        or CHARACTER_GROUP_PROTAGONIST in identity
        or item.importance == "high"
    ):
        return CHARACTER_GROUP_PROTAGONIST
    if CHARACTER_GROUP_ANTAGONIST in stance or CHARACTER_GROUP_ANTAGONIST in camp or CHARACTER_GROUP_ANTAGONIST in identity:
        return CHARACTER_GROUP_ANTAGONIST
    return camp or identity or CHARACTER_GROUP_SUPPORTING


def character_relationship_edges(item) -> list[dict]:
    edges = []
    relationships = relationships_for_attributes(item.attributes)

    for relationship in relationships:
        edges.append({
            "from": item.name,
            "to": relationship["to"],
            "label": relationship.get("label", "相关"),
        })
    return edges


def character_detail_text(item) -> str:
    parts = []
    if item.aliases:
        parts.append(f"别名: {', '.join(item.aliases)}")
    for key in CHARACTER_DISPLAY_ATTRIBUTE_KEYS:
        value = item.attributes.get(key)
        if value:
            parts.append(f"{key}: {value}")

    relationship_lines = character_relationship_detail_lines(item)
    if relationship_lines:
        parts.append("关系列表:")
        parts.extend(relationship_lines)

    if item.created_at:
        parts.append(f"创建时间: {item.created_at}")
    if item.updated_at:
        parts.append(f"更新时间: {item.updated_at}")

    body = item.body or item.attributes.get("_free_text", "")
    if body:
        parts.append(f"\n描述:\n{body.strip()}")

    return "\n".join(parts) or "暂无详细背景记录"


def character_relationship_detail_lines(item) -> list[str]:
    lines = []
    relationships = relationships_for_attributes(item.attributes)

    for relationship in relationships:
        label = relationship.get("label", "相关")
        description = relationship.get("description", "")
        suffix = f": {description}" if description else ""
        lines.append(f"  {relationship['to']}（{label}）{suffix}")
    return lines
