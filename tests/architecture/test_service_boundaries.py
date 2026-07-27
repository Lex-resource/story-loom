import ast
from pathlib import Path


def test_services_do_not_import_worker_support():
    services_root = Path(__file__).resolve().parents[2] / "services"
    violations = []
    for path in services_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("worker_support"):
                violations.append(f"{path.name}:{node.lineno}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("worker_support"):
                        violations.append(f"{path.name}:{node.lineno}")
    assert violations == []
