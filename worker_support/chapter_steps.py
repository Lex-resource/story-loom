"""单章生成的阶段适配器。

每个适配器把一个生成阶段包装成统一签名：**读黑板 → 调既有 flow 函数 → 写黑板 →
返回裁决**。适配器里刻意**不含任何编排**：不知道下一步是谁、不知道有没有回边、
不知道预算用没用完。那些属于编排层（Phase C 的图解释器），于是「跑哪些阶段、什么顺序、
什么条件回边」才可能变成用户可编辑的数据。

**这里不重写任何 flow 函数** —— `run_writer_draft`、`run_editor_review`、
`run_post_edit_validation` 等原样调用，参数逐个对照搬迁。适配器只是把原本靠「谁在谁
上面」隐含的读写关系写成明面。这是整套改动安全的关键：真正做事的代码一行没动。

角色一览（11 个）。其中 `context_refresh` 与 `publish` 是**系统角色**：没有提示词、
不可删除、用户在界面上看不到它们可配置的部分。

| 角色              | agent      | 干什么                             | 可能的裁决          |
|-------------------|------------|------------------------------------|---------------------|
| `outline`         | planner    | 生成/复用分章大纲                  | ok / empty          |
| `context_refresh` | (system)   | 循环顶部刷新记忆与上下文           | ok / skipped        |
| `draft`           | writer     | 写初稿                             | ok                  |
| `pre_editor`      | validator  | 编辑前置校验                       | ok                  |
| `review`          | editor     | 审阅打分，可能打回                 | ok / rewrite        |
| `force_revise`    | editor     | 重写用尽后的强制修正               | ok / skipped        |
| `post_edit`       | validator  | 编辑后校验，可能要求再走一轮       | ok / rewrite        |
| `style_repair`    | editor     | 去 AI 腔（有确定性门控，可能不跑） | ok / skipped        |
| `final`           | validator  | 终审与字数                         | ok / fail / blocked |
| `publish`         | (system)   | 落定校验结论                       | ok / blocked        |
| `postprocess`     | extractor  | 沉淀记忆并发布                     | ok                  |
"""
from __future__ import annotations

from core.pipeline_vocab import ChapterStatus

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from agents.constants import (
    AGENT_EDITOR,
    AGENT_EXTRACTOR,
    AGENT_PLANNER,
    AGENT_VALIDATOR,
    AGENT_WRITER,
)
from services.continuity_contract import prompt_outline_for_agent
from services.pipeline_transitions import set_job_step
from worker_support.chapter_repository import get_chapter_by_index
from worker_support.chapter_run_state import (
    VERDICT_BLOCKED,
    VERDICT_EMPTY,
    VERDICT_FAIL,
    VERDICT_OK,
    VERDICT_REWRITE,
    VERDICT_SKIPPED,
    ChapterRunState,
)
from worker_support.generation_context import rewrite_instructions_for_writer
from worker_support.generation_editor_flow import (
    run_editor_review,
    run_force_editor_revision,
    run_post_edit_validation,
    run_style_repair,
)
from worker_support.generation_editor_policy import mark_editor_rewrite
from worker_support.generation_nodes import editor, planner, validator_agent, writer
from worker_support.generation_outline import prepare_chapter_outline
from worker_support.generation_postprocess import run_chapter_post_processing
from worker_support.generation_validation_flow import (
    run_final_validator_flow,
    run_pre_editor_validation,
    run_saved_chapter_comprehensive_validation,
)
from worker_support.generation_validator_policy import finalize_validated_chapter
from worker_support.generation_writer_flow import (
    load_writer_context,
    run_writer_draft,
    save_writer_draft,
)

# 角色名与裁决词表的唯一来源是 `services/pipeline_stages` —— 图校验器（services/）和
# 适配器（这里）必须用同一套值，各写一份迟早漂移。
# `tests/worker_support/test_chapter_graph_runner.py::test_real_adapters_cover_every_graph_role`
# 钉住「图登记的每个角色都有适配器」。
from services.pipeline_stages import (
    ROLE_CONTEXT_REFRESH,
    ROLE_DRAFT,
    ROLE_FINAL,
    ROLE_FORCE_REVISE,
    ROLE_OUTLINE,
    ROLE_POST_EDIT,
    ROLE_POSTPROCESS,
    ROLE_PRE_EDITOR,
    ROLE_PUBLISH,
    ROLE_REVIEW,
    ROLE_STYLE_REPAIR,
)

