"""章节生成的叙事域:一次单章生成发生在主线域还是某个支线域。

森林遗留 B1/B2 的迁移基石:适配器链与仓库函数经 domain 参数分派
主线 Chapter 表 / 支线 CharacterBranchChapter 表,而不是各自硬编码。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

STORYLINE_MAIN = "main"


@dataclass(frozen=True)
class ChapterDomain:
    """一次单章生成所属的叙事域。

    - 主线:branch_id=None,storyline_id="main",章节落在 chapters 表
    - 支线:branch_id=支线 id,storyline_id=支线故事线,章节落在
      character_branch_chapters 表;anchor_main_chapter 是创建支线时的
      主线锚点(记忆时间锚定用)
    """

    project_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    storyline_id: str = STORYLINE_MAIN
    anchor_main_chapter: int | None = None

    @property
    def is_branch(self) -> bool:
        return self.branch_id is not None


def mainline_domain(project_id: uuid.UUID) -> ChapterDomain:
    return ChapterDomain(project_id=project_id)
