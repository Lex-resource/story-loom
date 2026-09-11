# Ariadne 源码快照

## Checkout

- Local path: `<本地路径>/Ariadne`
- Remote: `https://github.com/yanshaoqwq/Ariadne.git`
- Branch: `main`
- Commit: `480065e77a433d490aaa4671c0f65b44bc0919f3`
- Commit time: `2026-08-15T02:21:46Z`
- Commit message: `Delete issue.md`
- Working tree: clean at snapshot time

## Project shape

Ariadne is a Rust core plus a .NET desktop application. The core contains workflow contracts, RAG context assembly, knowledge models, memory pipelines, and retrieval services. The README describes a three-level outline (book, stage, chapter), Detail/Critic/Prudent/Polisher nodes, multi-granularity summaries, source references, and hybrid retrieval.

## Source observations

### Context assembly

`core/src/rag/context.rs` defines a `WritingContextAssembler` and selects sections by Agent kind. Planner, Writer, Critic, Prudent, Polisher, and Summarizer receive different context surfaces rather than one universal prompt. Sections carry IDs, titles, content, sources, and metadata.

### Narrative memory

`core/src/rag/memory.rs` stores story segments, story events, chapter summaries, stage summaries, registered changes, and foreshadowing links. The summary pipeline can apply these records to a cloned working state and publish only after validation and cancellation checks succeed.

### Provenance and approval

`core/src/knowledge/models.rs` defines summary levels, fact kinds, versioned fact values, source spans, fact proposals, two-step approvals, and conflict records. `core/src/knowledge/service.rs` makes conflicting proposals enter a review state instead of silently overwriting existing facts.

### Retrieval

`core/src/retrieval/hybrid.rs` merges ranked vector and full-text results, deduplicates by chunk ID, supports metadata layer weights, and optionally passes the combined candidate set to a reranker. This is deterministic until a reranker is explicitly configured.

## Legal and product boundary

`LICENSE` is PolyForm Noncommercial License 1.0.0. `COMMERCIAL_LICENSE.md` requires a separate written commercial license for commercial product integration, production operation, paid deployment, and commercial redistribution. This checkout is for local research only. No Ariadne source is copied into `novel-assistant`.
