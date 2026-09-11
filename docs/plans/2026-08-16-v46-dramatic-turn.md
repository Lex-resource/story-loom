# V46 Dramatic Turn Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve long-form chapter character agency and prose quality without increasing model calls or weakening accepted-fact continuity gates.

**Architecture:** Reuse the existing Planner `character_goals` and `beats` output. Normalize those fields into a small deterministic `dramatic_turn` projection containing goal, pressure, choice, consequence, and emotional movement. Expose the projection through the shared Writer execution brief and compact review contract, then add role-specific V46 guidance to Planner, Writer, Editor, Validator, and Extractor. V45 remains the parent behavior for context budgets and authority boundaries.

**Tech Stack:** Python, Pydantic, pytest, local experiment recorder, CodeGraph.

---

### Task 1: Add the V46 prompt-version and deterministic dramatic projection

**Files:**
- Modify: `services/experiment_recorder.py`
- Modify: `services/continuity_contract.py`
- Modify: `services/chapter_continuity.py`
- Test: `tests/test_v46_dramatic_turn.py`

**Step 1: Write the failing test**

Cover prompt version recognition, projection of a character goal and beat, and omission of empty legacy fields.

**Step 2: Run the focused test to verify it fails**

Run: `python -m pytest tests/test_v46_dramatic_turn.py -q`
Expected: FAIL because V46 and the projection do not exist.

**Step 3: Write the minimal implementation**

Extend the version order through V46. Carry `character_goals`, `emotional_arc`, and `beats` into the canonical chapter contract, and render a bounded `dramatic_turn` object in `contract_prompt` and `writer_execution_brief`. Keep only the first primary goal and at most three compact beats; do not add a model call or persistence field.

**Step 4: Run the focused test**

Run: `python -m pytest tests/test_v46_dramatic_turn.py -q`
Expected: PASS.

### Task 2: Add role-specific V46 instructions

**Files:**
- Modify: `agents/prompt_hints.py`
- Modify: `agents/writing/planner.py`
- Modify: `agents/writing/writer.py`
- Modify: `agents/writing/editor.py`
- Modify: `agents/writing/validator_agent.py`
- Modify: `agents/writing/extractor.py`
- Test: `tests/test_v46_dramatic_turn.py`

**Step 1: Write the failing test**

Assert that every writing Agent receives the V46 marker and that Writer/Validator guidance distinguishes a soft dramatic-quality warning from a hard continuity conflict.

**Step 2: Run the focused test to verify it fails**

Run: `python -m pytest tests/test_v46_dramatic_turn.py -q`
Expected: FAIL because no Agent exposes the V46 hint.

**Step 3: Write the minimal implementation**

Add one compact V46 hint function. Select it before V45 in each Agent's existing version branch. Keep V45 context budgets and all hard authority, artifact, location, timeline, and unknown-boundary rules unchanged.

**Step 4: Run focused and regression tests**

Run: `python -m pytest tests/test_v46_dramatic_turn.py tests/test_v45_narrative_delta.py tests/test_v44_compact_input.py -q`
Expected: PASS.

### Task 3: Record and validate the experiment variant

**Files:**
- Create: `docs/research/novel-memory-continuity/ariadne/versions/A32.md`
- Modify: `docs/research/novel-memory-continuity/ariadne/README.md`

Record V46's hypothesis, parent A31, controlled variables, startup gates, and empty-result status. After implementation run CodeGraph sync, compile checks, focused tests, and the broader Python test suite before starting a fresh A32 project from the fixed chapter-1 seed.