# 系统角色：没有提示词、不可被用户从工作流里删掉。
SYSTEM_ROLES: frozenset[str] = frozenset({ROLE_CONTEXT_REFRESH, ROLE_PUBLISH})


@dataclass(frozen=True)
class StepAdapter:
    """一个阶段的执行契约。

    Attributes:
        role: 角色名，工作流节点通过它找到适配器。
        run: 执行体。签名 ``(state, node) -> 裁决``。
    """

    role: str
    run: Callable[[ChapterRunState, Any], Awaitable[str]]


_ADAPTERS: dict[str, StepAdapter] = {}


def register(role: str):
    """把一个执行体登记为某角色的适配器。

    刻意**不带** anchor 参数：resume 锚点由适配器体内的 ``set_job_step`` 调用决定，
    在这里再声明一遍就是第二份同样的事实，而没人读的重复事实迟早漂移。
    「锚点只能是 5 个 agent 名」这条硬约束由
    ``tests/worker_support/test_chapter_steps_anchors.py`` 直接对源码做 AST 检查。
    """

    def decorator(func: Callable[[ChapterRunState, Any], Awaitable[str]]):
        _ADAPTERS[role] = StepAdapter(role=role, run=func)
        return func

    return decorator


def adapter_for(role: str) -> StepAdapter:
    try:
        return _ADAPTERS[role]
    except KeyError:
        known = ", ".join(sorted(_ADAPTERS)) or "<none>"
        raise KeyError(f"未知阶段角色 {role!r}。已登记: {known}") from None


def registered_roles() -> tuple[str, ...]:
    return tuple(_ADAPTERS)


async def _check_paused(state: ChapterRunState) -> None:
    # orchestrator 与 generate_job_runner 相互导入，只能函数内 lazy import。
    from worker_support.orchestrator import check_paused

    await check_paused(state.db, state.job.id)


# ---------------------------------------------------------------------------
# planner
# ---------------------------------------------------------------------------

@register(ROLE_OUTLINE)
async def run_outline(state: ChapterRunState, node: Any = None) -> str:
    """生成或复用分章大纲。

    ``use_existing_outline`` 为真时复用存量大纲、不烧 planner —— resume 与 attempt
    重试都走这条，别把它实现成「每次从头策划」。
    """
    state.outline = await prepare_chapter_outline(
        state.db,
        novel=state.novel,
        chapter_index=state.chapter_index,
        use_existing_outline=state.use_existing_outline,
        mem_context=state.memory,
        skeleton=state.skeleton,
        issue_summaries=state.issue_summaries,
        custom_prompt=state.custom_prompt,
        planner_node=planner,
        planner_cb=state.planner_cb,
        planner_previous_ending=state.planner_previous_ending,
        project_id=state.project_id,
        events=state.events,
    )

    if not state.outline or not state.outline.get("summary"):
        await state.events.error(
            f"第 {state.chapter_index} 章大纲为空或生成失败，已暂停生成，请手动补充。"
        )
        return VERDICT_EMPTY

    # 校验器要和 Writer 看同一份本章计划，否则「本章首次揭露」会被当成无依据的未来事实。
    state.memory["chapter_outline"] = prompt_outline_for_agent(state.outline)

    # 推进章节状态到 write-edit 簇的入口。这两段都是「策划完成」的后果，所以放在这里：
    #
    # 1. 真正从 planner 起步时把章节推进到 writer。从 editor/validator 恢复的任务不能
    #    被拉回去。
    # 2. 确定这一簇的恢复锚点：带着存量草稿从 editor 恢复就锚在 editor（否则恢复会
    #    重跑 Writer 覆盖用户已经看过的正文），否则锚在 writer。
    #    `skip_write_edit` 时整簇都不跑，不必也不该动锚点。
    if state.start_step == AGENT_PLANNER:
        set_job_step(state.job, AGENT_WRITER, state.chapter)
        await state.db.commit()

    if not state.skip_write_edit:
        await _check_paused(state)
        if (
            state.start_step == AGENT_EDITOR
            and state.draft_content
            and state.runtime.has_editor
        ):
            set_job_step(state.job, AGENT_EDITOR, state.chapter, allow_resume=True)
        else:
            set_job_step(state.job, AGENT_WRITER, state.chapter, allow_resume=True)
        await state.db.commit()

    return VERDICT_OK


