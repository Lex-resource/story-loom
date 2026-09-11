# Data Flow Map

## Chapter generation

```text
Chapter/previous published ending
  -> deterministic ChapterHandoff
  -> Planner context + outline
  -> deterministic ChapterContract
  -> Writer draft
  -> Editor review/repair
  -> Validator continuity gate
  -> optional Writer retry
  -> published Chapter
  -> Extractor output
```

The handoff and contract do not add model calls. They are deterministic
projections of database rows and already-generated outputs.

## Post-processing writes

For a normal published chapter, `apply_extractor_updates` currently performs
these operations:

1. Capture immutable extractor Evidence, when enabled.
2. Persist Memory Atom candidates from the validated extractor patch.
3. Stop and mark the chapter pending review for a hard extractor conflict.
4. Apply character-card updates and enqueue character vectors.
5. Promote ordinary atom candidates to accepted memory and project accepted
   world rules into Doctrine.
6. Publish chapter state and update novel counters.
7. Record experiment publication.
8. Aggregate a Scene Block and enqueue its vector outbox item.

The first canonical update group and the later Scene Block update are separated
by commits. The Ariadne research therefore treats atomic publication as a
separate A3 experiment; A2 does not claim to fix this boundary.

## Retrieval path

```text
PostgreSQL doctrines / scene blocks / atoms
  -> role and chapter filters
  -> bounded layered-memory prompt

Vector outbox
  -> Chroma worker
  -> advisory vector context
```

The vector index is advisory and is not authoritative over accepted
PostgreSQL facts. A2 projections will initially remain PostgreSQL records and
will not change the frontend or add a vector call.

## Idempotency and risk points

- Evidence is content-hash keyed and append-only.
- Atom candidates are hash-keyed and conflict-safe.
- Scene Blocks are content-hash keyed, but aggregation happens after the
  chapter publication commit.
- Character updates and canonical memory promotion share the first post-
  processing commit, while vector work is outboxed.
- A failed post-publication Scene Block step can roll back only that later
  operation; it cannot roll back the already-published chapter.

These observations define the A3 rollback tests and are not changed by the A2
story-index projection.
