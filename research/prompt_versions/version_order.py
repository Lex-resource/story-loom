"""版本与变体轴的分派判据。

这两条轴原先散布在生产代码里(`services/experiment_recorder.prompt_version_at_least`
共 292 处调用,以及 6 处 `ExperimentContext.variant` 检查)。生产已冻结在 A28/V43,
因此判据本身只对研究运行有意义,整体移入本模块。

生产侧不再引用这里的任何函数——它只通过 `services/version_surface.resolve` 的
返回值感知覆盖层的存在。
"""
from __future__ import annotations

import re

from services.experiment_recorder import current

# 生产冻结点。研究覆盖层只在活动版本/变体**偏离**该冻结点时才接管。
PRODUCTION_PROMPT_VERSION = "V43"
PRODUCTION_ARIADNE_SERIES = 28

_PROMPT_VERSION_ORDER = {f"V{index}": index for index in range(0, 67)}

_ARIADNE_VARIANT = re.compile(r"ariadne-a(\d+)(?:-|$)")


def prompt_version() -> str:
    """活动提示词版本。

    没有 `ExperimentContext` 时返回生产冻结版本——生产不再从 settings 读取该值。
    """
    context = current()
    if context is not None:
        return context.prompt_version
    return PRODUCTION_PROMPT_VERSION


def version_number(version: str) -> int:
    return _PROMPT_VERSION_ORDER.get(version.upper(), 0)


def prompt_version_at_least(version: str) -> bool:
    return version_number(prompt_version()) >= version_number(version)


def active_variant() -> str:
    context = current()
    return str(getattr(context, "variant", "") or "").lower() if context is not None else ""


def ariadne_series() -> int | None:
    """活动 Ariadne 变体的序号。

    没有 `ExperimentContext` 时返回生产冻结的序号(A28)——与 `prompt_version()`
    返回 `PRODUCTION_PROMPT_VERSION` 的语义一致:"无上下文"就是"生产",而生产
    冻结在 A28/V43。这样无论有没有 context,生产路径的两条轴都解析到同一点。

    非 Ariadne 变体(有 context 但 variant 不匹配)返回 None。

    注意生产代码里历史上存在两种写法:数值比较(`A>=7`)与前缀匹配
    (`startswith("ariadne-a5")`)。两者在 `ariadne-a28` 下结论相反,
    所以本模块把两种判据分开暴露,不做统一。
    """
    if current() is None:
        return PRODUCTION_ARIADNE_SERIES
    match = _ARIADNE_VARIANT.match(active_variant())
    return int(match.group(1)) if match else None


def ariadne_series_at_least(series: int) -> bool:
    """数值判据:活动 Ariadne 序号 >= series。"""
    current_series = ariadne_series()
    return current_series is not None and current_series >= series


def variant_startswith(prefix: str) -> bool:
    """前缀判据。与 `ariadne_series_at_least` 不等价——见上。"""
    return active_variant().startswith(prefix)


def is_production_frozen_point() -> bool:
    """活动上下文是否就是生产冻结点(A28/V43)。

    为真时研究覆盖层必须让路,由生产代码给出结果——这保证 pin A28/V43 的
    研究复现与生产走同一条路径。
    """
    if current() is None:
        return True
    if prompt_version().upper() != PRODUCTION_PROMPT_VERSION:
        return False
    return ariadne_series() == PRODUCTION_ARIADNE_SERIES