# ---------------------------------------------------------------------------
# 循环顶部：刷新上下文
# ---------------------------------------------------------------------------

@register(ROLE_CONTEXT_REFRESH)
async def run_context_refresh(state: ChapterRunState, node: Any = None) -> str:
    """重新从库里取记忆与流水线上下文，并清掉上一轮的校验结论。

    返回 ``skipped`` 表示本轮不必重写初稿（``decision`` 不是 ``"rewrite"``）——
    从 editor 恢复（``decision == "revise"``）以及 post_edit 要求再走一轮
    （``decision`` 已是 ``"accept"``）都走这条，实测都不重跑 Writer。

    清 ``latest_validator_result`` 是必须的：上一轮 post_edit 留下的结论对这一轮的
    新正文无效。原实现把它放在 ``if validation_before_editor: ... else: ...`` 的
    else 分支里，等价但看不出意图。
    """
    writer_context = await load_writer_context(
        state.db, state.novel, state.chapter_index, state.outline
    )
    state.memory = writer_context.memory
    state.memory["chapter_outline"] = state.outline
    state.pipeline_context = writer_context.pipeline

    state.latest_validator_result = None
    state.validation_errors = ""

    return VERDICT_OK if state.decision == "rewrite" else VERDICT_SKIPPED


# ---------------------------------------------------------------------------
# writer
# ---------------------------------------------------------------------------

@register(ROLE_DRAFT)
async def run_draft(state: ChapterRunState, node: Any = None) -> str:
    """写初稿。重写时把上一版的校验错误作为修改指令带进去。"""
    prev_chapter = await get_chapter_by_index(
        state.db, state.novel.id, state.chapter_index, domain=state.domain
    )
    rewrite_instructions = rewrite_instructions_for_writer(
        state.custom_prompt,
        prev_chapter.error if prev_chapter else None,
        state.succeeding_beginning,
        state.chapter_index,
    )

    await _check_paused(state)
    set_job_step(state.job, AGENT_WRITER, state.chapter, allow_resume=True)
    await state.db.commit()
    await state.events.status(
        AGENT_WRITER,
        state.chapter_index,
        (
            f"作家智能体正在创作初稿... (第 {state.rewrite_count + 1} 次尝试)"
            if state.rewrite_count > 0
            else "作家智能体正在创作初稿..."
        ),
    )

    state.draft_content = await run_writer_draft(
        state.db,
        state.novel,
        state.chapter_index,
        writer,
        state.pipeline_context,
        state.outline,
        state.skeleton,
        state.issue_summaries,
        rewrite_instructions,
        on_chunk=state.writer_cb,
    )
    # 新初稿让上一版的润色稿失效。
    state.edited_content = None
    state.chapter = await save_writer_draft(
        state.db, state.novel, state.chapter_index, state.draft_content
    )
    return VERDICT_OK


# ---------------------------------------------------------------------------
# validator：编辑前置
# ---------------------------------------------------------------------------

@register(ROLE_PRE_EDITOR)
async def run_pre_editor(state: ChapterRunState, node: Any = None) -> str:
    """编辑之前先做一次校验，把硬伤作为审阅输入交给 Editor。"""
    result = await run_pre_editor_validation(
        state.db,
        state.novel,
        state.chapter_index,
        state.outline.get("title", f"第{state.chapter_index}章"),
        state.draft_content,
        state.edited_content,
        state.pipeline_context.previous_ending,
        state.memory,
        state.chapter,
        validator_agent,
        state.events,
        has_editor=state.runtime.has_editor,
        on_validator_chunk=state.validator_cb,
    )
    state.latest_validator_result = result["validator_result"]
    state.draft_content = result["draft_content"]
    state.edited_content = result["edited_content"]
    state.validation_errors = result["validation_errors"]
    return VERDICT_OK


# ---------------------------------------------------------------------------
# editor
# ---------------------------------------------------------------------------

