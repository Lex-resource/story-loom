# V54 Intra-Chapter Action Repair Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce content retries caused by repeated operations and over-asserted unknown labels while preserving V53's successful cross-chapter stage boundary.

**Architecture:** Extend the existing chapter contract with a bounded unique-action ledger derived from the Planner outline. Add a shared V54 prompt surface that makes each operation single-use within a chapter and keeps unknown UI labels observational. Route only these two sentence/action-local Validator issue classes through the existing Editor repair path; hard fact, timeline, location, and core-event conflicts still require Writer retry or blocking. No new model call is added to the default pipeline, database schema, memory layer, or frontend.

**Tech Stack:** Python, Pydantic, existing continuity contract, existing Editor local-repair flow, pytest, CodeGraph.

---

### Task 1: Record V53 boundary and add contract tests

**Files:**
- Modify: `agents/writing_schemas.py`
- Modify: `services/continuity_contract.py`
- Test: `tests/test_v54_intra_chapter_action_repair.py`

1. Add a bounded `unique_action_ledger` outline field accepting strings or structured action objects.
2. Normalize it into the compact chapter contract and render it for Planner, Writer, Editor, and Validator.
3. Test that duplicate/empty action entries are bounded and that V53 fields remain present.

### Task 2: Add the shared V54 prompt surface

**Files:**
- Modify: `agents/prompt_hints.py`
- Modify: `agents/writing/planner.py`
- Modify: `agents/writing/writer.py`
- Modify: `agents/writing/editor.py`
- Modify: `agents/writing/validator_agent.py`
- Modify: `agents/writing/extractor.py`
- Test: `tests/test_v54_intra_chapter_action_repair.py`

1. Register V54 after V53 and inherit all V53 hints.
2. Require Planner to list each device/query/verification/entry operation once and map it to one response and one resulting change.
3. Require Writer to execute each listed operation at most once; later scenes may observe, choose, or interpret the response but may not resubmit the same operation.
4. Require all agents to render unknown field types as `待判定`/`未返回`, never as a confirmed property such as `不可见`.
5. Require Extractor to persist only the operation's first observed response and the actual new change.

### Task 3: Route narrow local issues to Editor repair

**Files:**
- Modify: `worker_support/generation_validator_policy.py`
- Modify: `worker_support/generation_editor_flow.py`
- Test: `tests/test_v54_intra_chapter_action_repair.py`

1. Add a V54 detector for same-operation resubmission and unknown-label over-assertion.
2. Reuse the existing local Editor repair and revalidation path with a V54 sentence/action-local contract.
3. Keep content retries enabled when an issue also contains a hard accepted-fact, timeline, location, or core-event conflict.
4. Test that V54 local issues do not call the Writer retry path, while mixed hard conflicts still do.

### Task 4: Verify, archive, and run A40

**Files:**
- Create: `docs/research/novel-memory-continuity/ariadne/versions/A40.md`
- Modify: `docs/research/novel-memory-continuity/ariadne/results.md`

1. Run focused V54/V53 tests, regression tests, compile checks, `git diff --check`, and CodeGraph sync/query/impact.
2. Create a new project from the fixed chapter-1 seed with a new memory namespace; use OpenAI-only, backup disabled, hybrid recall disabled, and start at chapter 2.
3. Record every prompt, response, memory snapshot, quality score, wall-clock metric, API retry, JSON recovery, and content retry under a new A40 run directory.
4. Stop on the first hard conflict or rewrite-budget pause; preserve all partial artifacts and do not modify the compressed backup or push GitHub.
