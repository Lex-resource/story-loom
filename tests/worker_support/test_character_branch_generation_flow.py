"""支线图引擎 handler 的行为测试(森林 K1/K3 配套安全网)。

覆盖此前无保护的 happy path 与 blocked 路径:E5 重写曾引入尾部 NameError
(未定义 outline)而测试全绿——本文件就是防复发的那张网。
"""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from worker_support import character_branch_generation_flow as flow
from core.pipeline_vocab import JobStatus
from core.character_vocab import CHARACTER_BRANCH_CHAPTER_STATUS_READY


def _fake_async(fn):
    async def _inner(*a, **k):
        result = fn(*a, **k)
        while asyncio.iscoroutine(result):
            result = await result
        return result
    return _inner


def _ids():
    return uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def _branch(branch_id):
    return SimpleNamespace(
        id=branch_id,
        storyline_id="branch:s1",
        anchor_main_chapter=28,
        target_chapters=3,
        current_chapter_index=0,
        status="generating",
    )


def _chapter(idx=1):
    return SimpleNamespace(
        chapter_index=idx,
        title="支线第1章",
        outline={
            "end_state": "角色拿到徽章",
            "character_goals": ["证明自己"],
            "relationship_changes": [{"to": "主角", "label": "结盟"}],
            "open_questions": ["徽章来源"],
        },
        content="支线正文",
        state_data={},
        relationship_changes=[],
        status="generating",
        error=None,
    )


class _FakeDB:
    def __init__(self, execute_results=None):
        self.commits = 0
        self._results = list(execute_results or [])

    async def execute(self, statement):
        result = self._results.pop(0) if self._results else None
        return SimpleNamespace(scalar_one_or_none=lambda: result)

    async def commit(self):
        self.commits += 1

    async def flush(self):
        return None

    async def get(self, model, key):
        return None

    async def rollback(self):
        return None

    def begin_nested(self):
        class _NullAsyncCM:
            async def __aenter__(self):
                return None

            async def __aexit__(self, *exc):
                return False

        return _NullAsyncCM()


@pytest.fixture
def wired(monkeypatch):
    branch_id, character_id, project_id = _ids()
    branch = _branch(branch_id)
    branch.title = "测试支线"
    branch.user_request = "写一段配角的自救支线"
    branch.generation_config = {"word_count": 2000}
    branch.anchor_context = {
        "character": {"card_data": {"identity": {"name": "配角"}}},
        "historical_docs": {"world_state": "潮汐异常", "foreshadowing": "", "plot_threads": ""},
        "anchor_chapter_ending": "锚点章节结尾",
    }
    chapter = _chapter(1)
    chapter.word_count = 0
    novel = SimpleNamespace(
        id=project_id,
        novel_format="long_webnovel",
        title="测试小说",
        outline={"书名": "测试", "类型": "悬疑", "风格": "克制"},
        target_chapters=100,
    )
    chapter_store = {1: chapter}
    captured = {"states": [], "graphs": [], "broadcasts": [], "scene": [], "events": []}

    class _FakeRuntime:
        max_rewrites = 2

    def fake_events(project_id, *, scope=None):
        ev = SimpleNamespace(scope=dict(scope or {}), payloads=[])

        async def status(step, chapter, message):
            ev.payloads.append(ev._scoped({"step": step}))

        ev.status = status
        captured["events"].append(ev)
        return ev

    monkeypatch.setattr(flow, "load_generation_pipeline_runtime",
                        _fake_async(lambda *a, **k: _FakeRuntime()))
    monkeypatch.setattr(flow, "_branch_checkpoint",
                        _fake_async(lambda *a, **k: branch))
    monkeypatch.setattr(flow, "create_or_get_branch_chapter",
                        _fake_async(lambda *a, **k: chapter))
    monkeypatch.setattr(flow, "_broadcast", _fake_async(
        lambda branch, message, **kw: captured["broadcasts"].append(message)))
    monkeypatch.setattr(flow, "recall_novel_memory",
                        _fake_async(lambda *a, **kw: SimpleNamespace(context="【支线记忆】x")))
    monkeypatch.setattr(flow, "prepare_planner_inputs", _fake_async(
        lambda *a, **k: SimpleNamespace(memory={}, issue_summaries="",
                                        previous_ending="锚点结尾",
                                        succeeding_beginning="")))
    monkeypatch.setattr(flow, "capture_branch_generation_evidence", _fake_async(lambda *a, **k: None))
    monkeypatch.setattr(flow, "enqueue_branch_chapter_vector", _fake_async(lambda *a, **k: None))
    monkeypatch.setattr(flow, "aggregate_scene_block", _fake_async(
        lambda *a, **kw: captured["scene"].append(kw)))
    monkeypatch.setattr(flow, "consolidate_scene_summary", _fake_async(
        lambda *a, **k: "整合摘要"))
    monkeypatch.setattr(flow, "GenerationEvents", fake_events)

    def fake_run_chapter_graph(state, graph):
        captured["states"].append(state)
        captured["graphs"].append(graph)
        return SimpleNamespace(decision="ok", validation_errors="")

    monkeypatch.setattr(flow, "run_chapter_graph", _fake_async(fake_run_chapter_graph))

    return {
        "novel": novel,
        "chapter_store": chapter_store,
        "branch": branch,
        "chapter": chapter,
        "project_id": project_id,
        "branch_id": branch_id,
        "character_id": character_id,
        "captured": captured,
        "monkeypatch": monkeypatch,
    }