@register(ROLE_REVIEW)
async def run_review(state: ChapterRunState, node: Any = None) -> str:
    """审阅打分。判 rewrite 时**在这里**消耗重写预算并记档。

    预算的加一放在适配器而不是编排层，是因为 ``mark_editor_rewrite`` 要把「第几次
    重写、为什么」写进章节 —— 那是这一步的产出，不是边的产出。编排层只负责比较
    ``rewrite_count`` 与 ``max_rewrites``。
    """
    await _check_paused(state)
    set_job_step(state.job, AGENT_EDITOR, state.chapter)
    await state.db.commit()
    await state.events.status(
        AGENT_EDITOR, state.chapter_index, "编辑智能体正在审阅及润色文稿..."
    )

    review = await run_editor_review(
        state.db,
        state.novel,
        state.chapter_index,
        editor,
        state.pipeline_context,
        state.draft_content,
        state.outline,
        state.issue_summaries,
        state.validation_errors,
        state.rewrite_count,
        on_chunk=state.editor_cb,
    )
    state.chapter = review.chapter
    state.editor_result = review.editor_result
    state.evaluations = review.evaluations
    state.decision = review.decision
    state.edited_content = review.edited_content
    state.raw_issues = review.raw_issues

    if state.decision != "rewrite":
        return VERDICT_OK

    state.rewrite_count += 1
    mark_editor_rewrite(
        state.chapter,
        state.rewrite_count,
        state.editor_result.get("rewrite_reason", ""),
        state.editor_result.get("rewrite_instructions", ""),
    )
    await state.db.commit()
    return VERDICT_REWRITE


@register(ROLE_FORCE_REVISE)
async def run_force_revise(state: ChapterRunState, node: Any = None) -> str:
    """重写预算耗尽后的强制修正。

    未启用强制修正时返回 ``skipped`` —— 编排层据此暂停等人工，而不是硬发布一版
    Editor 已经判定不合格的正文。
    """
    if not state.runtime.enable_force_correction:
        await state.events.status(
            AGENT_EDITOR,
            state.chapter_index,
            "编辑器要求重写，但当前流程未启用自动重写/强制修正，已暂停等待人工处理。",
        )
        return VERDICT_SKIPPED

    await state.events.status(
        AGENT_EDITOR,
        state.chapter_index,
        f"重写次数已达上限（{state.max_rewrites}次），正在启动编辑智能体进行强制修正和润色...",
    )
    revision = await run_force_editor_revision(
        state.db,
        state.novel,
        state.chapter_index,
        state.chapter,
        editor,
        state.draft_content,
        state.outline,
        state.memory,
        state.issue_summaries,
        state.editor_result.get("rewrite_reason", ""),
        state.validation_errors,
        state.evaluations,
        on_chunk=state.editor_cb,
    )
    state.decision = revision.decision
    state.edited_content = revision.edited_content
    state.raw_issues = revision.raw_issues
    # 强制修正产出的是新内容，必须重新做完整校验才能发布。
    state.latest_validator_result = None
    await state.db.commit()
    return VERDICT_OK


@register(ROLE_STYLE_REPAIR)
async def run_style_repair_step(state: ChapterRunState, node: Any = None) -> str:
    """文风修复。内置的「去 AI 腔」前面有确定性检测器做门控，常常不实际调用 LLM。

    自定义节点可以设 `options.always_run` 绕过门控 —— 口语化重写、节奏加速这类润色
    是无条件想跑一遍的，而内置的去 AI 腔要保持只在检测到套话/句式单一时才烧 token。
    两者共用同一个适配器，靠节点上的开关区分。
    """
    if state.chapter is None:
        return VERDICT_SKIPPED

    always_run = bool(node.option("always_run", False)) if node is not None else False

    outcome = await run_style_repair(
        state.db,
        state.novel,
        state.chapter_index,
        state.chapter,
        editor,
        state.draft_content,
        state.edited_content,
        state.outline,
        state.memory,
        state.issue_summaries,
        state.events,
        on_chunk=state.editor_cb,
        force=always_run,
    )
    if not outcome.ran:
        return VERDICT_SKIPPED

    state.edited_content = outcome.edited_content
    # 去 AI 腔后的正文是新内容，不能复用旧的完整校验结论。
    state.latest_validator_result = None
    return VERDICT_OK


# ---------------------------------------------------------------------------
# validator：编辑后 / 终审
# ---------------------------------------------------------------------------

