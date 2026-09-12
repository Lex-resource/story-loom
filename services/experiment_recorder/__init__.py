"""Local, opt-in artifacts for reproducible generation experiments.

The recorder deliberately stays outside the business database. A generation
job opts in through ``job.params.experiment``; ordinary production runs incur
no file writes. Prompt and response snapshots are local research artifacts
and never contain provider secrets.

本包只负责**运行记录**。版本/变体分派曾经也在这里，现已移到
``research/prompt_versions/version_order.py``——生产冻结在 A28/V43，分派判据
只对研究运行有意义。生产代码不应再需要"当前是哪个版本"这个问题的答案。

内部按职责分模块:_io(写盘)/_context(上下文)/_events(事件流)/
_manifest(清单快照)/_publication(发布收尾);本文件再导出完整公共面,
现有 `from services.experiment_recorder import X` 全部保持可用。
"""

from services.experiment_recorder._context import (  # noqa: F401
    ExperimentContext,
    activate,
    adeactivate,
    context_from_job,
    current,
    deactivate,
)
from services.experiment_recorder._events import (  # noqa: F401
    record_chapter_finished,
    record_content_retry,
    record_event,
    record_json_recovery,
    record_llm_attempt,
    record_prompt_template,
)
from services.experiment_recorder._manifest import (  # noqa: F401
    arecord_run_manifest,
    code_snapshot,
    provider_snapshot,
    record_run_manifest,
)
from services.experiment_recorder._publication import (  # noqa: F401
    arecord_published_chapter,
    record_published_chapter,
)

# 共享可变 IO 状态:再导出的是同一对象(不是拷贝),包内外增删可见。
from services.experiment_recorder._io import (  # noqa: F401
    _await_io_work,
    _io_executor,
    _pending_writes,
    _pending_writes_lock,
)

__all__ = [
    "ExperimentContext",
    "activate",
    "adeactivate",
    "arecord_published_chapter",
    "arecord_run_manifest",
    "code_snapshot",
    "context_from_job",
    "current",
    "deactivate",
    "provider_snapshot",
    "record_chapter_finished",
    "record_content_retry",
    "record_event",
    "record_json_recovery",
    "record_llm_attempt",
    "record_prompt_template",
    "record_published_chapter",
    "record_run_manifest",
]
