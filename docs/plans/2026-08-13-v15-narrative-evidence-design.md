# V15 Narrative Evidence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce repeated Validator rewrites caused by evidence-field omissions while improving character portrayal without increasing memory recall or adding model calls.

**Architecture:** Extend the versioned prompt-hint layer with a compact evidence checklist and a character relationship-action contract. Keep V14 as the parent version and gate all new behavior behind V15. Do not change the four-layer memory model or V14 run artifacts.

**Tech Stack:** Python, prompt hint helpers, experiment recorder version gates, pytest, CodeGraph.

---

### Task 1: Add V15 prompt contract tests

**Files:**
- Modify: `tests/test_prompt_utils.py`
- Modify: `tests/test_planner_prompt_contract.py`

1. Add tests proving V15 hints are empty below V15 and present at V15.
2. Assert the compact evidence checklist names metadata source, frame source, device receipt, and physical effect exactly once.
3. Assert the character contract requires goal, choice, consequence, and relationship change without requiring a new agent call.

### Task 2: Implement V15 versioned hints

**Files:**
- Modify: `agents/prompt_hints.py`
- Modify: `services/experiment_recorder.py`

1. Extend the prompt-version gate through V15.
2. Add `v15_compact_evidence_and_character_action_hint(agent_type)`.
3. Keep V14 behavior unchanged for V14 and earlier runs.
4. Wire the hint into the existing Planner, Writer, Editor, Validator, and Extractor prompt assembly paths.

### Task 3: Record the experiment version

**Files:**
- Create: `docs/research/novel-memory-continuity/versions/V15.md`
- Modify: `docs/research/novel-memory-continuity/README.md`
- Modify: `docs/research/novel-memory-continuity/results.md`

1. Document the hypothesis and exact prompt changes before the experiment.
2. Reserve a new independent run directory; do not reuse V14 project or memory.
3. Append final chapter metrics and conclusion after the run.

### Task 4: Verify and run the independent experiment

1. Run focused tests, full pytest, compileall, `codegraph sync`, and `/health`.
2. Confirm the OpenAI provider remains active and backup provider remains disabled.
3. Generate ten chapters in a new project/run using V15.
4. Deduplicate resumed chapter completion events and record the final metrics.
