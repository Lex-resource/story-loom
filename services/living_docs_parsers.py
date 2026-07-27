"""Living-docs 内容解析器。

从 services/vector_store.py 抽取，因为这些函数解析的是 living-docs 的 JSON-lines 格式，
属于 living-docs 领域而非向量存储。vector_store 与 worker_support/merger 均从此导入。
"""
import json


def parse_character_state(content: str) -> list[tuple[str, str]]:
    """解析 character_state 文本，返回 (name, json_str) 列表。

    Supports legacy JSON-lines, full JSON arrays/objects, and the current
    Markdown rendering produced by ``knowledge_to_markdown("character_state", ...)``.
    """
    content = (content or "").strip()
    if not content:
        return []

    try:
        from services.knowledge_markdown import knowledge_from_markdown

        items = knowledge_from_markdown("character_state", content)
        if items:
            return [
                (item.name, json.dumps(item.model_dump(), ensure_ascii=False))
                for item in items
            ]
    except Exception:
        pass

    parsed_items = _parse_json_items(content)
    if parsed_items is not None:
        return _character_items_to_results(parsed_items)

    results = []
    lines = content.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            name = data.get("name", "未命名")
            results.append((name, json.dumps(data, ensure_ascii=False)))
        except Exception as je:
            print(f"[LivingDocsParsers WARN] Failed to parse character_state line: {line[:80]!r} — {je}")
    return results


def parse_bullet_points(content: str) -> list[str]:
    """解析 world_state/plot_threads 等文本，返回 JSON 字符串或原始 bullet 行列表。"""
    content = (content or "").strip()
    if not content:
        return []

    parsed_items = _parse_json_items(content)
    if parsed_items is not None:
        return [json.dumps(item, ensure_ascii=False) for item in parsed_items]

    results = []
    lines = content.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            results.append(json.dumps(data, ensure_ascii=False))
        except Exception:
            if line.startswith('-') or line.startswith('*'):
                results.append(line)
    return results


def _parse_json_items(content: str) -> list[dict] | None:
    """Parse a full JSON payload into a list of dict items when possible."""
    try:
        data = json.loads(content)
    except Exception:
        return None
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return None


def _character_items_to_results(items: list[dict]) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for item in items:
        name = item.get("name", "未命名")
        results.append((name, json.dumps(item, ensure_ascii=False)))
    return results
