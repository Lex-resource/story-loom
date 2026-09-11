# V60 External Consequence

## Goal

V59 improved ordering, but its first clean chapters still centered the device
operation and its returned information. V60 tests whether requiring a visible
state change outside the interface makes the same structured turn read as a
scene rather than a query-and-explanation procedure.

## Controlled change

Keep V59's structured `primary_action` and `character_turn`, layered-memory
authority boundaries, retry policy, provider, embedding settings, and six-call
generation path. Add one role-specific constraint: the immediate consequence
must alter an observable external state such as position, access, item
availability, exposure risk, time window, relationship distance, or investigation
direction. The ending must be a concrete state that cannot be restored merely by
repeating the same query.

No database field, memory layer, frontend surface, or model call is added.
Historical V59 remains available through its direct hint helper and archived
prompt snapshots.

## Runtime controls

- Stop the incomplete A45 run before starting A46.
- Start from the same fixed published chapter-1 seed in a fresh project and
  memory namespace.
- Use OpenAI / `gpt-5.6-luna` only; backup provider disabled.
- Hybrid recall disabled; local Chroma embeddings.
- `bootstrap_skeleton=false`; generate chapters 2-10.
- Preserve all prompts, responses, memory snapshots, quality scores, retries,
  tokens, and wall-clock metrics.

## Hypothesis and gate

V60 should keep V59's zero-content-retry behavior while improving writing
quality, character portrayal, and chapter continuity. The first Planner and
Writer snapshots must contain the V60 marker and the non-empty shared turn.
Only existing facts and the current chapter contract may supply the external
change; the prompt must not encourage invented entities or mechanisms.
