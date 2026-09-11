# V20 Low-Retry Continuity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore V12-level content retry behavior while retaining only the useful cross-chapter state protections from V19.

**Architecture:** V20 keeps the cumulative authority and evidence-surface rules through V12, but replaces V19's aggressive prompt budgets with V10/V12 budgets. Cross-chapter window and countdown state remains deterministic, while evidence-surface omissions and terminology warnings are handled as local Editor fixes rather than Writer rewrites unless they create a real fact conflict.

**Tech Stack:** Python, pytest, local experiment recorder, CodeGraph, PostgreSQL-backed generation worker.

---

### Task 1: Add V20 version gates and research artifacts

**Files:**
- Modify: `services/experiment_recorder.py`
- Modify: `services/continuity_contract.py`
- Modify: `services/context_compaction.py`
- Create: `docs/research/novel-memory-continuity/versions/V20.md`
- Modify: `docs/research/novel-memory-continuity/README.md`

Add V20 to version recognition, keep the deterministic cross-chapter state contract, and use the V10/V12 context budgets. Record the hypothesis and no-shared-memory experiment requirement.

### Task 2: Add focused regression tests

**Files:**
- Modify: `tests/services/test_context_compaction.py`
- Modify: `tests/test_planner_prompt_contract.py`
- Modify: `tests/test_provider_and_experiment.py`

Test V20 budget selection, short state rules, and that a source-surface wording warning does not request a Writer retry while a real item-state conflict still does.

### Task 3: Implement V20 prompt and retry policy

**Files:**
- Modify: `agents/prompt_hints.py`
- Modify: `worker_support/generation_validator_policy.py`
- Modify: `agents/writing/planner.py`
- Modify: `agents/writing/writer.py`
- Modify: `agents/writing/editor.py`
- Modify: `agents/writing/validator_agent.py`
- Modify: `agents/writing/extractor.py`

Add a compact V20 state hint and make it explicit that evidence-surface completeness is a local repair concern unless it contradicts an accepted fact, item state, or chapter contract. Preserve V19 artifacts and behavior for V19 runs.

### Task 4: Verify implementation

Run focused tests, full pytest, compileall, `codegraph sync`, and the backend health check. Do not modify the archive or commit/push.

### Task 5: Run V20 experiment

Create a new independent project and run ten chapters with the OpenAI provider, no fallback provider, a fresh memory snapshot, and a new run directory. Save prompts, responses, events, quality scores, and final conclusion locally.
