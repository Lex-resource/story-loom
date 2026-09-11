# V66 Compact Character Texture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test whether a compact generation prompt that foregrounds concrete character choice and visible cost can raise V65's character portrayal and writing quality without increasing retries or model calls.

**Architecture:** Keep V65's evidence-boundary classifier, local Editor repair, layered memory, provider routing, and chapter pipeline unchanged. For the V66 experiment only, replace the chained generation hint surface with a concise role-specific execution surface; Validator and Extractor retain concise hard-authority rules. No schema, memory layer, frontend surface, or dedicated model call is added.

**Tech Stack:** Python, prompt-version gates, local experiment recorder, pytest, CodeGraph, PostgreSQL-backed worker.

---

### Task 1: Add the V66 prompt gate

**Files:**
- Modify: `services/experiment_recorder.py`
- Modify: `agents/prompt_hints.py`
- Test: `tests/test_v66_compact_character_texture.py`

1. Extend prompt version recognition through `V66`.
2. Add a compact role-specific V66 hint and dispatch it before V65.
3. Assert V65 remains unchanged when the active version is V65.
4. Assert all five roles receive the V66 marker, while the Writer receives character texture, one-choice, visible-cost, and no-repeat rules.

### Task 2: Verify the controlled code change

Run:

```powershell
pytest -q tests/test_v65_evidence_boundary.py tests/test_v66_compact_character_texture.py tests/test_provider_and_experiment.py
python -m compileall -q agents services worker_support tests
codegraph sync
```

Expected: all selected tests pass, compilation succeeds, and CodeGraph reports the modified files synchronized.

### Task 3: Run the isolated V66 experiment

Use the OpenAI provider as the sole provider, disable backup and hybrid recall, use local Chroma embeddings, copy only the fixed chapter-1 seed into a fresh project and memory namespace, and generate chapters 2-10. Use run ID `ariadne-a52-v66-compact-character-texture-10ch-20260816`. Preserve rendered prompts, raw responses, events, metrics, and the V65 artifacts.

### Task 4: Evaluate and archive

Compare V66 with V65 on all seven dimensions, content/API/JSON retries, local repair count, LLM calls, tokens, context size, and wall-clock time. Append the final result to `docs/research/novel-memory-continuity/ariadne/results.md` and `versions/A52.md`; do not overwrite V65 or push the local branch.
