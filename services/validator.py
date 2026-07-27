import re
from collections import Counter
from typing import Optional

from agents.constants import BLACKLIST, STYLE_BLACKLIST  # re-export for backwards compat

# ---------------------------------------------------------------------------
# Validator tuning constants (previously inline magic numbers).
# ---------------------------------------------------------------------------

# BLACKLIST 已迁移至 agents/constants.py 以避免 agents → services 反向依赖。
# 此处通过 import re-export，已有代码 `from services.validator import BLACKLIST` 仍可工作。

# Characters stripped from the start of title/content to normalize leading
# markdown headings (ASCII '#' and fullwidth '＃').
TITLE_STRIP_CHARS = '#＃'

# A chapter is considered too short if its word count falls below this fraction
# of the target word count.
WORD_COUNT_LOWER_RATIO = 0.75

# Maximum number of trailing chars from the previous chapter compared against
# the start of the current chapter for repetition-overlap detection.
REPEAT_CHECK_MAX_WINDOW = 500

# Overlap (in characters) above which a repetition error is emitted.
REPEAT_OVERLAP_WARNING_THRESHOLD = 50

# Number of decimal places kept when reporting the repeat rate.
REPEAT_RATE_PRECISION = 4

# ---------------------------------------------------------------------------
# Style / cliché density heuristic (Item6+7 detection half).
# Pure, deterministic, LLM-free: cheap enough to run on every chapter and on
# every rerank candidate. It does NOT gate publication on its own — it feeds a
# score the destyle node and candidate reranker consume. The LLM "judge" that
# must quote offending sentences lives in the destyle agent prompt, not here.
# ---------------------------------------------------------------------------

# Cliché hits per this many chars above which prose reads as AI-slop.
STYLE_CLICHE_DENSITY_WINDOW = 1000

# Density (hits per window) at/above which we flag a style problem.
STYLE_CLICHE_DENSITY_THRESHOLD = 2.0

# Sentence-length coefficient of variation below which rhythm is monotonous
# (every sentence the same length is a hallmark of dead LLM prose).
STYLE_LENGTH_CV_MIN = 0.35

# Only assess rhythm once there are enough sentences for variance to mean
# something; below this we skip the CV check to avoid noise on short passages.
STYLE_MIN_SENTENCES_FOR_CV = 8

# --- Sentence-level self-repetition (long-form / high-emotion failure mode) ---
# CV and cliché density both miss the case where an LLM literally re-emits its
# own sentences ("你们准备好了吗" ×6): the phrase isn't blacklisted and mixed
# short/long copies keep CV high. This dimension counts near-identical repeats.

# Sentences shorter than this are ignored — short interjections ("好。", "走。")
# legitimately recur and would inflate the rate as false positives.
STYLE_REPEAT_MIN_SENTENCE_LEN = 6

# Only meaningful once the passage has enough long sentences to have a baseline.
STYLE_REPEAT_MIN_SENTENCES = 20

# Fraction of long sentences that are duplicate re-emissions above which prose
# reads as self-repetitive ("复读"). Calibrated on real long-form output: a
# finale章 that re-emits "你们准备好了吗"×6 etc. lands at ~0.074, while clean
# chapters sit around 0.005 — an order of magnitude below. 0.05 flags the former
# with headroom and never touches the latter.
STYLE_REPEAT_RATE_THRESHOLD = 0.05

# Sentence terminators for splitting (Chinese + ASCII).
_SENTENCE_SPLIT_RE = re.compile(r"[。！？!?…]+[”’\"']?|\n+")


def _split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_SPLIT_RE.split(text or "")
    return [p.strip() for p in parts if p and p.strip()]


def _length_cv(sentences: list[str]) -> float:
    """Coefficient of variation (std/mean) of sentence lengths.

    Higher = more varied rhythm. Returns 0.0 when there is nothing to measure.
    """
    lengths = [len(s) for s in sentences]
    n = len(lengths)
    if n == 0:
        return 0.0
    mean = sum(lengths) / n
    if mean == 0:
        return 0.0
    variance = sum((x - mean) ** 2 for x in lengths) / n
    return (variance ** 0.5) / mean


def _self_repetition(sentences: list[str]) -> tuple[float, dict[str, int]]:
    """Rate of duplicate long sentences + the offending phrases and their counts.

    Only sentences of at least STYLE_REPEAT_MIN_SENTENCE_LEN chars count toward
    the denominator, so recurring short interjections don't inflate the rate.
    Returns (rate, {sentence: count}) where count is the number of extra
    (beyond-first) emissions; empty dict when nothing repeats.
    """
    longs = [s for s in sentences if len(s) >= STYLE_REPEAT_MIN_SENTENCE_LEN]
    if len(longs) < STYLE_REPEAT_MIN_SENTENCES:
        return 0.0, {}
    counts = Counter(longs)
    repeats = {s: c for s, c in counts.items() if c >= 2}
    extra = sum(c - 1 for c in repeats.values())
    rate = extra / len(longs)
    return rate, {s: counts[s] for s in repeats}


