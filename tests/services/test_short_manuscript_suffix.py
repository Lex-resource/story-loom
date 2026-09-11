"""S18 回归测试：短篇上下文按预算取尾与全量渲染逐字节一致。

输出只取决于整份手稿渲染后的最后 max_chars 字符，因此任何"包含足够
字符数的连续后缀"渲染出的结果必须与全量渲染完全相同。
"""
from types import SimpleNamespace

from services.memory_manager import _pick_short_suffix_start
from services.short_story_context import (
    TRUNCATION_MARKER,
    build_short_manuscript_context,
)


def _make_chapters(count, content_chars):
    return [
        SimpleNamespace(
            chapter_index=i + 1,
            title=f"节{i + 1}",
            content=("内容" * (content_chars // 2))[:content_chars],
            edited_content=None,
            draft_content=None,
        )
        for i in range(count)
    ]


def test_suffix_subset_renders_identically_to_full_book():
    chapters = _make_chapters(12, 700)
    max_chars = 4000
    expected = build_short_manuscript_context(chapters, max_chars=max_chars)
    assert expected.startswith(TRUNCATION_MARKER)

    blocks_meta = [(c.chapter_index, c.title, len(c.content)) for c in chapters]
    start_index, reached = _pick_short_suffix_start(blocks_meta, max_chars=max_chars)
    assert reached

    subset = [c for c in chapters if c.chapter_index >= start_index]
    assert (
        build_short_manuscript_context(subset, max_chars=max_chars) == expected
    )


def test_small_book_keeps_full_rendering_without_marker():
    chapters = _make_chapters(3, 100)
    max_chars = 60_000
    blocks_meta = [(c.chapter_index, c.title, len(c.content)) for c in chapters]
    start_index, reached = _pick_short_suffix_start(blocks_meta, max_chars=max_chars)

    assert not reached
    assert start_index == 1
    assert build_short_manuscript_context(chapters, max_chars=max_chars) == (
        build_short_manuscript_context(
            [c for c in chapters if c.chapter_index >= start_index],
            max_chars=max_chars,
        )
    )


def test_single_huge_chapter_is_selected_alone():
    chapters = _make_chapters(2, 50)
    chapters[1].content = "巨" * 80_000
    max_chars = 1000
    expected = build_short_manuscript_context(chapters, max_chars=max_chars)

    blocks_meta = [(c.chapter_index, c.title, len(c.content)) for c in chapters]
    start_index, reached = _pick_short_suffix_start(blocks_meta, max_chars=max_chars)

    assert reached
    assert start_index == 2
    subset = [c for c in chapters if c.chapter_index >= start_index]
    assert build_short_manuscript_context(subset, max_chars=max_chars) == expected
