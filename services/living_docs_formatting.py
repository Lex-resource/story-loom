"""Markdown formatting helpers for living docs.

These functions are pure presentation logic. Keeping them out of
``living_docs.py`` leaves that module focused on storage orchestration.
"""
import json

from services.knowledge_constants import (
    FORESHADOWING_DEFAULT_IMPORTANCE,
    FORESHADOWING_STATUS_ACTIVE,
    FORESHADOWING_STATUS_CANCELLED,
    FORESHADOWING_STATUS_RESOLVED,
)


def format_outline_to_markdown(outline: dict) -> str:
    if not outline:
        return ""
    lines = []
    title = outline.get("书名") or outline.get("标题") or "未命名小说"
    lines.append(f"# 《{title}》全书整体大纲\n")

    simple_keys = ["类型", "风格", "总章数", "结局走向"]
    for key in simple_keys:
        if key in outline:
            lines.append(f"**{key}**: {outline[key]}\n")

    complex_keys = ["世界设定", "主要人物", "主要伏笔"]
    for key in complex_keys:
        if key in outline:
            lines.append(f"## {key}")
            value = outline[key]
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    lines.append(f"### {sub_key}")
                    lines.append(f"{sub_value}\n")
            elif isinstance(value, list):
                for item in value:
                    lines.append(f"- {item}")
                lines.append("")
            else:
                lines.append(f"{value}\n")
    return "\n".join(lines)


def format_act_outline_to_markdown(outline: dict) -> str:
    if not outline:
        return ""
    lines = []
    title = outline.get("书名") or outline.get("标题") or "未命名小说"
    lines.append(f"# 《{title}》分幕大纲与情节设计\n")

    if "故事阶段" in outline:
        stages = outline["故事阶段"]
        if isinstance(stages, list):
            for idx, stage in enumerate(stages):
                stage_title = f"第 {idx + 1} 阶段"
                if isinstance(stage, dict):
                    stage_title = stage.get("阶段名称") or stage.get("名称") or stage_title
                    lines.append(f"## {stage_title}")
                    for key, value in stage.items():
                        if key in ["阶段名称", "名称"]:
                            continue
                        if isinstance(value, list):
                            lines.append(f"### {key}")
                            for item in value:
                                lines.append(f"- {item}")
                            lines.append("")
                        else:
                            lines.append(f"**{key}**: {value}\n")
                else:
                    lines.append(f"## {stage_title}")
                    lines.append(f"{stage}\n")
        elif isinstance(stages, dict):
            for key, value in stages.items():
                lines.append(f"## {key}")
                lines.append(f"{value}\n")
        else:
            lines.append("## 故事阶段")
            lines.append(f"{stages}\n")
    else:
        lines.append("## 分幕设计")
        lines.append("暂无分幕大纲数据。")
    return "\n".join(lines)


def compile_foreshadowing(docs) -> str:
    active_lines = []
    resolved_lines = []
    cancelled_lines = []

    for doc in docs:
        try:
            data = json.loads(doc.content)
        except Exception:
            data = {
                "description": doc.content,
                "status": FORESHADOWING_STATUS_ACTIVE,
                "importance": FORESHADOWING_DEFAULT_IMPORTANCE,
                "chapter": 1,
            }

        fs_id = doc.name
        desc = data.get("description", "")
        status = data.get("status", FORESHADOWING_STATUS_ACTIVE)
        importance = data.get("importance", FORESHADOWING_DEFAULT_IMPORTANCE)
        chapter = data.get("chapter", 1)

        line = f"- [ID: {fs_id}] {desc} (重要度: {importance}, 埋下章节: {chapter}"

        if status == FORESHADOWING_STATUS_ACTIVE:
            line += ")"
            active_lines.append(line)
        elif status == FORESHADOWING_STATUS_RESOLVED:
            res_ch = data.get("resolved_chapter", "")
            line += f", 回收章节: {res_ch})"
            resolved_lines.append(line)
        elif status == FORESHADOWING_STATUS_CANCELLED:
            can_ch = data.get("cancelled_chapter", "")
            line += f", 作废章节: {can_ch})"
            cancelled_lines.append(line)

    content = "# 伏笔账本\n\n## 活跃伏笔\n"
    if active_lines:
        content += "\n".join(active_lines) + "\n"
    else:
        content += "(暂无)\n"

    content += "\n## 已回收伏笔\n"
    if resolved_lines:
        content += "\n".join(resolved_lines) + "\n"
    else:
        content += "(暂无)\n"

    content += "\n## 已作废伏笔\n"
    if cancelled_lines:
        content += "\n".join(cancelled_lines) + "\n"
    else:
        content += "(暂无)\n"

    return content
