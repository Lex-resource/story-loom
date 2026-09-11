# V57 Compact Character Surface

## Goal

Improve character portrayal and prose quality after the V56 partial run without
adding model calls or weakening the layered-memory authority boundary.

## Observation from A42/V56

V56 added `character_turn`, but its runtime prompt still recursively included
the V45-V56 generation hints. The resulting surface behaved like an audit
checklist: the fixed seed repeatedly produced observation, confirmation,
stopping, and redirection. Chapters 2 and 3 scored 8.43 and 8.57, with
character portrayal and writing quality both at 8 in the complete evaluations.

## Controlled change

V57 keeps the existing `primary_action`, `character_turn`, chapter contract,
memory layers, authority rules, and retry policy. It replaces the accumulated
V54/V55/V56 prompt chain with one compact role-specific instruction for
Planner, Writer, Editor, Validator, and Extractor. The compact surface asks
for one pressure-driven tradeoff and one visible consequence, while keeping
unknown and candidate information unresolved. It adds no database field,
memory layer, frontend surface, or default model call.

## Runtime controls

Use a fresh project copied only from the fixed published chapter-1 seed, a new
layered-memory namespace, OpenAI / `gpt-5.6-luna` only, backup disabled, hybrid
recall disabled, `chroma_local` embeddings, and `bootstrap_skeleton=false`.
Generate chapters 2-10 and retain all prompts, responses, memory snapshots,
quality dimensions, retry classes, token counts, and wall-clock metrics.

## Hypothesis

Removing accumulated instruction duplication should reduce mechanical prose and
make the character choice more visible without increasing content retries.
V57 is eligible only after all nine generated chapters complete and satisfy the
existing hard-conflict and quality gates.
