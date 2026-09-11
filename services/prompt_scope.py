"""提示词解析作用域。

一个自定义工作流可能想：

* **复用**别人的提示词（自己不维护一套）—— 覆盖 `category`
* 给某个步骤**换一份**提示词（「毒舌版审稿」「口语化重写」）—— 覆盖提示词**名字**
* 同一角色在图里出现多次、各用不同提示词 —— 所以覆盖必须是**逐步骤**的，
  不能只是工作流级的一张静态表

三件事都归结为一个问题：调用点写死了提示词名（`agents/constants.py` 的
`PROMPT_EDITOR_REVIEW` 之类，共 20 处调用），而 category 一律是 `novel_format`。
本模块用 contextvar 在**唯一解析点**（`agents/base.AgentBase.get_prompt_template`）
把这两个值改掉，于是那 20 处调用点一行都不用改。

用 contextvar 而不是参数透传：提示词名要从图的步骤一路传到 agent 方法内部，中间要穿过
`run_editor_review` → `EditorAgent.review_chapter` → `get_prompt_template` 三层，
每层都加一个 `prompt_name=None` 形参是纯噪音。contextvar 在 asyncio 里天然按任务隔离，
并发生成多个章节不会串。

作用域为空（长篇、以及所有没有自定义节点的工作流）时 `resolve` 原样返回 ——
长篇提示词的解析路径完全不变。
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Iterator, Mapping


@dataclass(frozen=True)
class PromptScope:
    """当前生效的提示词覆盖。

    Attributes:
        category: 覆盖提示词 category（`prompt_templates.category`）。
            `None` 表示用调用点传入的 `novel_format`。
        names: `内置提示词名 -> 覆盖名`。只覆盖表里有的，其他原样。
    """

    category: str | None = None
    names: Mapping[str, str] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return self.category is None and not self.names


EMPTY_SCOPE = PromptScope()

_scope: ContextVar[PromptScope] = ContextVar("prompt_scope", default=EMPTY_SCOPE)


def current() -> PromptScope:
    return _scope.get()


def activate(scope: PromptScope) -> Token:
    return _scope.set(scope)


def deactivate(token: Token) -> None:
    _scope.reset(token)


@contextmanager
def scoped(scope: PromptScope) -> Iterator[None]:
    token = activate(scope)
    try:
        yield
    finally:
        deactivate(token)


def resolve(name: str, category: str) -> tuple[str, str]:
    """把 (提示词名, category) 按当前作用域解析成实际要加载的一对。

    **只能调用一次**（在 `agents/base.AgentBase.get_prompt_template` 里）。重复调用
    在病态映射下会来回翻：若一个工作流把审稿节点指向 `editor_destyle`、把去 AI 腔节点
    指向 `editor_review`，映射就是 `{editor_review: editor_destyle,
    editor_destyle: editor_review}`，套两次等于没换。
    """
    scope = _scope.get()
    if scope.is_empty():
        return name, category
    return scope.names.get(name, name), scope.category or category
