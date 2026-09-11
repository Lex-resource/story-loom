# V49 Observation Language Repair Implementation Plan

**Goal:** Reduce unnecessary Writer retries caused by turning interface observations into confirmed history, identity, or causality.

**Architecture:** Add a role-specific V49 prompt surface with concrete safe/unsafe wording. When Validator reports only this narrow issue class, the existing Editor performs one targeted local repair and the chapter is revalidated; the repair is recorded as `local_editor_repair` and is not counted as a content retry. Any real fact, timeline, location, item, or core-event conflict continues through the existing Writer-retry/blocking policy.

**Tech Stack:** Python, existing Agent pipeline, pytest, local experiment recorder, CodeGraph.

---

## Trigger

A34/V48 paused chapter 2 after three Writer retries. The text repeatedly upgraded a displayed label into a real historical record, then into an actual sender/request and causal explanation. The memory merge itself produced no conflict.

## Tasks

1. Add `v49_observation_language_hint` and route Planner, Writer, Editor, Validator, and Extractor through it for V49+.
2. Classify only pure observation-to-history/causality wording issues as V49 local-repair candidates.
3. Add one targeted Editor repair and Validator recheck before the normal Writer retry path.
4. Record local repair events separately from content retries.
5. Add unit tests for prompt coverage and protection of hard-boundary conflicts.
6. Run a fresh OpenAI-only A35 experiment from the fixed chapter-1 snapshot.

## Evaluation

A35 is useful only if the Prompt gate passes, the first observation-language issue is repaired without `content_retry`, and hard conflicts remain blocking. Record extra Editor calls explicitly; do not claim the API cost decreased if local repair is used.
