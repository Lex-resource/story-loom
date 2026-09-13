"""单章生成的黑板（blackboard）。

`_process_single_chapter` 原本用 **30 个局部变量**在 425 行里传递状态：`draft_content`、
`edited_content`、`rewrite_count`、`decision`、`latest_validator_result`、`raw_issues`、
`a5_polisher_used`…… 每个阶段读一部分、写一部分，靠「谁在谁上面」这件事保证正确。

把编排交给数据驱动的引擎之后这条就不成立了 —— 阶段顺序可以被用户改，于是「哪个阶段
读哪些槽、写哪些槽」必须显式化。本模块就是那份显式契约：一个可变 dataclass，
每个适配器（`worker_support/chapter_steps.py`）声明自己读写哪些字段。

**刻意用 dataclass 而不是 dict**：拼写错误在属性访问时立刻抛 `AttributeError`，
而 dict 会静默返回 `None` —— 在一条要跑五次 LLM 调用的链路上，静默的 None 会一路漂到
提示词里，代价是一整章的 token 加一次人工排查。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.chapter_domain import ChapterDomain
from typing import Any, Callable

# 裁决词表与角色名的唯一来源在 `services/pipeline_stages` —— 图校验器（services/，不得
# 导入 worker_support）与适配器都要用，各写一份迟早漂移。这里重新导出，让
# worker_support 内部不必到处写 `from services.pipeline_stages import ...`。
from services.pipeline_stages import (  # noqa: F401
    ALL_VERDICTS,
    VERDICT_BLOCKED,
    VERDICT_EMPTY,
    VERDICT_FAIL,
    VERDICT_OK,
    VERDICT_REWRITE,
    VERDICT_SKIPPED,
)


@dataclass
class ChapterRunState:
    """一章生成过程中所有跨阶段状态。

    字段名沿用 `_process_single_chapter` 里原本的局部变量名，方便逐行对照 ——
    这次改动是**机械搬迁**，不是重写语义。
    """

    # --- 固定输入（构造后不改） ---
    db: Any
    job: Any
    novel: Any
    chapter_index: int
    attempt: int
    runtime: Any
    events: Any
    project_id: str

    # --- resume 决策（入口前算好，见 generation_start_policy） ---
    start_step: str = "planner"
    use_existing_outline: bool = False
    custom_prompt: str | None = None
    # 叙事域:None=主线;支线 job 携带支线域,仓库/上下文按此分派
    domain: ChapterDomain | None = None
    # 提示词 category 覆盖（工作流「复用别人的提示词」时非空）。解释器把它连同节点的
    # 提示词覆盖一起装进 `services/prompt_scope` 的作用域。
    prompt_category: str | None = None

    # --- 流式回调，按 agent 分频道 ---
    planner_cb: Callable | None = None
    writer_cb: Callable | None = None
    editor_cb: Callable | None = None
    validator_cb: Callable | None = None

    # --- 章节行与上下文 ---
    chapter: Any = None
    skeleton: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    outline: dict[str, Any] = field(default_factory=dict)
    pipeline_context: Any = None
    succeeding_beginning: str = ""
    issue_summaries: str = ""
    planner_previous_ending: str = ""

    # --- write → edit → validate 循环 ---
    draft_content: str | None = None
    edited_content: str | None = None
    rewrite_count: int = 0
    max_rewrites: int = 1
    # "rewrite" / "revise" / "accept" / "none"。注意它**不是**裁决：resume 到 editor 时
    # 由 initial_generation_decision 派生成 "revise"，于是循环跳过 Writer 而直接审阅。
    decision: str = "rewrite"
    validation_errors: str = ""
    # 从 validator/extractor 恢复且已有草稿时为真：整个 write-edit 簇跳过。实现手法是
    # 把 rewrite_count 顶到 max_rewrites，于是图入口边的预算守卫直接走 on_exhausted。
    skip_write_edit: bool = False
    # 已经做过的完整校验结果。有值时终审复用它而不重跑 —— 强制修正与去 AI 腔产出新
    # 内容后必须置回 None，否则会拿旧结论发布新正文。
    latest_validator_result: dict[str, Any] | None = None
    raw_issues: list[dict[str, Any]] = field(default_factory=list)
    a5_polisher_used: bool = False
    editor_result: dict[str, Any] = field(default_factory=dict)
    evaluations: dict[str, Any] = field(default_factory=dict)

    # --- 终态 ---
    validator_result: dict[str, Any] | None = None
