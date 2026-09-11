"""短篇 Validator 判定语言与执行语言必须一致。

短篇 validator 模板要求 LLM 用 `logic|consistency|pacing|payoff|viewpoint`
(`prompts/validation/zhihu_short_validation.json`)，短篇表面宣布只有四类构成 block。
在格式轴接管重试词表之前，`viewpoint` 与 `payoff` 都不在长篇词表里，
`requires_content_retry` 因此返回 False，缺陷正文走 force_save 直接落盘。
"""
from services.validation_constants import RETRYABLE_CATEGORIES
from worker_support.generation_validator_policy import requires_content_retry

SHORT = "zhihu_short"
LONG = "long_webnovel"


def _blocked(category: str, description: str) -> dict:
    """一个只含单条阻断级问题的失败校验结果。

    描述刻意避开 `_V43_HYPOTHESIS_TERMS`（假设/待核实/candidate/unknown）、
    `_V20_LOCAL_REPAIR_TERMS`（字段缺失/未登记/术语混用…）与 `_V40_SOFT_CONTRACT_TERMS`
    ——那三张表会把问题分流到局部修复路径，与本文件要测的类别判定无关。
    """
    return {
        "passed": False,
        "errors": [f"[{category}] {description}"],
        "hard_issues": [
            {"category": category, "description": description, "severity": "block"}
        ],
    }


def test_short_form_viewpoint_block_retries():
    """人称越权是短篇四种 block 之一，必须能退回 Writer。"""
    result = _blocked("viewpoint", "第一人称叙述里越权描写了他人内心")
    assert requires_content_retry(result, SHORT) is True


def test_short_form_payoff_block_retries():
    """开篇承诺被违背是短篇四种 block 之一，必须能退回 Writer。"""
    result = _blocked("payoff", "开篇许诺的悬念到结尾没有兑现")
    assert requires_content_retry(result, SHORT) is True


def test_short_form_pacing_block_never_retries():
    """节奏问题一律观察项：短篇表面明说不得单独触发重写。"""
    result = _blocked("pacing", "第二节推进偏快")
    assert requires_content_retry(result, SHORT) is False


def test_long_form_baseline_unchanged():
    """长篇词表里没有这两类，行为必须与 A28/V43 前完全一致。"""
    assert requires_content_retry(_blocked("viewpoint", "越权描写"), LONG) is False
    assert requires_content_retry(_blocked("payoff", "承诺没有兑现"), LONG) is False
    assert requires_content_retry(_blocked("pacing", "推进偏快"), LONG) is False


def test_shared_categories_retry_on_both_workflows():
    """两个工作流共有的类别不受格式轴影响。"""
    for novel_format in (SHORT, LONG):
        assert requires_content_retry(_blocked("logic", "反转在全文中找不到铺垫"), novel_format) is True
        assert requires_content_retry(_blocked("consistency", "与前文分节的事实冲突"), novel_format) is True


def test_missing_novel_format_falls_back_to_long_form_baseline():
    """调用点忘了传格式时保守处理，不擅自放宽判定。"""
    assert requires_content_retry(_blocked("viewpoint", "越权描写")) is False
    assert requires_content_retry(_blocked("logic", "反转找不到铺垫")) is True


def test_short_form_categories_are_a_superset_of_the_baseline():
    """短篇是在长篇基线上扩展，不是另起一套 —— 否则长篇类别会在短篇里静默失效。"""
    from services.short_form_surfaces import short_retry_categories

    short = short_retry_categories()
    assert RETRYABLE_CATEGORIES <= short
    assert {"viewpoint", "payoff"} <= short
    assert "pacing" not in short


def test_passed_result_never_retries():
    assert requires_content_retry({"passed": True, "hard_issues": []}, SHORT) is False


def test_failed_errors_without_structured_issues_retries():
    assert requires_content_retry({"passed": False, "errors": ["法则拦截"]}, SHORT) is True


def test_unknown_block_category_retries():
    result = _blocked("unclassified_rule", "违反未登记的内容法则")
    assert requires_content_retry(result, SHORT) is True
