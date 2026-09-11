import asyncio
from types import SimpleNamespace

import pytest

from agents.llm_transport import LLMTransportOptions, OpenAICompatibleTransport
from services.pipeline_types import ChapterStatus, NovelStatus
from worker_support import generation_postprocess


class _Db:
    def __init__(self):
        self.rollback_count = 0
        self.commit_count = 0

    async def rollback(self):
        self.rollback_count += 1

    async def commit(self):
        self.commit_count += 1

    async def refresh(self, _value):
        return None


class _Events:
    def __init__(self):
        self.errors = []

    async def status(self, *_args):
        return None

    async def error(self, message):
        self.errors.append(message)


def test_extractor_timeout_marks_chapter_recoverable(monkeypatch, freeze_tunables):
    async def hanging_post_processing(*_args, **_kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr(
        generation_postprocess,
        "run_post_processing",
        hanging_post_processing,
    )
    # 后处理超时已入库(runtime_tunables):直接覆盖进程内快照
    freeze_tunables(post_processing_timeout_seconds=0.01)

    db = _Db()
    job = SimpleNamespace(id="job-1", status="running", current_step="validator", error=None)
    novel = SimpleNamespace(id="novel-1", status=NovelStatus.GENERATING)
    chapter = SimpleNamespace(
        status="validated",
        pipeline_step="validating",
        error=None,
    )
    events = _Events()

    with pytest.raises(generation_postprocess.PostProcessingTimeoutError):
        asyncio.run(
            generation_postprocess.run_chapter_post_processing(
                db,
                job,
                novel,
                chapter,
                14,
                has_extractor=True,
                check_paused=lambda *_args: asyncio.sleep(0),
                events=events,
            )
        )

    assert chapter.status == ChapterStatus.POSTPROCESS_FAILED
    assert chapter.pipeline_step == "extracting"
    assert job.status == "failed"
    assert job.current_step == "extractor"
    assert novel.status == NovelStatus.PAUSED
    assert db.rollback_count == 1
    assert events.errors


def test_llm_transport_has_a_total_call_deadline(monkeypatch):
    transport = OpenAICompatibleTransport(
        timeout=0.01,
        debug_enabled=False,
        log_dir=".",
        payload_size_threshold=1000,
    )

    async def hanging_request(_options):
        await asyncio.sleep(1)

    monkeypatch.setattr(transport, "_complete_chat", hanging_request)
    options = LLMTransportOptions(
        model="test-model",
        base_url="http://127.0.0.1",
        api_key="test-key",
        system_prompt="system",
        user_prompt="user",
        temperature=0.1,
        max_tokens=10,
    )

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(transport.complete_chat(options))