@register(ROLE_POST_EDIT)
async def run_post_edit(state: ChapterRunState, node: Any = None) -> str:
    """编辑后校验。要求再走一轮时返回 ``rewrite``。

    注意 ``rewrite_count`` 由 flow 函数自己算出来回填 —— 它可能因为触发了轻度润色
    等分支而与 review 的计数不同，所以这里是赋值而不是加一。
    """
    outcome = await run_post_edit_validation(
        state.db,
        state.novel,
        state.chapter_index,
        state.chapter,
        state.outline,
        state.memory,
        state.draft_content,
        state.edited_content,
        state.rewrite_count,
        state.max_rewrites,
        state.raw_issues,
        state.events,
        validator_agent,
        on_validator_chunk=state.validator_cb,
        on_editor_chunk=state.editor_cb,
        editor_node=editor,
        a5_polisher_used=state.a5_polisher_used,
    )
    state.latest_validator_result = outcome.validator_result
    state.draft_content = outcome.draft_content
    state.edited_content = outcome.edited_content
    state.rewrite_count = outcome.rewrite_count
    state.decision = outcome.decision
    state.validation_errors = outcome.validation_errors
    state.a5_polisher_used = outcome.a5_polisher_used
    if outcome.decision == "blocked":
        return VERDICT_BLOCKED
    return VERDICT_REWRITE if outcome.should_continue else VERDICT_OK


@register(ROLE_FINAL)
async def run_final(state: ChapterRunState, node: Any = None) -> str:
    """终审与字数。

    ``latest_validator_result`` 有值时复用它，不重复烧一次完整校验 —— 这是
    happy path 上省掉的一整次 LLM 调用。强制修正与去 AI 腔会把它置回 None，
    于是新内容一定被重新校验过才发布。
    """
    skip_revalidation = (
        state.start_step == AGENT_EXTRACTOR
        and state.chapter is not None
        and state.chapter.status in (ChapterStatus.VALIDATED, ChapterStatus.POST_PROCESSING)
    )
    if skip_revalidation:
        state.validator_result = state.chapter.validator_result or {"passed": True}
    else:
        await _check_paused(state)
        set_job_step(state.job, AGENT_VALIDATOR, state.chapter, allow_resume=True)
        await state.db.commit()
        await state.events.status(
            AGENT_VALIDATOR, state.chapter_index, "正在进行内容规则校验与字数统计..."
        )
        state.chapter = await get_chapter_by_index(
            state.db, state.novel.id, state.chapter_index
        , domain=state.domain)
        if state.latest_validator_result is not None:
            state.validator_result = state.latest_validator_result
        else:
            state.validator_result = await run_saved_chapter_comprehensive_validation(
                state.db,
                state.novel,
                state.chapter,
                state.chapter_index,
                validator_agent,
                on_validator_chunk=state.validator_cb,
            )

    state.validator_result = await run_final_validator_flow(
        state.db,
        state.novel,
        state.chapter,
        state.chapter_index,
        state.attempt,
        state.validator_result,
        validator_agent,
        state.events,
        on_validator_chunk=state.validator_cb,
    )

    if state.validator_result.get("terminal_block"):
        return VERDICT_BLOCKED
    if not state.validator_result.get("passed"):
        return VERDICT_FAIL
    return VERDICT_OK


# ---------------------------------------------------------------------------
# 发布
# ---------------------------------------------------------------------------

@register(ROLE_PUBLISH)
async def run_publish(state: ChapterRunState, node: Any = None) -> str:
    """把校验结论落定到章节。

    ``auto_force_saved`` 时返回 ``blocked``：正文**已经**落定（不能丢），但要暂停等
    人工复核。这与 ``final`` 的 ``blocked``（尚未落定就拦下）是两件事，顺序反了会丢稿。
    """
    finalize_validated_chapter(state.chapter, state.validator_result)
    await state.db.commit()

    if state.validator_result.get("auto_force_saved"):
        await state.events.status(
            AGENT_VALIDATOR,
            state.chapter_index,
            "本章经过多轮重写后仍需强制保存，已暂停等待人工复核。",
        )
        return VERDICT_BLOCKED
    return VERDICT_OK


# ---------------------------------------------------------------------------
# extractor
# ---------------------------------------------------------------------------

@register(ROLE_POSTPROCESS)
async def run_postprocess(state: ChapterRunState, node: Any = None) -> str:
    """沉淀记忆并发布。

    注意 ``has_extractor=False`` **不是**跳过本步 —— 发布本身在这里面。它只是让内部
    不跑设定提取。把它实现成「图里不含本步」会导致章节永远发布不了。
    """
    from worker_support.orchestrator import check_paused

    await run_chapter_post_processing(
        state.db,
        state.job,
        state.novel,
        state.chapter,
        state.chapter_index,
        has_extractor=state.runtime.has_extractor,
        check_paused=check_paused,
        events=state.events,
    )
    return VERDICT_OK
