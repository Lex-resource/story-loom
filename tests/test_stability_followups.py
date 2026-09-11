"""S6/S4 回归测试。

S6：tokenizer 预热与字符数兜底、metrics 计算语义（现于线程池中执行，数值
必须与原同步实现一致）。
S4：启动恢复只重置陈旧 RUNNING job，且存在新鲜 RUNNING 行时跳过小说状态
重置（SQL 层的 staleness 过滤不在本测试范围，验证的是编排逻辑）。
"""
import asyncio
import os
import logging
from types import SimpleNamespace

import pytest

from agents import llm_call_state
from services import startup_recovery, token_count
from services.pipeline_types import JobStatus


@pytest.fixture(autouse=True)
def _reset_tokenizer_state(monkeypatch):
    monkeypatch.setattr(token_count, "_tokenizer", None)
    monkeypatch.setattr(token_count, "_warned_tokenizer_error", False)


def test_count_tokens_empty_string():
    assert token_count.count_tokens("") == 0


def test_fallback_estimate_when_tokenizer_unavailable(monkeypatch, caplog):
    def _boom():
        raise ImportError("transformers missing")

    monkeypatch.setattr(token_count, "get_tokenizer", _boom)
    with caplog.at_level(logging.WARNING, logger="services.token_count"):
        estimate = token_count.count_tokens("一二三四五六七八九十")  # 10 字符

    assert estimate == max(1, int(10 / 1.5))
    assert any("tokenizer_encode_failed" in r.message for r in caplog.records)


def test_fallback_warns_only_once(monkeypatch, caplog):
    def _boom():
        raise ImportError("transformers missing")

    monkeypatch.setattr(token_count, "get_tokenizer", _boom)
    with caplog.at_level(logging.WARNING, logger="services.token_count"):
        token_count.count_tokens("abc")
        token_count.count_tokens("def")

    warnings = [r for r in caplog.records if "tokenizer_encode_failed" in r.message]
    assert len(warnings) == 1


def test_preload_tokenizer_success_and_failure(monkeypatch):
    calls = []

    def _ok():
        calls.append(1)
        return object()

    monkeypatch.setattr(token_count, "get_tokenizer", _ok)
    assert token_count.preload_tokenizer() is True
    assert len(calls) == 1

    def _boom():
        raise RuntimeError("no tokenizer dir")

    monkeypatch.setattr(token_count, "get_tokenizer", _boom)
    assert token_count.preload_tokenizer() is False


def test_call_metrics_semantics_unchanged():
    """reset/apply 的数值语义必须与下放线程池之前一致。"""
    agent = SimpleNamespace(
        last_duration=0.0,
        last_input_tokens=0,
        last_output_tokens=0,
        last_cache_hit_tokens=0,
        last_cache_miss_tokens=0,
    )
    fake_count = len

    start = llm_call_state.reset_call_metrics(agent, "sys", "user", fake_count)
    assert start > 0
    assert agent.last_input_tokens == len("sys") + len("user")
    assert agent.last_output_tokens == 0

    # usage 缺失：本地估算 output tokens
    llm_call_state.apply_api_usage(agent, None, "response", fake_count)
    assert agent.last_output_tokens == len("response")

    # usage 存在：API 值优先
    llm_call_state.apply_api_usage(
        agent,
        {"prompt_tokens": 10, "completion_tokens": 5, "prompt_cache_hit_tokens": 2},
        "ignored",
        fake_count,
    )
    assert agent.last_input_tokens == 10
    assert agent.last_output_tokens == 5
    assert agent.last_cache_hit_tokens == 2


class _RecoverySession:
    def __init__(self, stale_jobs, fresh_count):
        self.stale_jobs = stale_jobs
        self.fresh_count = fresh_count
        self.novel_update_executed = False
        self.commits = 0
        self._call = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, statement):
        self._call += 1
        if self._call == 1:
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: self.stale_jobs)
            )
        if self._call == 2:
            return SimpleNamespace(scalar=lambda: self.fresh_count)
        self.novel_update_executed = True
        return SimpleNamespace(rowcount=1)

    async def commit(self):
        self.commits += 1


@pytest.fixture(autouse=True)
def _no_append_error(monkeypatch):
    monkeypatch.setattr(startup_recovery, "append_job_error", lambda job, msg, traceback="": None)


