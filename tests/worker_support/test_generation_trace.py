"""单章生成流程的 golden trace。

`worker_support/generate_job_runner._process_single_chapter` 有 400 余行，串起
planner → writer → editor → validator → extractor，内含重写回边、强制修正、
attempt 级递归和 resume 语义 —— 而在本文件之前它**没有任何端到端测试**。

它是**把生成拓扑做成可编辑数据**（图引擎）的唯一安全网：把所有 LLM/DB 侧的 flow
函数 stub 掉，只记录**阶段调用顺序与关键决策点**，重构前后这份序列必须逐项一致。
图模型里的每一条边，都必须能在这里找到对应的一条 trace —— 否则那条边就是没有证据的猜测。

序列里同时记录 `set_job_step`，因为 resume 依赖的正是 `job.current_step` 的取值 ——
阶段顺序对了但状态流转变了，恢复中的项目会坏。

**哪些东西刻意不 stub**（stub 掉就等于把要测的东西换成了假的）：

* `resolve_generation_start_state` —— resume 锚点的推导，尤其是 attempt 递归前
  `job.current_step` 已被设成 `"writer"` 这件事
* `initial_generation_loop_state` —— `decision` 是 `"revise"` 还是 `"rewrite"`、
  `skip_write_edit` 是否为真，都决定循环走不走
* `process_single_chapter` —— 递归上限 `attempt < 3` 由生产代码自己判定
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from services.pipeline_types import ChapterStatus
from worker_support import chapter_steps as steps
from worker_support import generate_job_runner as runner


def _patch(monkeypatch, name, value):
    """把某个依赖打到**所有持有它**的模块上。

    阶段实现从 generate_job_runner 搬到 chapter_steps 之后，同一个名字可能出现在
    两处（``set_job_step``、``get_chapter_by_index``）或只在其中一处。逐个写死模块
    很快就会漂移，所以这里按属性存在与否分发 —— 黄金序列是不变量，patch 打在哪
    只是测试管线。
    """
    hit = False
    for module in (runner, steps):
        if hasattr(module, name):
            monkeypatch.setattr(module, name, value)
            hit = True
    assert hit, f"没有任何被测模块持有 {name!r} —— patch 目标已失效"


class _Trace(list):
    """按顺序记录阶段调用；``add`` 返回值方便在 lambda 里用。"""

    def __init__(self, *args):
        super().__init__(*args)
        # 有些行为不体现在调用顺序上 —— 例如 ``has_extractor`` 是作为参数传给
        # ``run_chapter_post_processing`` 的，序列里看不出来。这类断言记在 captured 里，
        # 不塞进序列：序列本身是黄金基线，不该为了新增断言而改动既有条目。
        self.captured: dict[str, object] = {}

    def add(self, label: str):
        self.append(label)
        return label


class _FakeSession:
    """只需要 commit —— 所有真正碰库的函数都被 stub 了。"""

    def __init__(self, trace: _Trace):
        self._trace = trace

    async def commit(self):
        return None


class _FakeEvents:
    def __init__(self, trace: _Trace):
        self._trace = trace

    async def status(self, agent, chapter, message, **kw):
        self._trace.add(f"event.status:{agent}")

    async def chunk(self, agent, chapter, text, **kw):
        return None

    async def error(self, message):
        self._trace.add("event.error")


def _runtime(**overrides):
    base = dict(
        has_editor=True,
        has_extractor=True,
        max_rewrites=2,
        enable_editor_loop=True,
        enable_force_correction=True,
        validation_before_editor=False,
    )
    base.update(overrides)
    # style_repair 默认跟随 has_editor —— 与 StagePlan 的派生规则一致
    # （默认阶段列表在有 editor/review 时才带 editor/style_repair）。
    base.setdefault("has_style_repair", base["has_editor"])
    base.setdefault("stages", ())
    return SimpleNamespace(**base)


def _chapter(**overrides):
    base = dict(
        status=ChapterStatus.DRAFT,
        pipeline_step=None,
        draft_content=None,
        edited_content=None,
        content=None,
        rewrite_count=0,
        outline=None,
        error=None,
        validator_result=None,
        title="第3章",
        review_flags=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


OUTLINE = {"title": "第3章 潮位", "summary": "林照复核第九次潮汐记录。", "key_events": ["复核记录"]}


def _install(
    monkeypatch,
    trace: _Trace,
    *,
    runtime,
    chapter,
    start_step="planner",
    editor_decisions=("accept",),
    post_edit_continue=(False,),
    style_repair_ran=False,
    final_validator_result=None,
    resume_extractor=False,
):
    """把 generate_job_runner 的全部外部依赖换成记录型 stub。

    ``final_validator_result`` 传 list 时按 attempt 逐次 pop，用于覆盖 attempt 级递归。
    """
    editor_seq = list(editor_decisions)
    post_seq = list(post_edit_continue)
    final_seq = (
        list(final_validator_result) if isinstance(final_validator_result, list) else None
    )

    async def _check_paused(db, job_id):
        return None

    # check_paused 是函数内 lazy import，必须 patch 到源模块上。
    import worker_support.orchestrator as orch
    monkeypatch.setattr(orch, "check_paused", _check_paused, raising=False)

    async def load_runtime(db, novel_format):
        trace.add(f"runtime.load:{novel_format}")
        return runtime

    _patch(monkeypatch, "load_generation_pipeline_runtime", load_runtime)

    async def get_chapter(db, novel_id, idx):
        return chapter

    _patch(monkeypatch, "get_chapter_by_index", get_chapter)

    async def prep_chapter(db, ch, novel_id, idx, step):
        trace.add(f"chapter.prepare:{step}")
        return chapter

    _patch(monkeypatch, "prepare_chapter_for_step", prep_chapter)

    _patch(monkeypatch, "get_job_params", lambda job: {})

    # 同样刻意用真实的 resolve_generation_start_state：attempt 级递归前生产代码把
    # job.current_step 设成了 "writer"（generate_job_runner.py:474），假的 resolver 会
    # 把它盖成 "planner"，于是黄金序列记录下「重试要重新策划大纲」这种**并不存在**的
    # 行为。记录了非生产行为的基线比没有基线更糟。
    real_resolve = runner.resolve_generation_start_state

    def resolve_start(job, ch, params, *, has_editor):
        # 只在首次进入时把锚点置为本场景的 start_step；递归再进来时不覆盖。
        if not getattr(job, "_trace_seeded", False):
            job.current_step = start_step
            job._trace_seeded = True
        state = real_resolve(job, ch, params, has_editor=has_editor)
        trace.add(f"start.resolve:{state.start_step}")
        return state

    _patch(monkeypatch, "resolve_generation_start_state", resolve_start)

    def set_step(job, step, ch=None, allow_resume=False):
        job.current_step = step
        trace.add(f"step:{step}{'(resume)' if allow_resume else ''}")

    _patch(monkeypatch, "set_job_step", set_step)
    _patch(monkeypatch, "GenerationEvents", lambda pid: _FakeEvents(trace))
    _patch(monkeypatch, "should_resume_extractor", lambda step, ch: resume_extractor)

    async def planner_inputs(db, novel, idx, custom_prompt):
        trace.add("planner.inputs")
        return SimpleNamespace(
            memory={}, custom_prompt=None, succeeding_beginning="",
            issue_summaries="", previous_ending="",
        )

    _patch(monkeypatch, "prepare_planner_inputs", planner_inputs)

    async def chapter_outline(db, **kw):
        # 复用存量大纲 vs 重新策划是两件事：resume 与 attempt 重试都走复用，
        # 序列里必须区分，否则「重试重新烧一遍 planner」这种回归看不出来。
        trace.add(
            "planner.outline(reuse)" if kw.get("use_existing_outline") else "planner.outline"
        )
        return OUTLINE

    _patch(monkeypatch, "prepare_chapter_outline", chapter_outline)
    _patch(monkeypatch, "prompt_outline_for_agent", lambda o, **kw: o)

    # 刻意**不**假造 initial_generation_loop_state —— resume 语义全在它里面
    # （start_step=="editor" 派生 decision="revise" 而不是 "rewrite"，于是不重写正文；
    # start_step in [validator, extractor] 且有草稿则 skip_write_edit=True，整个
    # write-edit 循环一次都不进）。stub 掉它就等于把要测的东西换成了假的。
    # 它只读 chapter 的几个字段，_chapter() 已经全部提供。
    real_loop_state = runner.initial_generation_loop_state

    def loop_state(ch, step, *, max_rewrites):
        state = real_loop_state(ch, step, max_rewrites=max_rewrites)
        trace.captured["loop_state"] = state
        return state

    _patch(monkeypatch, "initial_generation_loop_state", loop_state)

    async def writer_ctx(db, novel, idx, outline):
        trace.add("writer.context")
        return SimpleNamespace(memory={}, pipeline=SimpleNamespace(previous_ending=""))

    _patch(monkeypatch, "load_writer_context", writer_ctx)
    _patch(monkeypatch, "rewrite_instructions_for_writer", lambda *a, **k: "instructions"
    )

    async def writer_draft(*a, **kw):
        trace.add("writer.draft")
        return "正文"

    _patch(monkeypatch, "run_writer_draft", writer_draft)

    async def save_draft(db, novel, idx, draft):
        trace.add("writer.save")
        return chapter

    _patch(monkeypatch, "save_writer_draft", save_draft)

    async def pre_validation(*a, **kw):
        trace.add("validator.pre_editor")
        return {
            "validator_result": {"passed": True},
            "draft_content": "正文",
            "edited_content": None,
            "validation_errors": "",
        }

    _patch(monkeypatch, "run_pre_editor_validation", pre_validation)

    async def editor_review(*a, **kw):
        decision = editor_seq.pop(0) if editor_seq else "accept"
        trace.add(f"editor.review:{decision}")
        return SimpleNamespace(
            chapter=chapter,
            editor_result={"rewrite_reason": "r", "rewrite_instructions": "i"},
            evaluations={}, decision=decision, edited_content="润色后", raw_issues=[],
        )

    _patch(monkeypatch, "run_editor_review", editor_review)
    _patch(monkeypatch, "mark_editor_rewrite", lambda ch, n, reason, instr: trace.add(f"editor.mark_rewrite:{n}"),
    )

    async def force_revision(*a, **kw):
        trace.add("editor.force_revise")
        return SimpleNamespace(decision="revise", edited_content="强制精修", raw_issues=[])

    _patch(monkeypatch, "run_force_editor_revision", force_revision)

    async def post_edit(*a, **kw):
        should_continue = post_seq.pop(0) if post_seq else False
        trace.add(f"validator.post_edit:continue={should_continue}")
        return SimpleNamespace(
            validator_result={"passed": True}, draft_content="正文",
            edited_content="润色后", rewrite_count=1 if should_continue else 0,
            decision="accept", validation_errors="", a5_polisher_used=False,
            should_continue=should_continue,
        )

    _patch(monkeypatch, "run_post_edit_validation", post_edit)

    async def style_repair(*a, **kw):
        trace.add(f"editor.style_repair:ran={style_repair_ran}")
        return SimpleNamespace(ran=style_repair_ran, edited_content="去AI腔")

    _patch(monkeypatch, "run_style_repair", style_repair)

    async def saved_validation(*a, **kw):
        trace.add("validator.comprehensive")
        return {"passed": True}

    _patch(monkeypatch, "run_saved_chapter_comprehensive_validation", saved_validation
    )

    async def final_validation(*a, **kw):
        trace.add("validator.final")
        if final_seq is not None:
            return final_seq.pop(0) if final_seq else {"passed": True}
        return final_validator_result if final_validator_result is not None else {"passed": True}

    _patch(monkeypatch, "run_final_validator_flow", final_validation)
    _patch(monkeypatch, "finalize_validated_chapter", lambda ch, result: trace.add("chapter.finalize"),
    )

    async def postprocess(*a, **kw):
        # has_extractor 只作为参数传进去，序列里看不出来 —— 记到 captured 里断言。
        trace.captured["has_extractor"] = kw.get("has_extractor")
        trace.add("extractor.postprocess")

    _patch(monkeypatch, "run_chapter_post_processing", postprocess)

    # attempt 级递归走的是模块全局名 process_single_chapter（generate_job_runner.py:476），
    # 所以 patch 到 runner 上就能拦住。stub 记录 attempt 后**真的**再跑一遍
    # _process_single_chapter，让递归终止条件（attempt < 3）由生产代码自己决定。
    async def retry_chapter(db, job, novel, idx, attempt, *, _experiment=None):
        trace.add(f"chapter.retry:attempt={attempt}")
        return await runner._process_single_chapter(
            db, job, novel, idx, attempt, experiment=_experiment
        )

    _patch(monkeypatch, "process_single_chapter", retry_chapter)
    _patch(monkeypatch, "StateMachine", SimpleNamespace(pause_job=lambda job, **kw: trace.add("job.pause")),
    )


def _run(trace, chapter, novel_format="long_webnovel"):
    job = SimpleNamespace(id="job-1", current_step="planner", current_chapter=0, status="running")
    novel = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        novel_format=novel_format,
        outline={"volumes": []},
        target_chapters=10,
        word_count_per_chapter=3000,
        status="generating",
    )
    asyncio.run(
        runner._process_single_chapter(_FakeSession(trace), job, novel, 3, 1)
    )
    return job


# ---------------------------------------------------------------------------
# 主路径:编辑通过、无重写、无风格修复
# ---------------------------------------------------------------------------

# 以下序列是**实测记录**，不是设计意图。两处容易看漏、但都必须保持：
#
# 1. 循环外先 set_job_step(writer, resume)，进入循环取 writer 上下文后，
#    `decision == "rewrite"` 分支**又**设一次 —— 两次都保留（:230 与 :249）。
# 2. happy path 不调用 validator.comprehensive：`run_post_edit_validation` 已经产出
#    validator_result，:442 直接复用。只有强制修正或去 AI 腔产生新内容（把
#    latest_validator_result 置回 None）时才会重新做完整校验。
GOLDEN_HAPPY_PATH = [
    "runtime.load:long_webnovel",
    "start.resolve:planner",
    "step:planner(resume)",
    "chapter.prepare:planner",
    "planner.inputs",
    "planner.outline",
    "step:writer",
    "step:writer(resume)",
    "writer.context",
    "step:writer(resume)",
    "event.status:writer",
    "writer.draft",
    "writer.save",
    "step:editor",
    "event.status:editor",
    "editor.review:accept",
    "validator.post_edit:continue=False",
    "editor.style_repair:ran=False",
    "step:validator(resume)",
    "event.status:validator",
    "validator.final",
    "chapter.finalize",
    "extractor.postprocess",
]


def test_long_form_happy_path_trace(monkeypatch):
    trace = _Trace()
    chapter = _chapter()
    _install(monkeypatch, trace, runtime=_runtime(), chapter=chapter)
    _run(trace, chapter)
    assert list(trace) == GOLDEN_HAPPY_PATH


# ---------------------------------------------------------------------------
# 分支:Editor 判 rewrite -> 回边到 Writer -> 第二轮通过
# ---------------------------------------------------------------------------

GOLDEN_EDITOR_REWRITE = [
    "runtime.load:long_webnovel",
    "start.resolve:planner",
    "step:planner(resume)",
    "chapter.prepare:planner",
    "planner.inputs",
    "planner.outline",
    "step:writer",
    "step:writer(resume)",
    "writer.context",
    "step:writer(resume)",
    "event.status:writer",
    "writer.draft",
    "writer.save",
    "step:editor",
    "event.status:editor",
    "editor.review:rewrite",
    "editor.mark_rewrite:1",
    # 回边：重新加载 writer 上下文，再设一次 step，然后重写
    "writer.context",
    "step:writer(resume)",
    "event.status:writer",
    "writer.draft",
    "writer.save",
    "step:editor",
    "event.status:editor",
    "editor.review:accept",
    "validator.post_edit:continue=False",
    "editor.style_repair:ran=False",
    "step:validator(resume)",
    "event.status:validator",
    "validator.final",
    "chapter.finalize",
    "extractor.postprocess",
]


def test_editor_rewrite_back_edge_trace(monkeypatch):
    """Editor 打回时的回边是 Phase 2 最不能弄坏的拓扑。"""
    trace = _Trace()
    chapter = _chapter()
    _install(
        monkeypatch, trace, runtime=_runtime(), chapter=chapter,
        editor_decisions=("rewrite", "accept"),
    )
    _run(trace, chapter)
    assert list(trace) == GOLDEN_EDITOR_REWRITE


# ---------------------------------------------------------------------------
# 分支:重写次数用尽 -> 强制修正
# ---------------------------------------------------------------------------


def test_force_correction_after_max_rewrites_trace(monkeypatch):
    """连续 rewrite 到上限后必须走强制修正，而不是继续回边。"""
    trace = _Trace()
    chapter = _chapter()
    _install(
        monkeypatch, trace, runtime=_runtime(max_rewrites=2), chapter=chapter,
        editor_decisions=("rewrite", "rewrite"),
    )
    _run(trace, chapter)
    assert "editor.force_revise" in trace
    # 强制修正后跳出循环，不再有第三次 writer.draft
    assert trace.count("writer.draft") == 2
    # 强制修正产出的是新内容，必须重新做完整校验
    assert trace.index("editor.force_revise") < trace.index("validator.comprehensive")


# ---------------------------------------------------------------------------
# 分支:Editor 前置校验
# ---------------------------------------------------------------------------


def test_validation_before_editor_trace(monkeypatch):
    trace = _Trace()
    chapter = _chapter()
    _install(
        monkeypatch, trace,
        runtime=_runtime(validation_before_editor=True), chapter=chapter,
    )
    _run(trace, chapter)
    assert "validator.pre_editor" in trace
    assert trace.index("validator.pre_editor") < trace.index("editor.review:accept")


# ---------------------------------------------------------------------------
# 分支:没有 Editor 节点
# ---------------------------------------------------------------------------


def test_no_editor_skips_review_and_style_repair(monkeypatch):
    trace = _Trace()
    chapter = _chapter()
    _install(monkeypatch, trace, runtime=_runtime(has_editor=False), chapter=chapter)
    _run(trace, chapter)
    assert not any(item.startswith("editor.") for item in trace)
    assert "writer.draft" in trace
    assert "validator.final" in trace
    assert "extractor.postprocess" in trace


# ---------------------------------------------------------------------------
# 分支:风格修复触发后必须重新完整校验
# ---------------------------------------------------------------------------


def test_style_repair_forces_fresh_validation(monkeypatch):
    """去 AI 腔产出新内容，必须重新走 comprehensive 校验而不是复用旧结果。"""
    trace = _Trace()
    chapter = _chapter()
    _install(
        monkeypatch, trace, runtime=_runtime(), chapter=chapter,
        style_repair_ran=True,
    )
    _run(trace, chapter)
    assert "editor.style_repair:ran=True" in trace
    assert "validator.comprehensive" in trace
    assert trace.index("editor.style_repair:ran=True") < trace.index("validator.comprehensive")


# ---------------------------------------------------------------------------
# 分支:resume 直落 extractor
# ---------------------------------------------------------------------------


def test_resume_at_extractor_skips_write_and_validate(monkeypatch):
    """POSTPROCESS_FAILED 等状态恢复时，绝不能重跑 Writer 改动已验证正文。"""
    trace = _Trace()
    chapter = _chapter(status=ChapterStatus.POSTPROCESS_FAILED, draft_content="正文")
    _install(
        monkeypatch, trace, runtime=_runtime(), chapter=chapter,
        start_step="extractor", resume_extractor=True,
    )
    _run(trace, chapter)
    assert list(trace) == [
        "runtime.load:long_webnovel",
        "start.resolve:extractor",
        "step:extractor(resume)",
        "chapter.prepare:extractor",
        "step:extractor(resume)",
        "extractor.postprocess",
    ]
    assert "writer.draft" not in trace
    assert "validator.final" not in trace


# ---------------------------------------------------------------------------
# 分支:待人工复核的章节立即暂停
# ---------------------------------------------------------------------------


def test_pending_review_chapter_pauses_immediately(monkeypatch):
    trace = _Trace()
    chapter = _chapter(status=ChapterStatus.PENDING_REVIEW, pipeline_step="extracting")
    _install(monkeypatch, trace, runtime=_runtime(), chapter=chapter)
    _run(trace, chapter)
    assert list(trace) == ["runtime.load:long_webnovel", "job.pause"]


# ---------------------------------------------------------------------------
# 分支:大纲为空则暂停在 planner
# ---------------------------------------------------------------------------


def test_empty_outline_pauses_at_planner(monkeypatch):
    trace = _Trace()
    chapter = _chapter()
    _install(monkeypatch, trace, runtime=_runtime(), chapter=chapter)

    async def empty_outline(db, **kw):
        trace.add("planner.outline")
        return {}

    _patch(monkeypatch, "prepare_chapter_outline", empty_outline)
    job = _run(trace, chapter)
    assert "event.error" in trace
    assert "job.pause" in trace
    assert "writer.draft" not in trace
    # 必须停在 planner，恢复时才会重跑策划
    assert job.current_step == "planner"


# ---------------------------------------------------------------------------
# 短篇走同一套拓扑 —— 差异在提示词/策略，不在阶段顺序
# ---------------------------------------------------------------------------


def test_short_form_uses_same_stage_topology(monkeypatch):
    """这是 Phase 2 范围判断的依据:长短篇阶段序列相同，只有 runtime.load 的格式不同。"""
    trace = _Trace()
    chapter = _chapter()
    _install(monkeypatch, trace, runtime=_runtime(), chapter=chapter)
    _run(trace, chapter, novel_format="zhihu_short")
    expected = ["runtime.load:zhihu_short"] + GOLDEN_HAPPY_PATH[1:]
    assert list(trace) == expected


# ---------------------------------------------------------------------------
# 以下场景是图引擎（Phase C）要复现的**剩余分支**。图模型的每条边都必须能在这里
# 找到对应的一条 trace，否则那条边就是没有证据的猜测。
# ---------------------------------------------------------------------------


def test_no_force_correction_pauses_at_editor(monkeypatch):
    """重写用尽 + 未启用强制修正 = 暂停等人工，而不是硬发布。

    对应图里 force_fix 步骤的 ``enabled_when: enable_force_correction`` 与
    ``on_disabled: "@pause:editor"``。
    """
    trace = _Trace()
    chapter = _chapter()
    _install(
        monkeypatch, trace,
        runtime=_runtime(max_rewrites=2, enable_force_correction=False),
        chapter=chapter,
        editor_decisions=("rewrite", "rewrite"),
    )
    job = _run(trace, chapter)
    assert trace.count("writer.draft") == 2
    assert "job.pause" in trace
    assert "editor.force_revise" not in trace
    # 暂停后直接 return —— 后续阶段一个都不能跑
    assert "editor.style_repair:ran=False" not in trace
    assert "validator.final" not in trace
    assert "extractor.postprocess" not in trace
    # 必须停在 editor，恢复时才会重新走审阅
    assert job.current_step == "editor"


def test_editor_loop_disabled_forces_on_first_rewrite(monkeypatch):
    """enable_editor_loop=False 时第一次 rewrite 就出圈，不走回边。

    对应图里 rewrite 边的 ``budgets.rewrite.disabled_when: not enable_editor_loop``
    —— 预算被禁用等于立刻耗尽。
    """
    trace = _Trace()
    chapter = _chapter()
    _install(
        monkeypatch, trace,
        runtime=_runtime(max_rewrites=3, enable_editor_loop=False),
        chapter=chapter,
        editor_decisions=("rewrite",),
    )
    _run(trace, chapter)
    # max_rewrites=3 却只写一稿：预算没被消耗，是回边本身被禁用了
    assert trace.count("writer.draft") == 1
    assert trace.count("editor.review:rewrite") == 1
    assert "editor.mark_rewrite:1" in trace
    assert "editor.force_revise" in trace
    # 强制修正产出新内容 -> 必须重新完整校验
    assert trace.index("editor.force_revise") < trace.index("validator.comprehensive")


def test_terminal_block_pauses_before_finalize(monkeypatch):
    """终审判 terminal_block:暂停，且**不得** finalize、不得发布。"""
    trace = _Trace()
    chapter = _chapter()
    _install(
        monkeypatch, trace, runtime=_runtime(), chapter=chapter,
        final_validator_result={"terminal_block": True},
    )
    job = _run(trace, chapter)
    assert "validator.final" in trace
    assert "job.pause" in trace
    assert "chapter.finalize" not in trace
    assert "extractor.postprocess" not in trace
    assert job.current_step == "validator"


def test_failed_validation_recurses_exactly_three_attempts(monkeypatch):
    """终审不通过 -> 整章重跑，上限 3 次 attempt。

    这是唯一一处**整函数级**递归（generate_job_runner.py:476），图里对应
    ``@retry_chapter`` 目标 + ``attempt`` 预算。递归上限必须钉死:多一次就是多烧一遍
    五个 agent 的 token。
    """
    trace = _Trace()
    chapter = _chapter()
    _install(
        monkeypatch, trace, runtime=_runtime(), chapter=chapter,
        final_validator_result={"passed": False},
    )
    _run(trace, chapter)
    assert [item for item in trace if item.startswith("chapter.retry")] == [
        "chapter.retry:attempt=2",
        "chapter.retry:attempt=3",
    ]
    assert trace.count("validator.final") == 3
    assert trace.count("writer.draft") == 3
    # 重试的锚点是 writer 而不是 planner，大纲**复用**不重新策划。图引擎若把重试实现成
    # 「从图的 entry 重新开始」，就会每次多烧一遍 planner —— 这里钉死。
    assert [item for item in trace if item.startswith("start.resolve")] == [
        "start.resolve:planner",
        "start.resolve:writer",
        "start.resolve:writer",
    ]
    assert trace.count("planner.outline") == 1
    assert trace.count("planner.outline(reuse)") == 2
    # 第 3 次 attempt 用尽后不再递归，终审失败必须暂停，不能落到 publish。
    assert trace.count("chapter.finalize") == 0
    assert "job.pause" in trace
    assert "extractor.postprocess" not in trace


def test_auto_force_saved_pauses_after_finalize(monkeypatch):
    """强制保存的章节要先 finalize 再暂停 —— 顺序反了会丢掉已校验的正文。"""
    trace = _Trace()
    chapter = _chapter()
    _install(
        monkeypatch, trace, runtime=_runtime(), chapter=chapter,
        final_validator_result={"passed": True, "auto_force_saved": True},
    )
    job = _run(trace, chapter)
    assert "chapter.finalize" in trace
    assert "job.pause" in trace
    assert trace.index("chapter.finalize") < trace.index("job.pause")
    # 暂停等人工复核，不能自动发布
    assert "extractor.postprocess" not in trace
    assert job.current_step == "validator"


def test_post_edit_continue_loops_back_without_rewriting(monkeypatch):
    """编辑后校验要求再走一轮时回到循环顶部，但 decision 已是 accept -> 不重写初稿。

    这条边容易被想成「回到 writer 重写」。实测不是:它回到循环顶部重新加载上下文，
    因为 decision 不是 "rewrite"，跳过 writer 直接再审一次。
    """
    trace = _Trace()
    chapter = _chapter()
    _install(
        monkeypatch, trace, runtime=_runtime(max_rewrites=2), chapter=chapter,
        post_edit_continue=(True, False),
    )
    _run(trace, chapter)
    assert trace.count("writer.draft") == 1
    assert trace.count("editor.review:accept") == 2
    assert [item for item in trace if item.startswith("validator.post_edit")] == [
        "validator.post_edit:continue=True",
        "validator.post_edit:continue=False",
    ]
    assert "extractor.postprocess" in trace


def test_resume_at_editor_reuses_draft_without_rewriting(monkeypatch):
    """从 editor 恢复:复用存量草稿，绝不重跑 Writer。

    机制在 initial_generation_decision —— start_step=="editor" 派生 "revise" 而不是
    "rewrite"，于是循环里的重写分支落空。图引擎必须保留这条:重跑 Writer 会覆盖
    用户已经看过的正文。
    """
    trace = _Trace()
    chapter = _chapter(draft_content="存量正文")
    _install(
        monkeypatch, trace, runtime=_runtime(), chapter=chapter,
        start_step="editor",
    )
    _run(trace, chapter)
    assert trace.captured["loop_state"].decision == "revise"
    assert "writer.draft" not in trace
    assert "writer.save" not in trace
    assert "step:editor(resume)" in trace
    assert "editor.review:accept" in trace
    # 从 editor 恢复也复用大纲，不重跑 planner
    assert "planner.outline(reuse)" in trace
    assert "extractor.postprocess" in trace


def test_resume_at_validator_skips_write_edit_loop_entirely(monkeypatch):
    """从 validator 恢复:skip_write_edit=True，write-edit 循环一次都不进。

    实现手法是把 rewrite_count 直接顶到 max_rewrites，于是 while 条件立刻为假。
    图引擎里这对应「入口就落在 final_check 之前」，而不是靠图内条件跳过。
    """
    trace = _Trace()
    chapter = _chapter(draft_content="已校验正文")
    _install(
        monkeypatch, trace, runtime=_runtime(), chapter=chapter,
        start_step="validator",
    )
    _run(trace, chapter)
    assert trace.captured["loop_state"].skip_write_edit is True
    assert "writer.context" not in trace
    assert "writer.draft" not in trace
    assert not any(item.startswith("editor.review") for item in trace)
    # 循环没进过 -> 没有 post_edit 结果可复用 -> 必须重新做完整校验
    assert "validator.comprehensive" in trace
    assert "validator.final" in trace
    assert "extractor.postprocess" in trace


def test_extractor_disabled_still_enters_postprocess(monkeypatch):
    """has_extractor=False 不是「跳过后处理」，而是后处理内部不跑提取。

    这点从序列上看不出来（它是传进 run_chapter_post_processing 的参数），但图引擎若
    误把它实现成「图里不含 postprocess 步骤」，章节就永远发布不了。
    """
    trace = _Trace()
    chapter = _chapter()
    _install(monkeypatch, trace, runtime=_runtime(has_extractor=False), chapter=chapter)
    _run(trace, chapter)
    assert "extractor.postprocess" in trace
    assert trace.captured["has_extractor"] is False


def test_style_repair_disabled_keeps_editor_review(monkeypatch):
    """去 AI 腔可以单独关掉，编辑审阅照跑。

    也顺带钉住:没有新内容产生时不重复完整校验（复用 post_edit 的结果）。
    """
    trace = _Trace()
    chapter = _chapter()
    _install(
        monkeypatch, trace,
        runtime=_runtime(has_style_repair=False), chapter=chapter,
    )
    _run(trace, chapter)
    assert not any(item.startswith("editor.style_repair") for item in trace)
    assert "editor.review:accept" in trace
    assert "validator.post_edit:continue=False" in trace
    assert "validator.comprehensive" not in trace
    assert "validator.final" in trace
    assert "extractor.postprocess" in trace
