"""S12 验收：生产代码零 print。

stdout 是给人调试用的，生产代码的失败必须进 logger 才能被日志系统
收集（带上下文、可过滤、可落文件）。tests/、scripts/、research/、
alembic/ 不在生产范围。
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_DIRS = ("agents", "services", "worker_support", "routers", "models")
PRODUCTION_FILES = ("main.py", "worker.py", "config.py", "database.py")


def _iter_production_files():
    for dirname in PRODUCTION_DIRS:
        yield from sorted((ROOT / dirname).rglob("*.py"))
    for name in PRODUCTION_FILES:
        path = ROOT / name
        if path.exists():
            yield path


def test_no_print_calls_in_production_code():
    offenders = []
    for path in _iter_production_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert offenders == [], f"生产代码存在 print 调用: {offenders}"
