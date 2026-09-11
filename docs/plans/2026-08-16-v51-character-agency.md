# V51 Character Agency And Observable Choice

## Decision

Freeze A36/V50 as a partial observation and run a fresh A37 from the fixed
published chapter-1 seed. V51 keeps V50's observation-language repair, memory
authority boundary, and retry classification. It adds only a shared prompt
surface for making one character choice visible in each chapter.

## Hypothesis

A36 removed content retries in its first three chapters, but its quality
average was `8.43/10` and the optional V50 repair path was not exercised. The
remaining weakness is narrative execution: investigation beats still risk
reading as repeated interface operations, with character portrayal and prose
quality below the target. Anchoring one choice in existing character state
and requiring a visible cost/risk/direction change may improve those
dimensions without inventing facts or adding calls.

## Controlled change

- V51 prompt marker is injected into Planner, Writer, Editor, Validator, and
  Extractor.
- Planner selects one key choice from existing character-card constraints,
  accepted state, or visible chapter pressure.
- Writer renders that choice through action, hesitation, tradeoff, refusal, or
  position change rather than psychological explanation.
- Editor compresses repeated procedure and preserves the choice chain.
- Validator treats thin characterization as a warning; hard continuity issues
  remain blocking and retryable.
- Extractor stores only observed choices/actions and visible consequences.
- No new database field, memory layer, frontend surface, or model call.

## Acceptance gates

The first Planner, Writer, Editor, Validator, and Extractor prompt snapshots
must contain `V51 角色选择落地` and `V50 最小证据修复`. A37 must start from a
fresh project containing only the fixed published chapter 1, initial character
state, and empty layered-memory namespace. Record every prompt, response,
quality dimension, retry type, token count, memory-context size, and wall
clock time under the local research directory.

## Comparison

The ten generated chapters are compared with A28/V43 and the partial A36/V50
observation. Success requires average quality at least `8.5`, continuity and
foreshadowing at least `8.5`, no hard setting/state/timeline conflicts, and
the existing low-retry thresholds. If the first two chapters fall below
`8.3` or a hard conflict appears, stop and preserve the failed sample.
