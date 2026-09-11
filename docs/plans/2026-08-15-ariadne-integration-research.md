# Ariadne Integration Research Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Determine, with source-level evidence and controlled experiments, which Ariadne ideas can improve the current layered novel-memory pipeline without importing Ariadne code, increasing default model calls, or weakening the V12 production baseline.

**Architecture:** Keep the current FastAPI + PostgreSQL + Chroma architecture and treat Ariadne as an external reference repository pinned at a local commit. Evaluate four additive capabilities independently: agent-specific context bundles, narrative event/segment projections, provenance-aware conflict handling, and atomic memory publication. Optional critic/polisher workflow nodes and hybrid retrieval are gated experiments, not production defaults.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy async/PostgreSQL, Chroma, pytest, CodeGraph, Git. Ariadne source is Rust/.NET and remains outside the product repository.

---

## Constraints and Archive Rules

- Ariadne checkout: `<本地路径>/Ariadne`.
- Pinned source commit: `480065e77a433d490aaa4671c0f65b44bc0919f3`.
- Ariadne is licensed under PolyForm Noncommercial License 1.0.0. Do not copy source, prompts, resource files, or schema implementations into the product repository. Record design references and links only.
- Work remains on the existing local branch `codex/novel-memory-tencentdb`; do not push to GitHub.
- Existing `V0`-`V24` research records and compressed backups are immutable. Ariadne experiments use a separate archive namespace: `docs/research/novel-memory-continuity/ariadne/`.
- Every experiment stores the hypothesis, parent version, code commit, Ariadne commit, prompt snapshot, rendered context, raw model output, metrics, and conclusion. Never overwrite a previous version.
- Run `codegraph sync` before any product-code change and record the resulting status in the research log.

## Research Questions

1. Can a structured `AgentContextBundle` reduce irrelevant context and content retries while preserving V12 quality?
2. Can story events, story segments, and stage summaries improve plot-thread and foreshadowing continuity without adding a model call per chapter?
3. Which facts should remain candidates or enter a conflict queue instead of being promoted to accepted memory?
4. Can one PostgreSQL transaction keep evidence, atoms, character current state, scene blocks, narrative projections, and publication state consistent?
5. Does deterministic PostgreSQL full-text retrieval add enough recall over Chroma to justify hybrid retrieval?
6. Do optional Detail/Critic/Prudent/Polisher nodes improve quality enough to justify their additional calls and failure surface?

## Phase 0: Snapshot and Source Inventory

### Task 0.1: Freeze the external reference

**Files:**
- Read: `<本地路径>/Ariadne/README.md`
- Read: `<本地路径>/Ariadne/LICENSE`
- Read: `<本地路径>/Ariadne/COMMERCIAL_LICENSE.md`
- Archive: `docs/research/novel-memory-continuity/ariadne/source-snapshot.md`

Record the clone path, remote URL, branch, commit, commit date, license, and the rule that Ariadne is a reference-only checkout.

### Task 0.2: Map Ariadne's source contracts

Inspect and summarize:

- `core/src/rag/context.rs`: per-agent context assembly.
- `core/src/rag/models.rs`: context sections, sources, summary pipeline contracts.
- `core/src/rag/memory.rs`: story segments, events, summaries, atomic publication.
- `core/src/knowledge/models.rs` and `core/src/knowledge/service.rs`: versioned facts, proposals, approval, conflicts.
- `core/src/retrieval/hybrid.rs`: vector/full-text fusion, metadata filters, RRF, reranking.
- `core/src/retrieval/query.rs` and `core/src/retrieval/lifecycle.rs`: query scope and rebuild behavior.

Archive only design findings and source links, never copied implementation text.

## Phase 1: Current-System Mapping

### Task 1.1: Produce the context ownership map

**Files:**
- Read: `services/memory_manager.py`
- Read: `services/novel_memory_recall.py`
- Read: `services/chapter_continuity.py`
- Read: `services/continuity_contract.py`
- Read: `agents/pipeline_context.py`
- Read: `worker_support/generation_outline.py`
- Read: `worker_support/generation_writer_flow.py`
- Read: `worker_support/generation_validation_flow.py`
- Archive: `docs/research/novel-memory-continuity/ariadne/current-state-map.md`

For Planner, Writer, Editor, Validator, Extractor, document every context block, source, authority, character budget, and fallback path. Identify duplicate content and empty legacy fields. Do not modify production code in this task.

### Task 1.2: Produce the data and transaction map

**Files:**
- Read: `models/novel_memory.py`
- Read: `services/novel_memory_atoms.py`
- Read: `services/novel_memory_evidence.py`
- Read: `services/novel_memory_scenes.py`
- Read: `services/knowledge_merger.py`
- Read: `services/character_card_service.py`
- Archive: `docs/research/novel-memory-continuity/ariadne/data-flow-map.md`

Trace candidate creation, accepted promotion, conflict handling, character-card authority, Scene Block aggregation, publication, Chroma outbox, and rollback boundaries. Mark any operation that can leave the database partially updated.

## Phase 2: Design Alternatives

Evaluate these alternatives before implementation:

### Option A: Context-only adaptation (recommended first)

Add an internal `AgentContextBundle` and `ContextSection` projection around existing memory. No new tables and no new model calls. This has the smallest blast radius and directly tests Ariadne's strongest idea.

### Option B: Context plus narrative projections

Add deterministic story-event/story-segment/stage-summary projections derived from existing chapter outline, handoff, extractor output, and accepted memory. The projections are not a fifth memory layer and are not shown as the four-layer memory UI.

### Option C: Full workflow adoption

