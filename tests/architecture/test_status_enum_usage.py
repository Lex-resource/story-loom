"""架构守恒:chapter/novel/job 等实体的 status 赋值必须走 core.pipeline_vocab 枚举。

背景(森林文档树 A2):worker_support 曾有 7 处 `chapter.status = "draft"` 这类
裸字符串赋值,绕过 `ChapterStatus`。StrEnum 与字符串相等所以运行时不报错,
但拼写错误、重构搜索、和词汇层的单一来源全部失效。本测试禁止生产代码里
对 `.status` 属性做字符串字面量赋值。

排除:枚举定义文件本身(core/)。
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_ROOTS = ("agents", "services", "worker_support", "routers")


def _status_string_assignments():
    violations = []
    for root in PRODUCTION_ROOTS:
        for path in sorted((ROOT / root).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if isinstance(target, ast.Attribute) and target.attr == "status":
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                            violations.append(f"{path.relative_to(ROOT)}:{node.lineno} = {node.value.value!r}")
    return violations


def test_status_assignments_use_enums_not_string_literals():
    violations = _status_string_assignments()
    assert violations == [], (
        "status 赋值必须使用 core.pipeline_vocab 的枚举(ChapterStatus/NovelStatus/JobStatus),"
        f"发现裸字符串赋值: {violations}"
    )
