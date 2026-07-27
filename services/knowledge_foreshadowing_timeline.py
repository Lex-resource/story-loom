from services.knowledge_constants import (
    FORESHADOWING_STATUS_ACTIVE,
    FORESHADOWING_STATUS_CANCELLED,
    FORESHADOWING_STATUS_RESOLVED,
)


def build_foreshadowing_timeline(items) -> dict:
    chains = []
    for item in items:
        chains.append({
            "id": item.name,
            "title": item.name,
            "events": sorted(foreshadowing_events(item), key=lambda event: event["chapter"]),
        })
    return {"chains": chains}


def foreshadowing_events(item) -> list[dict]:
    chapter = getattr(item, "chapter", 1) or 1
    description = getattr(item, "description", "") or item.body or f"埋下伏笔: {item.name}"
    events = [{
        "chapter": int(chapter),
        "type": "plant",
        "desc": description,
    }]

    status = getattr(item, "status", FORESHADOWING_STATUS_ACTIVE)
    if status == FORESHADOWING_STATUS_RESOLVED:
        resolved_chapter = getattr(item, "resolved_chapter", None) or chapter
        events.append({
            "chapter": int(resolved_chapter),
            "type": "resolve",
            "desc": f"回收伏笔：{item.name}",
        })
    elif status == FORESHADOWING_STATUS_CANCELLED:
        cancelled_chapter = getattr(item, "cancelled_chapter", None) or chapter
        events.append({
            "chapter": int(cancelled_chapter),
            "type": "cancel",
            "desc": f"作废伏笔：{item.name}",
        })
    return events
