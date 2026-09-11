# V59 Action-First Realization

## Goal

V58 repaired the missing structured turn in V57, but the generation surface can
still turn that structure into a procedural sequence of reading, recording and
explaining. V59 tests whether changing only the narrative order improves
character portrayal and writing quality without adding calls or changing memory
authority.

## Controlled change

Keep V58's non-empty `primary_action` and `character_turn`, layered-memory
recall, authority boundaries, retry policy, provider, and embedding settings.
Replace the V58 agent hint surface with an action-first rule:

`scene pressure -> character choice -> immediate visible consequence -> at most one necessary reveal -> new state`

Planner, Writer, Editor, Validator, and Extractor receive role-specific wording
for the same rule. No database field, memory layer, or model call is added.
Warnings about thin prose remain local quality signals and do not trigger a
Writer retry.

## Runtime controls

- Fresh project from the fixed published chapter-1 seed.
- New layered-memory namespace.
- OpenAI / `gpt-5.6-luna` only; backup provider disabled.
- Hybrid recall disabled; `chroma_local` embeddings.
- `bootstrap_skeleton=false`; generate chapters 2-10.
- Preserve all prompts, responses, memory snapshots, quality scores, retries,
  tokens, and wall-clock metrics.

## Hypothesis and gate

V59 should preserve V58's continuity and zero-content-retry behavior while
raising character portrayal and writing quality. The first Planner and Writer
snapshots must contain the V59 marker and the non-empty shared turn. A startup
failure excludes the run without reusing its memory.