def test_stale_jobs_failed_and_novels_reset(monkeypatch):
    stale = SimpleNamespace(id="job-1", status=JobStatus.RUNNING)
    session = _RecoverySession([stale], fresh_count=0)
    monkeypatch.setattr(startup_recovery, "async_session", lambda: session)

    failed, fresh = asyncio.run(startup_recovery.reset_stale_running_jobs())

    assert (failed, fresh) == (1, 0)
    assert stale.status == JobStatus.FAILED
    assert session.novel_update_executed is True
    assert session.commits == 1


def test_fresh_running_jobs_skip_novel_reset(monkeypatch):
    session = _RecoverySession([], fresh_count=2)
    monkeypatch.setattr(startup_recovery, "async_session", lambda: session)

    failed, fresh = asyncio.run(startup_recovery.reset_stale_running_jobs())

    assert (failed, fresh) == (0, 2)
    assert session.novel_update_executed is False


def _fake_chroma_client(monkeypatch, target):
    """mock get_client 并记录 delete_collection 调用(探针集合清理)。"""
    from services import vector_chroma

    class _FakeClient:
        def __init__(self):
            self.deleted_collections = []

        def delete_collection(self, name):
            self.deleted_collections.append(name)

    fake_client = _FakeClient()
    monkeypatch.setattr(vector_chroma, "get_client", lambda: fake_client)
    target.append(fake_client)
    return fake_client


def test_preload_chroma_success(monkeypatch, tmp_path):
    """预热成功:读写探针通过 + 模型缓存存在时 embedding 会话建立。"""
    from services import vector_chroma

    ops = []

    class _FakeCollection:
        def upsert(self, ids, documents, embeddings, metadatas):
            ops.append(("upsert", ids))

        def query(self, query_embeddings, n_results):
            ops.append(("query", n_results))
            return {"ids": [["warmup-probe"]]}

        def delete(self, ids):
            ops.append(("delete", ids))

    holders = []
    fake_client = _fake_chroma_client(monkeypatch, holders)
    monkeypatch.setattr(vector_chroma, "get_or_create_collection", lambda _n: _FakeCollection())
    monkeypatch.setattr(vector_chroma, "_ONNX_MODEL_CACHE_DIR", tmp_path)  # 已存在
    embedding_calls = []
    monkeypatch.setattr(
        vector_chroma,
        "_default_embedding_function",
        lambda texts: embedding_calls.append(texts),
    )

    assert vector_chroma.preload_chroma() is True
    assert vector_chroma.chroma_warmup_ok is True
    assert [op[0] for op in ops] == ["upsert", "query", "delete"]
    assert embedding_calls == [["warmup"]]
    # 探针集合用完即删,不在集合列表里留残留
    assert fake_client.deleted_collections == [f"chroma_warmup_probe_{os.getpid()}"]


def test_preload_chroma_probe_failure_returns_false(monkeypatch):
    """探针失败不抛:返回 False 并记录健康标志,chroma 照常可用。"""
    from services import vector_chroma

    class _BrokenCollection:
        def upsert(self, *a, **kw):
            raise RuntimeError("disk stuck")

    monkeypatch.setattr(vector_chroma, "get_or_create_collection", lambda _n: _BrokenCollection())
    holders = []
    fake_client = _fake_chroma_client(monkeypatch, holders)

    assert vector_chroma.preload_chroma() is False
    assert vector_chroma.chroma_warmup_ok is False
    # 失败残留的探针集合也要被 finally 清理
    assert fake_client.deleted_collections == [f"chroma_warmup_probe_{os.getpid()}"]


def test_preload_chroma_skips_download_when_model_cache_missing(monkeypatch, caplog, tmp_path):
    """模型缓存缺失:不触发下载(0.5.0 下载无超时),明确告警。"""
    import logging

    from services import vector_chroma

    class _FakeCollection:
        def upsert(self, *a, **kw):
            pass

        def query(self, **kw):
            return {"ids": [["warmup-probe"]]}

        def delete(self, *a, **kw):
            pass

    _fake_chroma_client(monkeypatch, [])
    monkeypatch.setattr(vector_chroma, "get_or_create_collection", lambda _n: _FakeCollection())
    monkeypatch.setattr(vector_chroma, "_ONNX_MODEL_CACHE_DIR", tmp_path / "missing")
    embedding_calls = []
    monkeypatch.setattr(
        vector_chroma,
        "_default_embedding_function",
        lambda texts: embedding_calls.append(texts),
    )

    with caplog.at_level(logging.WARNING, logger="services.vector_chroma"):
        assert vector_chroma.preload_chroma() is True  # 探针本身通过

    assert embedding_calls == []  # 没有触发模型加载/下载
    assert any("chroma_embedding_model_cache_missing" in r.message for r in caplog.records)
