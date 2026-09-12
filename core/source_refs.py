"""来源引用(source_ref)的统一模板。

`chapter:{index}[:part...]` 家族的字符串此前散布在 narrative_index /
chapter_continuity / knowledge_merger 各自手写,格式漂移无测试守(森林 A3)。
所有 chapter 来源引用一律经此函数拼装。
"""

from __future__ import annotations


def chapter_source_ref(chapter_index: int, *parts: str | int) -> str:
    """构造 `chapter:{index}` 或 `chapter:{index}:{part}[:...]` 形态的来源引用。"""
    base = f"chapter:{chapter_index}"
    for part in parts:
        base += f":{part}"
    return base