def analyze_style(content: str) -> dict:
    """Heuristic AI-slop detector across three dimensions.

    1. cliché density  — STYLE_BLACKLIST phrases per 1000 chars
    2. rhythm monotony — sentence-length coefficient of variation too low
    3. self-repetition — the same long sentence re-emitted verbatim ("复读"),
       the long-form / high-emotion failure mode CV and density both miss.

    Returns a structured report the destyle node / reranker consume. `flagged`
    is True when prose crosses any threshold; `cliche_hits` and
    `self_repetition_hits` name the exact offending phrases/sentences so the LLM
    judge downstream can be forced to quote and rewrite them.
    """
    text = content or ""
    char_count = len(text)

    cliche_counts: dict[str, int] = {}
    total_hits = 0
    for phrase in STYLE_BLACKLIST:
        c = text.count(phrase)
        if c:
            cliche_counts[phrase] = c
            total_hits += c

    density = (total_hits / char_count * STYLE_CLICHE_DENSITY_WINDOW) if char_count else 0.0

    sentences = _split_sentences(text)
    length_cv = _length_cv(sentences)
    monotonous = len(sentences) >= STYLE_MIN_SENTENCES_FOR_CV and length_cv < STYLE_LENGTH_CV_MIN

    repeat_rate, repeat_hits = _self_repetition(sentences)
    self_repetitive = repeat_rate >= STYLE_REPEAT_RATE_THRESHOLD

    flagged = (
        density >= STYLE_CLICHE_DENSITY_THRESHOLD
        or monotonous
        or self_repetitive
    )

    return {
        "flagged": flagged,
        "cliche_hits": cliche_counts,
        "cliche_total": total_hits,
        "cliche_density": round(density, REPEAT_RATE_PRECISION),
        "length_cv": round(length_cv, REPEAT_RATE_PRECISION),
        "sentence_count": len(sentences),
        "monotonous_rhythm": monotonous,
        "self_repetition_rate": round(repeat_rate, REPEAT_RATE_PRECISION),
        "self_repetition_hits": repeat_hits,
        "self_repetitive": self_repetitive,
    }


def style_quality_score(content: str) -> float:
    """0.0–1.0 goodness score for reranking (higher = more human-sounding).

    Combines cliché density (penalized) and rhythm variety (rewarded). Pure and
    deterministic so candidate ranking is reproducible.
    """
    report = analyze_style(content)
    density_penalty = min(report["cliche_density"] / STYLE_CLICHE_DENSITY_THRESHOLD, 1.0)
    rhythm_reward = min(report["length_cv"] / STYLE_LENGTH_CV_MIN, 1.0) if report["sentence_count"] else 0.0
    repeat_penalty = min(report["self_repetition_rate"] / STYLE_REPEAT_RATE_THRESHOLD, 1.0)
    base = (1.0 - density_penalty) * 0.6 + rhythm_reward * 0.4
    return round(max(0.0, base * (1.0 - repeat_penalty)), REPEAT_RATE_PRECISION)


def validate_chapter(
    content: str,
    title: str,
    target_word_count: int,
    previous_content: Optional[str] = None,
) -> dict:
    cleaned_title = title.lstrip(TITLE_STRIP_CHARS).strip() if title else ""
    cleaned_content = content.lstrip(TITLE_STRIP_CHARS).lstrip() if content else ""

    content = cleaned_content
    title = cleaned_title

    errors = []
    warnings = []
    word_count = len(content)

    # 1. Word count check (only minimum, no upper limit)
    if target_word_count > 0:
        lower = int(target_word_count * WORD_COUNT_LOWER_RATIO)
        if word_count < lower:
            errors.append(f"字数 {word_count} 不足，要求至少 {lower} 字")

    # 2. Title check
    if not title or not title.strip():
        errors.append("缺少章节标题")

    # 3. Empty content
    if not content or not content.strip():
        errors.append("章节内容为空")

    # 4. Blacklist check
    for word in BLACKLIST:
        if word in content:
            errors.append(f"包含出戏内容: {word}")

    # 5. Repetition check
    repeat_rate = 0.0
    if previous_content and content:
        # Find the longest matching suffix of previous_content that matches the prefix of content
        limit = min(REPEAT_CHECK_MAX_WINDOW, len(previous_content), len(content))
        overlap = 0
        for l in range(limit, 0, -1):
            if previous_content[-l:] == content[:l]:
                overlap = l
                break
        repeat_rate = overlap / max(len(content), 1)
        if overlap > REPEAT_OVERLAP_WARNING_THRESHOLD:
            errors.append(f"与上一章重复字数过多: {overlap} 字")

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "word_count": word_count,
        "repeat_rate": round(repeat_rate, REPEAT_RATE_PRECISION),
        "cleaned_title": cleaned_title,
        "cleaned_content": cleaned_content,
    }
