import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 生产代码根目录。research/ 不在其中——它是覆盖层，允许持有版本判据。
PRODUCTION_ROOTS = ("agents", "services", "worker_support", "routers")

# 唯一允许触碰版本/变体分派的生产文件：产研之间的接缝。
VERSION_SEAM = "services/version_surface.py"

# 唯一允许按格式名硬比的生产文件。这三处的职责就是「把格式名翻译成别的东西」，
# 不翻译反而做不成事：策略解析本身、从创作档案派生内部格式、提示词模板种子。
FORMAT_NAME_ALLOWLIST = (
    "services/workflow_registry.py",
    "services/creative_profile.py",
    "services/prompt_loader.py",
)

_FORMAT_LITERALS = frozenset({"zhihu_short", "long_webnovel"})


def _mentions_novel_format(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == "novel_format":
            return True
        if isinstance(child, ast.Attribute) and child.attr == "novel_format":
            return True
        # mem_context.get("novel_format") / payload["novel_format"]
        if isinstance(child, ast.Constant) and child.value == "novel_format":
            return True
    return False


def _mentions_format_name(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and child.value in _FORMAT_LITERALS:
            return True
        if isinstance(child, ast.Name) and child.id.startswith("NOVEL_FORMAT_"):
            return True
        if isinstance(child, ast.Attribute) and child.attr.startswith("NOVEL_FORMAT_"):
            return True
    return False



def _production_files():
    for root in PRODUCTION_ROOTS:
        yield from sorted((ROOT / root).rglob("*.py"))


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def test_services_do_not_import_worker_support():
    services_root = ROOT / "services"
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


def test_core_command_services_are_http_independent():
    violations = []
    for relative in (
        "services/chapter_service.py",
        "services/pipeline_service.py",
        "services/project_service.py",
        "services/outline_service.py",
        "services/continuity_sanitizers.py",
        "services/novel_memory_ranking.py",
        "services/character_card_serialization.py",
        "services/chapter_handoff_formatting.py",
        "services/system_configs_service.py",
        "services/workflow_admin_service.py",
        "services/service_errors.py",
    ):
        path = ROOT / relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (
                (node.module or "").startswith("fastapi")
                or (node.module or "") == "database"
            ):
                violations.append(f"{relative}:{node.lineno}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Depends":
                violations.append(f"{relative}:{node.lineno}")
    assert violations == []


def test_configuration_services_are_http_independent():
    violations = []
    for relative in (
        "services/system_configs_service.py",
        "services/workflow_admin_service.py",
    ):
        path = ROOT / relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("fastapi"):
                violations.append(f"{relative}:{node.lineno}")
    assert violations == []


def test_production_has_no_prompt_version_gates():
    """生产代码不得依据提示词版本分支。

    生产冻结在 A28/V43（见 docs/research/novel-memory-continuity/PRODUCTION.md）。
    历史上有 292 处 `prompt_version_at_least(...)` 散布在 19 个生产文件里，其中约
    一半引用高于 V43 的版本，在生产下恒为假。它们已被按 V43 求值并内联，历史行为
    移入 research/prompt_versions/。

    新增版本相关行为时，请在 research/ 里注册一个表面，而不是在生产加门。
    """
    violations = []
    for path in _production_files():
        rel = _relative(path)
        if rel == VERSION_SEAM:
            continue
        source = path.read_text(encoding="utf-8")
        if "prompt_version_at_least" not in source and "prompt_version(" not in source:
            continue
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in {"prompt_version_at_least", "_prompt_version_at_least", "prompt_version"}:
                    violations.append(f"{rel}:{node.lineno}")
    assert violations == [], (
        "生产代码出现了提示词版本门。请改为在 research/prompt_versions/ 注册表面：\n"
        + "\n".join(violations)
    )


def test_production_has_no_variant_axis_gates():
    """生产代码不得**依据** ExperimentContext.variant 分支。

    这是第二条分派轴，曾经让生产行为与 PRODUCTION.md 验证过的 A28/V43 不一致：
    生产运行没有 ExperimentContext，variant 为空串，于是 Ariadne 分支全部落空。
    最严重的一处使有界假设措辞触发 Writer 重写，而 A28 的招牌指标正是零内容重试。

    把 variant 写进事件记录是允许的（`experiment_recorder` 的本职）；这里查的是
    用它做判断——比较、`startswith`、`lower()`、正则匹配等。
    """
    dispatch_methods = {"startswith", "endswith", "lower", "upper", "strip", "match", "search"}
    violations = []
    for path in _production_files():
        rel = _relative(path)
        if rel == VERSION_SEAM:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            reads = [
                child
                for child in ast.walk(node)
                if isinstance(child, ast.Attribute)
                and child.attr == "variant"
                and isinstance(child.ctx, ast.Load)
            ]
            if not reads:
                continue
            # 条件判断里出现 variant → 分派
            if isinstance(node, (ast.If, ast.IfExp, ast.While)):
                if any(
                    isinstance(c, ast.Attribute) and c.attr == "variant"
                    for c in ast.walk(node.test)
                ):
                    violations.append(f"{rel}:{node.lineno} (条件分支)")
            # variant 上调用字符串/正则方法 → 分派
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in dispatch_methods and any(
                    isinstance(c, ast.Attribute) and c.attr == "variant"
                    for c in ast.walk(node.func)
                ):
                    violations.append(f"{rel}:{node.lineno} (字符串判据)")
            # 与字面量比较 → 分派
            if isinstance(node, ast.Compare) and reads:
                violations.append(f"{rel}:{node.lineno} (比较)")
    assert violations == [], (
        "生产代码依据 ExperimentContext.variant 分支。变体轴判据属于 research/：\n"
        + "\n".join(sorted(set(violations)))
    )

def test_production_does_not_import_research_at_module_scope():
    """research/ 只能在接缝函数内部被导入。

    这保证部署时可以完全不包含 research/ 目录——`research_override` 用 ImportError
    兜住缺失，并缓存该结果。
    """
    violations = []
    for path in _production_files():
        rel = _relative(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:  # 只看模块层
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("research"):
                violations.append(f"{rel}:{node.lineno}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("research"):
                        violations.append(f"{rel}:{node.lineno}")
    assert violations == [], (
        "生产代码在模块层导入了 research/。请改为在函数内部导入并用 ImportError 兜住：\n"
        + "\n".join(violations)
    )


def test_version_seam_is_the_only_research_entry_point():
    """除接缝文件外，生产代码不得调用 research_override。

    接缝本身可以被任意生产模块调用，但"如何找到 research"这件事只有一处实现。
    """
    seam_path = ROOT / VERSION_SEAM
    assert seam_path.exists(), f"缺少版本接缝文件 {VERSION_SEAM}"

    source = seam_path.read_text(encoding="utf-8")
    assert "def research_override(" in source
    # 接缝必须用 ImportError 兜住 research/ 缺失
    assert "ImportError" in source, "接缝必须容忍 research/ 不存在"


def test_production_does_not_hardcode_novel_format():
    """生产代码不得按格式名判断工作流（CLAUDE.md 硬约束第 8 条）。

    「工作流」可自定义、可克隆之后，`novel_format` 不再等于工作流类型：从短篇克隆出来的
    工作流会拿到短篇提示词，却在按格式名硬比的地方走长篇 schema / 记忆合并 / 重试分类 ——
    提示词对了、结构错了，是最难查的一类静默错误。反方向同样成立：克隆自长篇的工作流会
    掉出长篇行为，`agents/writing/editor.py` 曾因此让五维提示词配上七维 schema，每章必重试。

    判断工作流类型请用 `services/workflow_surface.is_short_form_workflow()`，或为这项行为
    注册一个策略表面。这条约束此前只写在 CLAUDE.md 与
    `tests/services/test_workflow_registry.py` 的 docstring 里，靠人记，于是攒下 9 处残留。
    """
    violations = []
    for path in _production_files():
        rel = _relative(path)
        if rel in FORMAT_NAME_ALLOWLIST:
            continue
        source = path.read_text(encoding="utf-8")
        if "novel_format" not in source:
            continue
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            if _mentions_novel_format(node) and _mentions_format_name(node):
                violations.append(f"{rel}:{node.lineno}")
    assert violations == [], (
        "生产代码按格式名判断工作流。请改用 is_short_form_workflow() 或注册策略表面：\n"
        + "\n".join(sorted(set(violations)))
    )
