"""Formatting helpers for vector-retrieved context snippets."""


def format_chapter_extracts(documents: list[str], metadatas: list[dict]) -> str:
    type_labels = {
        "character": "人物",
        "event": "事件",
        "setting": "设定",
    }
    lines = []
    seen: set[str] = set()
    for doc, meta in zip(documents, metadatas):
        if not doc or not meta:
            continue
        key = f"{meta.get('chapter_index')}|{meta.get('type')}|{doc[:80]}"
        if key in seen:
            continue
        seen.add(key)
        chapter_index = meta.get("chapter_index", "?")
        label = type_labels.get(meta.get("type", ""), meta.get("type", "片段"))
        name = meta.get("name", "")
        prefix = f"- [第{chapter_index}章·{label}]"
        if name:
            prefix += f" {name}:"
        lines.append(f"{prefix} {doc.strip()}")
    return "\n".join(lines)
