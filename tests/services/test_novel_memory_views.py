from types import SimpleNamespace

import asyncio
from types import SimpleNamespace

from services.novel_memory_views import (
    _chapter,
    build_foreshadowing_view,
    build_plot_tracks_view,
)


def test_memory_view_prefers_source_chapter_over_legacy_payload():
    assert _chapter(SimpleNamespace(source_chapter=7, data={"chapter": 1})) == 7


def test_memory_view_reads_legacy_chapter_payload_without_defaulting_to_one():
    assert _chapter(SimpleNamespace(source_chapter=None, data={"chapter": 6})) == 6
    assert _chapter(SimpleNamespace(source_chapter=None, data={})) is None


class _ScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return list(self.values)


class _Session:
    def __init__(self, values):
        self.values = values
        self.statement = None

    async def scalars(self, statement):
        self.statement = statement
        return _ScalarResult(self.values)


def test_timeline_views_place_unknown_legacy_chapters_last():
    atoms = [
        SimpleNamespace(
            memory_key="f:chain",
            statement="旧记录",
            data={},
            source_chapter=None,
        ),
        SimpleNamespace(
            memory_key="f:chain",
            statement="当前记录",
            data={"chapter": 2},
            source_chapter=None,
        ),
    ]

    foreshadowing = asyncio.run(build_foreshadowing_view(_Session(atoms), "project"))
    assert [event["chapter"] for event in foreshadowing["chains"][0]["events"]] == [2, None]

    plot = asyncio.run(build_plot_tracks_view(_Session(atoms), "project"))
    assert [event["chapter"] for event in plot["events"]] == [2, None]


def test_knowledge_view_queries_are_bounded():
    session = _Session([])

    asyncio.run(build_plot_tracks_view(session, "project", limit=12))

    statement = session.statement
    assert statement._limit_clause.value == 12
