# V53 Cross-Chapter Stage Ledger Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Prevent a new chapter from replaying the previous chapter's completed action, response, or terminal state by exposing a deterministic completed-event ledger and requiring a concrete stage delta.

**Architecture:** Extend the existing deterministic `ChapterHandoff` projection with a compact `completed_event_ledger` and `previous_terminal_state`. Extend the existing chapter contract with `new_stage_delta` and a prohibition against replaying completed events. Keep the change prompt-only and projection-only: no new model call, database table, memory layer, or frontend surface.

**Tech Stack:** Python, Pydantic schemas, SQLAlchemy handoff projection, pytest, CodeGraph.

---

### Task 1: Add deterministic completed-event projection

**Files:**
- Modify: `services/chapter_continuity.py`
- Test: `tests/test_v53_cross_chapter_stage_ledger.py`

Steps:
1. Add `completed_event_ledger` and `previous_terminal_state` to `ChapterHandoff`.
2. Derive the ledger from the previous chapter's accepted outline fields, accepted memory state changes, and terminal scene state without calling an LLM.
3. Include a bounded projection in the V30 handoff prompt and Writer execution brief.
4. Test that completed actions and terminal state survive projection and that the projection remains bounded.

### Task 2: Add V53 contract fields and normalization

**Files:**
- Modify: `services/continuity_contract.py`
- Modify: `agents/writing_schemas.py`
- Test: `tests/test_v53_cross_chapter_stage_ledger.py`

Steps:
1. Add `new_stage_delta` to the chapter outline schema.
2. Build a V53 contract containing the previous completed ledger, previous terminal state, and the required new stage delta.
3. Render these fields through the compact contract used by Writer, Editor, and Validator.
4. Test replay detection inputs and non-empty stage-delta rendering.

### Task 3: Add shared V53 prompts

**Files:**
- Modify: `agents/prompt_hints.py`
- Modify: `agents/writing/planner.py`
- Modify: `agents/writing/writer.py`
- Modify: `agents/writing/editor.py`
- Modify: `agents/writing/validator_agent.py`
- Modify: `agents/writing/extractor.py`
- Test: `tests/test_v53_cross_chapter_stage_ledger.py`

Steps:
1. Add a version-gated V53 hint inheriting V52.
2. Require Planner to output a non-empty `new_stage_delta` and avoid completed actions.
3. Require Writer to briefly bridge the prior terminal state and move into a new stage, location, investigation entry, relationship state, or risk state.
4. Require Editor and Validator to treat replay/no-stage-delta as a continuity issue and preserve the low-retry distinction between local repair and Writer rewrite.
5. Require Extractor to record only new stage changes and mark inherited/replayed material as non-new.

### Task 4: Verify and archive

**Files:**
- Create: `docs/research/novel-memory-continuity/ariadne/versions/A39.md`
- Modify: `docs/research/novel-memory-continuity/ariadne/results.md`

Steps:
1. Run the V53 focused tests, compile checks, and `git diff --check`.
2. Run CodeGraph status/query/impact for the changed symbols.
3. Record V53's hypothesis, exact prompt surface, inherited evidence, and runtime gate in A39.
4. Start a fresh A39 project and retain all prompts, responses, metrics, and partial results under the existing local research directory.
