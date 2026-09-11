# V50 Minimal Observation Patch Implementation Plan

**Goal:** Make observation-language repairs deterministic and sentence-local so a narrow evidence-boundary issue cannot cause a broad Editor rewrite or a follow-up Writer retry.

**Architecture:** V50 keeps V49's classification and hard-boundary protection. It adds a shared prompt surface to all five writing agents, explicitly injects that surface into the force-revision path, and builds a repair contract from the Validator's exact evidence and suggested replacement. The repair remains one optional Editor call and is recorded separately from content retries.

**Tech Stack:** Python, existing Agent pipeline, pytest, local experiment recorder, CodeGraph.

---

### Task 1: Extend experiment versioning and prompt coverage

**Files:**
- Modify: `services/experiment_recorder.py`
- Modify: `agents/prompt_hints.py`
- Modify: `agents/writing/planner.py`
- Modify: `agents/writing/writer.py`
- Modify: `agents/writing/editor.py`
- Modify: `agents/writing/validator_agent.py`
- Modify: `agents/writing/extractor.py`
- Test: `tests/test_v50_minimal_observation_patch.py`

Add V50 to the version order and define `v50_minimal_observation_patch_hint`. Route V50 through every writing Agent and ensure `EditorAgent.force_revise_chapter` receives the V50 hint. The hint must require one-sentence-local repair, preservation of all non-target text, and no new facts, identities, causality, locations, items, or events.

### Task 2: Build the narrow repair contract

**Files:**
- Modify: `worker_support/generation_validator_policy.py`
- Modify: `worker_support/generation_editor_flow.py`
- Test: `tests/test_v50_minimal_observation_patch.py`

Add V50-only helpers that accept the existing narrow observation classifier, format the Validator's evidence and fix suggestion as a repair contract, and record whether the local repair was attempted. Keep hard conflicts and mixed issue sets on the existing Writer-retry path. The contract must state that the Editor must preserve every sentence not identified by Validator.

### Task 3: Verify and prepare the next controlled run

**Files:**
- Create: `docs/research/novel-memory-continuity/ariadne/versions/A36.md`
- Modify: `docs/research/novel-memory-continuity/ariadne/README.md`
- Modify: `docs/research/novel-memory-continuity/ariadne/results.md`

Run focused V50 tests, compile checks, the full test suite, and `codegraph sync`. Retain A35's partial raw events. Create a fresh OpenAI-only project from the same fixed published chapter-1 seed, set prompt version V50, and record the startup gate before generating chapters 2-10.

### Verification

- V50 prompt marker appears in Planner, Writer, Editor, Validator, and Extractor snapshots.
- Force revision receives the V50 marker.
- A pure observation-language issue builds a local repair contract; a real accepted-fact, timeline, item, location, or core-event conflict does not.
- Full test suite passes before the experiment starts.
- A36 raw events, prompts, metrics, and final conclusion remain under the local branch and are not pushed.
