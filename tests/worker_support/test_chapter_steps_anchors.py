"""resume 锚点的 AST 检查。

**硬约束**：``job.current_step`` / ``chapter.pipeline_step`` 的取值域只能是那 5 个
agent 名。这是存量在飞项目零迁移的全部依据 —— 细粒度阶段（11 个角色）怎么编排都不
影响恢复，正因为锚点被限制在这 5 个值里。

为什么用 AST 而不是运行期断言：锚点是 ``set_job_step`` 的**调用参数**，只有真的把那条
分支跑到才会暴露。golden trace 覆盖了 20 个场景，但它 stub 掉了 ``set_job_step``，
而且新加一个适配器时很容易写出一条测试没走到的分支。直接读源码则一个都跑不掉。

也不用「在适配器上声明 anchor」那种做法：那是第二份同样的事实，而没人读的重复事实
迟早和真正的调用漂移。
"""
from __future__ import annotations

import ast
import pathlib

from agents.constants import (
    AGENT_EDITOR,
    AGENT_EXTRACTOR,
    AGENT_PLANNER,
    AGENT_VALIDATOR,
    AGENT_WRITER,
)
from services.chapter_graph import VALID_ANCHORS

SOURCE = pathlib.Path(__file__).resolve().parents[2] / "worker_support" / "chapter_steps.py"

# 源码里允许出现的锚点写法：AGENT_* 常量名。字面量字符串一律不允许 ——
# 写成 "wirter" 这种拼写错误会让恢复静默走到一个不存在的步骤。
ALLOWED_CONSTANT_NAMES = {
    "AGENT_PLANNER": AGENT_PLANNER,
    "AGENT_WRITER": AGENT_WRITER,
    "AGENT_EDITOR": AGENT_EDITOR,
    "AGENT_VALIDATOR": AGENT_VALIDATOR,
    "AGENT_EXTRACTOR": AGENT_EXTRACTOR,
}


def _set_job_step_calls() -> list[ast.Call]:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "set_job_step"
    ]


def test_source_actually_sets_job_steps():
    """先确认检查对象存在 —— 否则这个文件会因为找不到调用而空转通过。"""
    assert len(_set_job_step_calls()) >= 3


def test_every_anchor_is_one_of_the_five_agent_names():
    for call in _set_job_step_calls():
        assert len(call.args) >= 2, f"set_job_step 缺少锚点参数（行 {call.lineno}）"
        anchor_node = call.args[1]
        assert isinstance(anchor_node, ast.Name), (
            f"行 {call.lineno}：锚点必须写成 AGENT_* 常量，不能是字面量或表达式 —— "
            f"拼错一个字母就会让恢复走到不存在的步骤"
        )
        assert anchor_node.id in ALLOWED_CONSTANT_NAMES, (
            f"行 {call.lineno}：{anchor_node.id!r} 不是允许的锚点常量；"
            f"只能用 {'、'.join(sorted(ALLOWED_CONSTANT_NAMES))}"
        )


def test_allowed_constants_match_the_graph_models_anchor_vocabulary():
    """两处词表必须一致：图里的 `@pause:<锚点>` 与适配器推进的章节状态是同一个值域。"""
    assert set(ALLOWED_CONSTANT_NAMES.values()) == set(VALID_ANCHORS)