def _job(wired, chapters=1):
    return SimpleNamespace(
        params={
            "branch_id": str(wired["branch_id"]),
            "character_id": str(wired["character_id"]),
            "chapters": chapters,
        },
        id=uuid.uuid4(),
        project_id=wired["project_id"],
        status=JobStatus.RUNNING,
        error=None,
    )


@pytest.mark.asyncio
async def test_branch_job_happy_path_runs_graph_and_completes(wired):
    novel_row = SimpleNamespace(
        id=wired["project_id"],
        novel_format="long_webnovel",
        target_chapters=100,
        word_count=0,
        title="测试小说",
        outline={"书名": "测试", "类型": "悬疑", "风格": "克制"},
    )
    db = _FakeDB(execute_results=[novel_row])
    job = _job(wired)

    await flow.process_character_branch_job(db, job)

    state = wired["captured"]["states"][0]
    # 域正确:支线域 + 锚点章
    assert state.domain.is_branch
    assert state.domain.anchor_main_chapter == 28
    # 支线域召回已注入上下文
    assert "支线记忆" in state.pipeline_context.novel_memory_context
    # 支线骨架来自支线上下文
    assert state.skeleton.get("支线故事") is True
    # 图为支线子图:恰好六个角色,不含主线的 pre_editor/style_repair
    roles = [step.role for step in wired["captured"]["graphs"][0].steps.values()]
    assert "pre_editor" not in roles and "style_repair" not in roles
    # K3:事件带支线域标记
    assert state.events.scope.get("branch_id") == str(wired["branch_id"])
    # 尾部:状态归位/指针推进/任务完成
    assert wired["chapter"].status == CHARACTER_BRANCH_CHAPTER_STATUS_READY
    assert wired["branch"].current_chapter_index == 1
    assert job.status == JobStatus.COMPLETED
    # 场景块吃到图内提取的支线原子(经 domain_artifacts)
    assert wired["captured"]["scene"], "场景块未写入"


@pytest.mark.asyncio
async def test_branch_job_blocked_marks_failure(wired):
    novel_row = SimpleNamespace(
        id=wired["project_id"],
        novel_format="long_webnovel",
        target_chapters=100,
        word_count=0,
        title="测试小说",
        outline={"书名": "测试", "类型": "悬疑", "风格": "克制"},
    )
    db = _FakeDB(execute_results=[novel_row])
    job = _job(wired)

    async def fake_blocked(state, graph):
        return SimpleNamespace(decision="blocked", validation_errors="硬冲突")

    wired["monkeypatch"].setattr(flow, "run_chapter_graph", _fake_async(fake_blocked))
    await flow.process_character_branch_job(db, job)

    assert wired["chapter"].status == "failed"
    assert wired["chapter"].error == "硬冲突"
    assert job.status == JobStatus.FAILED