Add Detail, multiple Critics, Prudent, and Polisher as default workflow nodes. Reject this as the production default unless a controlled experiment meets the quality and retry gates after accounting for all extra calls.

The design record must explain why the selected option preserves V12's low retry behavior and how it avoids duplicating character cards, Scene Blocks, or canonical facts.

## Phase 3: Controlled Experiment Matrix

Each variant starts from the same novel snapshot and isolated PostgreSQL memory. No shared memory, manual正文 edits, or remote push.

| Variant | Change | Extra default model calls | Success gate |
|---|---|---:|---|
| A0 | V12 baseline | 0 | Reproduce baseline metrics and runtime audit |
| A1 | AgentContextBundle only | 0 | Lower or equal content retry; no quality regression |
| A2 | A1 + deterministic story event/segment projections | 0 | Improve plot continuity/foreshadowing without context explosion |
| A3 | A2 + conflict queue and atomic memory publication | 0 normally | Zero hard authority conflicts and no partial publication |
| A4 | A3 + deterministic hybrid full-text/vector recall | 0 | Better targeted recall at equal or lower context budget |
| A5 | A3 + gated Detail/Critic/Prudent/Polisher | Variable | Only enabled for quality-gate failures; net quality gain must justify calls |

Run 10 chapters for each variant. Select at most two candidates for 20-30 chapter runs and two independent repetitions. Record the existing seven quality dimensions plus context size, retrieval hit rate, conflict count, transaction rollback count, content/API/JSON retry counts, and wall-clock time.

## Phase 4: Implementation Tasks After Design Approval

### Task 4.1: Add context bundle contracts

**Files:**
- Create or modify: `agents/context_bundle.py`
- Modify: `agents/pipeline_context.py`
- Modify: `services/memory_manager.py`
- Modify: `services/novel_memory_recall.py`
- Test: `tests/services/test_agent_context_bundle.py`

Implement deterministic sections with `section_id`, `title`, `content`, `sources`, `authority`, `source_chapter`, `version`, and character budget. Keep the existing dictionary fields as a compatibility adapter until all agents consume the bundle.

### Task 4.2: Add narrative projections

**Files:**
- Create: `models/narrative_index.py`
- Create: `services/narrative_index.py`
- Create: `tests/services/test_narrative_index.py`
- Modify: `models/__init__.py`
- Create: one Alembic migration under `alembic/versions/`

Use deterministic IDs and source references. Support event-to-chapter, segment-to-event, stage-to-chapter, and foreshadowing-to-event links. Store accepted projections separately from candidate proposals, and keep the frontend unchanged in the first experiment.

### Task 4.3: Make high-risk memory changes explicit

**Files:**
- Modify: `services/novel_memory_atoms.py`
- Modify: `services/knowledge_merger.py`
- Modify: `services/character_card_service.py`
- Create or modify: conflict queue model/service and focused tests

Only hard conflicts enter the queue. Ordinary candidate extraction remains non-blocking. Never let an Extractor update immutable character-card core settings.

### Task 4.4: Close publication transaction boundaries

**Files:**
- Modify: `services/knowledge_merger.py`
- Modify: `services/novel_memory_scenes.py`
- Modify: `services/experiment_publication.py`
- Test: transaction rollback and idempotency tests

Keep external model calls outside the database transaction. Commit canonical PostgreSQL records atomically, then enqueue Chroma/vector work through the existing outbox. Ensure retries cannot duplicate Evidence, Atoms, Scene Blocks, narrative events, or publication events.

### Task 4.5: Add optional hybrid retrieval

**Files:**
- Modify: `services/novel_memory_recall.py`
- Modify: `services/vector_chroma.py`
- Create or modify: PostgreSQL full-text query service
- Test: `tests/services/test_hybrid_recall.py`

Start with deterministic PostgreSQL keyword/full-text candidates merged with Chroma results. Do not add a reranker model call in the first experiment.

### Task 4.6: Gate optional quality agents

**Files:**
- Modify: `worker_support/generation_editor_policy.py`
- Modify: `worker_support/generation_validation_flow.py`
- Modify: `services/quality_metrics.py`
- Test: focused gate and retry-count tests

Enable extra agents only when the validator reports a hard continuity issue or a chapter is explicitly marked high risk. Distinguish their calls from Writer content retries in the experiment recorder.

## Phase 5: Verification and Release Decision

Run, at minimum:

```powershell
codegraph sync
python -m compileall agents models services worker_support tests
pytest -q
```

For each experiment, verify:

- hard setting, character-state, and timeline conflicts are zero;
- accepted facts retain source chapter and authority;
- candidate facts cannot silently enter authoritative context;
- one failed post-processing step leaves no partial canonical state;
- duplicate workers are idempotent;
- average content retry is at most 1 per chapter and at least 80% chapters have zero content retries;
- seven-dimensional average is at least 8.5, continuity and foreshadowing are at least 8.5, and all other dimensions are at least 8.0;
- no default workflow change adds a dedicated handoff or narrative-index model call.

Production selection remains V12 unless a candidate beats it on quality and retry gates in independent runs. Preserve all failed variants and raw events.

## Archive Layout

```text
docs/research/novel-memory-continuity/ariadne/
├── README.md
├── source-snapshot.md
├── current-state-map.md
├── data-flow-map.md
├── design-options.md
├── results.md
└── versions/
    ├── A0.md
    ├── A1.md
    ├── A2.md
    ├── A3.md
    ├── A4.md
    └── A5.md
```

Raw run directories remain under `data/research_runs/` and must include the Ariadne source commit in their manifest. Prompt files are copied by version into the corresponding run directory; old versions are never overwritten.
