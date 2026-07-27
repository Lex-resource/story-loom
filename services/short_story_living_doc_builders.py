from __future__ import annotations

from typing import Any

from models.novel import Novel
from services.knowledge_types import (
    CharacterKnowledge,
    ForeshadowingKnowledge,
    WorldRuleKnowledge,
)


def outline_title(novel: Novel, outline: dict[str, Any]) -> str:
    return outline.get("书名") or outline.get("标题") or novel.title or "未命名小说"


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def item_name(item: Any, *keys: str, fallback: str) -> str:
    if isinstance(item, dict):
        for key in keys:
            value = item.get(key)
            if value:
                return str(value)
    return fallback


def build_characters(outline: dict[str, Any]) -> list[CharacterKnowledge]:
    items: list[CharacterKnowledge] = []
    for idx, raw in enumerate(as_list(outline.get("主要人物")), start=1):
        name = item_name(raw, "姓名", "名字", "name", fallback=f"人物{idx}")
        attrs: dict[str, Any] = {}
        body = ""
        if isinstance(raw, dict):
            attrs = {
                "角色": raw.get("角色") or raw.get("role", ""),
                "动机": raw.get("动机") or raw.get("motivation", ""),
                "relationships": raw.get("relationships") or raw.get("关系") or [],
            }
            body = raw.get("简介") or raw.get("描述") or raw.get("body") or ""
        else:
            body = str(raw)
        items.append(CharacterKnowledge(name=name, body=body, attributes={k: v for k, v in attrs.items() if v}))
    return items


def build_world_rules(outline: dict[str, Any]) -> list[WorldRuleKnowledge]:
    items: list[WorldRuleKnowledge] = []
    for idx, raw in enumerate(as_list(outline.get("世界设定")), start=1):
        name = item_name(raw, "名称", "名字", "name", fallback=f"世界设定{idx}")
        body = ""
        rule_type = ""
        attrs: dict[str, Any] = {}
        if isinstance(raw, dict):
            body = raw.get("描述") or raw.get("内容") or raw.get("body") or ""
            rule_type = raw.get("rule_type") or raw.get("类型") or raw.get("type") or ""
            attrs = {k: v for k, v in raw.items() if k not in {"名称", "名字", "name", "描述", "内容", "body"}}
        else:
            body = str(raw)
        items.append(WorldRuleKnowledge(name=name, body=body, rule_type=rule_type, attributes=attrs))
    return items


def build_foreshadowing(outline: dict[str, Any]) -> list[ForeshadowingKnowledge]:
    items: list[ForeshadowingKnowledge] = []
    for idx, raw in enumerate(as_list(outline.get("关键伏笔") or outline.get("主要伏笔")), start=1):
        name = item_name(raw, "伏笔名称", "名称", "name", fallback=f"伏笔{idx}")
        if isinstance(raw, dict):
            desc = raw.get("description") or raw.get("描述") or raw.get("埋设和回收方式") or ""
            chapter = int(raw.get("chapter") or raw.get("埋下章节") or 1)
            resolved = raw.get("resolved_chapter") or raw.get("回收章节") or raw.get("收回章节")
            resolved_chapter = int(resolved) if resolved else None
        else:
            desc = str(raw)
            chapter = 1
            resolved_chapter = None
        items.append(
            ForeshadowingKnowledge(
                name=name,
                description=desc,
                chapter=chapter,
                resolved_chapter=resolved_chapter,
            )
        )
    return items


def format_global_outline(title: str, outline: dict[str, Any]) -> str:
    lines = [f"# 《{title}》全书整体大纲", ""]
    for key in ("类型", "简介", "总章节数", "故事基调", "结局走向"):
        if outline.get(key):
            lines.append(f"**{key}**: {outline[key]}")
            lines.append("")
    for key in ("主要人物", "世界设定", "关键伏笔"):
        values = as_list(outline.get(key))
        if not values:
            continue
        lines.append(f"## {key}")
        for raw in values:
            if isinstance(raw, dict):
                name = raw.get("名字") or raw.get("姓名") or raw.get("名称") or raw.get("伏笔名称") or "条目"
                desc = raw.get("描述") or raw.get("动机") or raw.get("description") or raw.get("简介") or ""
                lines.append(f"- **{name}**: {desc}")
            else:
                lines.append(f"- {raw}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def format_act_outline(title: str, outline: dict[str, Any]) -> str:
    lines = [f"# 《{title}》分幕大纲与情节设计", ""]
    for idx, raw in enumerate(as_list(outline.get("故事阶段")), start=1):
        if isinstance(raw, dict):
            name = raw.get("幕名") or raw.get("阶段名称") or raw.get("名称") or f"第{idx}幕"
            lines.append(f"## {name}")
            for key in ("章节范围", "progress", "核心冲突"):
                if raw.get(key):
                    label = "主要推进" if key == "progress" else key
                    lines.append(f"**{label}**: {raw[key]}")
                    lines.append("")
        else:
            lines.append(f"## 第{idx}幕")
            lines.append(str(raw))
            lines.append("")
    return "\n".join(lines).strip() + "\n"
