"""研究覆盖层的分派入口。

`services/version_surface.research_override` 是生产侧唯一调用点,它把表面名和参数
转发到 `resolve`。每个 handler 返回覆盖值,或返回 `NO_OVERRIDE` 表示让生产代码接管。

新增一个研究版本时:在对应模块里用 `@register("<surface>")` 实现行为,并确保该模块
被本文件末尾导入。生产代码不需要任何改动。
"""
from __future__ import annotations

from research.prompt_versions.registry import (  # noqa: F401
    register,
    registered_surfaces,
    resolve,
)

# 导入各版本模块以触发注册。放在末尾,且注册表位于独立模块,避免循环导入。
from research.prompt_versions import hints  # noqa: E402,F401
from research.prompt_versions import validator_policy  # noqa: E402,F401
from research.prompt_versions import quality_gate  # noqa: E402,F401
from research.prompt_versions import compaction  # noqa: E402,F401
from research.prompt_versions import contract  # noqa: E402,F401
