# Results

## A0/V12 clean baseline

Run directory: `data/research_runs/ariadne-a0-v12-baseline-10ch-20260815`;
project: `0cb4c81e-e0c6-4b1a-b2d2-17fa4f1dd7af`; provider: OpenAI /
`gpt-5.6-luna`; backup provider: disabled; embedding: `chroma_local`;
narrative index: disabled.

Chapter 1 was a copied published seed. Chapters 2-10 were generated in this
new isolated project, each with one final completed event and complete
seven-dimension quality data. The run scored `8.617/10`; continuity averaged
`9.111` and foreshadowing payoff `8.889`. Character portrayal averaged
`7.889`, which is below the minimum `8.0` requirement.

There were `4` content retries (`0.444/chapter`) and `5/9` retry-free chapters
(`55.56%`). API retries and JSON recoveries were both `0`. The pipeline used
`67` LLM calls, `3,008.05s` wall-clock, `973,190` input tokens, `142,830`
output tokens, and an average chapter memory context of `10,629.962` characters.
The structured copy of these metrics is in
`data/research_runs/ariadne-a0-v12-baseline-10ch-20260815/metrics.json`.

## A1 compatibility result

- Ariadne reference commit: `480065e77a433d490aaa4671c0f65b44bc0919f3`
- Product branch: `codex/novel-memory-tencentdb`
- Provider: OpenAI, model `gpt-5.6-luna`
- Backup provider: disabled
- Embedding: `chroma_local` because the OpenAI provider has no embedding model
- CodeGraph: synchronized before A1 changes and again before this batch

### Deterministic verification

`pytest -q tests/services/test_agent_context_bundle.py tests/services/test_context_compaction.py`
passed with 12 tests. `python -m compileall -q agents services worker_support tests`
also passed in the available runtime.

### A1 real LLM smoke test

Run directory: `data/research_runs/ariadne-a1-llm-smoke-20260815`.

This was a single manually constructed Writer Bundle, not a full chapter
pipeline. It used one OpenAI call, one attempt, zero API retries, zero content
retries, zero JSON recoveries, about 5.814 seconds wall-clock time, 4,589 input
tokens, 71 output tokens, and 167 rendered memory-context characters.

The response preserved the accepted handoff action and did not promote the
candidate sender identity to a fact. This supports the authority-boundary
hypothesis, but it is insufficient to claim a quality improvement for full
chapter generation.

## Current decision

A1 is a compatibility foundation. The next controlled change is A2: add
deterministic narrative projections and test them independently before running
the complete Planner -> Writer -> Editor -> Validator -> Extractor path.

## A2 result

A2 persistence was idempotent and the complete pipeline consumed the narrative
index without a new model call. The original nine-chapter sequence on project
`ecc00446-3efb-478e-b24b-d37cbaf1f45d` is now classified as exploratory rather
than a clean ten-chapter run: chapter 1 was manually seeded, chapters 2-4
were three separate single-chapter experiments, and chapters 5-10 were the
only chapters in `ariadne-a2-10ch-20260815`.

Across chapters 2-10, the sequence scored `8.491/10`; continuity averaged
`9.0`, foreshadowing payoff `8.667`, content retries were `3` total
(`0.333/chapter`), and only `6/9` chapters were retry-free. The sequence used
`64` LLM calls, `1` API retry, `0` JSON recoveries, `3,061.45s` wall-clock,
`1,003,693` input tokens, `139,130` output tokens, and an average recorded
memory context of `13,065.913` characters. Character portrayal and writing
quality both averaged `7.889`, below the research gate.

The isolated six-chapter sub-run `ariadne-a2-10ch-20260815` scored `8.547/10`
with `2` content retries and `4/6` retry-free chapters. It is not sufficient
to claim a ten-chapter result. A2 remains a research projection, not the
production default. The next comparison is a fresh A0/V12 baseline and a
fresh A2 run from the same chapter-1 snapshot.

## A3 status

A3 implementation and smoke verification are complete locally and preserve the
V12 prompt. The isolated chapter-2 smoke used seven LLM calls, zero content
retries, and quality `8.71/10`. Its hard-conflict routing check left the
chapter pending review without publishing Scene Block or Narrative Index
projections. Replaying the same extractor result was idempotent. A3 is still
not a ten-chapter quality decision.

## A4 status

A4 implementation is complete locally. It keeps A3's authority and atomic
publication rules, ranks a bounded PostgreSQL memory pool by the current
chapter query, and adds role-specific Chroma history as explicitly advisory
context. It does not add a dedicated LLM call and can disable the vector part
with `ENABLE_NOVEL_HYBRID_RECALL=false`. The A4 ten-chapter run is the next
controlled experiment; no quality or retry improvement is claimed yet.

The formal A4 r2 attempt (`ariadne-a4-v12-hybrid-10ch-20260815-formal-r2`)
was stopped before chapter 2 produced a Planner `llm_attempt` event. Its only
chapter-2 event was an empty lexical/vector recall audit, so it is classified
as interrupted infrastructure evidence rather than a quality result. The raw
directory is retained and excluded from all comparisons.

## A5 status

A5 implementation is complete locally. It keeps V12 prompts and A3 memory
publication as the control path, then enables the Ariadne-inspired Detail /
Critic / Prudent / Polisher role mapping only for the explicit A5 experiment
variant. Two early attempts were excluded as infrastructure/implementation
failures and retained in their raw directories. The valid run is
`data/research_runs/ariadne-a5-v12-gated-polisher-10ch-20260815-r3/` on
project `67ae1789-17d2-41f0-9594-545bc21f8176`.

Its first completed chapter (chapter 2 after the copied chapter-1 seed) used
7 LLM calls, 0 API retries, 0 JSON recoveries, 0 content retries, and
`382.895s` wall-clock time. The seven-dimension score was `8.43`; continuity
and foreshadowing were both `9`. Chapter 3 has already recalled 10 lexical
memory candidates, including 7 accepted atoms. The ten-chapter quality
conclusion remains pending.

The A5 run was stopped at chapter 3 by user direction because the version was
not considered promising. Its raw events and prompts remain under
`data/research_runs/ariadne-a5-v12-gated-polisher-10ch-20260815-r3/` and are
excluded from ten-chapter comparisons because the run is incomplete.

## A6 status

A6 is the immediate ablation after A5: V12 prompts, A3 atomic publication and
structured continuity context remain enabled, while the A5 extra Polisher path
is explicitly disabled. It starts from a fresh project and memory namespace,
uses the OpenAI provider as the sole provider, and records a new run directory.
The purpose is to measure whether A5's extra repair call caused its latency or
quality instability before introducing another model-facing change.

A6 was stopped after chapter 2. Its Writer/Editor/Validator sequence scored
`8.57`, but Validator raised one avoidable content retry because the V12
evidence-surface contract required a “共同校准脉冲” absent from the handoff.
The run also used `hybrid_enabled=true` unexpectedly and is excluded from
formal comparison. A7 fixes the deterministic contract condition and runs with
hybrid recall explicitly disabled.

## A7 status

A7 implementation and focused regression coverage are complete locally. It is
the next clean ten-chapter run after A6, using a fresh project and the copied
chapter-1 seed. The A5 and A6 raw directories remain unchanged.

A7 was then excluded as an interrupted partial run: its Worker had loaded the
old prompt module when the prompt-side contract fix was added. The raw project
and events remain preserved. A8 is the clean repetition after all A7 changes
were complete.

## A8 status

A8 was stopped after chapter 3 in step mode and is excluded from formal
ten-chapter comparison. Chapters 2 and 3 both completed without a content
retry and both received a preliminary seven-dimension score of `8.71`, but the
run recorded API/JSON recovery activity and the chapter-3 Writer memory
context had grown to `12,510` characters. Its raw project, events, prompts,
responses, and partial output remain unchanged.

## A9 status

A9 was the next independent Ariadne experiment. It kept A8's A3 atomic
memory, conditional evidence-surface contract, character cards, and
no-Polisher control, while selecting V20's low-retry state profile. It stopped
in chapter 2 after one Writer retry: the final score was `8.43`, wall-clock
`473.362s`, with `1` content retry, `0` API retries, `0` JSON recoveries, `7`
LLM calls, and a context range of `687`-`3,697` characters. The hard failure
was an invented `记录页` plus wording that looked like reopening a closed
read-only window. A9 is excluded from formal comparison; project
`7e12f1af-1386-4ad7-a661-0dc7080a5417` and all raw artifacts remain preserved.

## A10 status

A10 adds the V25 explicit artifact and closed-window contract motivated by the
A9 failure. It keeps the same memory and no-Polisher control, adds no model
call, and passes the new `item_state_rules` to all five Agents through the
shared chapter contract. Project `b8c2fd2c-10a0-488b-aa4d-665a13dfcf52` was
created from the fixed chapter-1 seed, but the run was stopped in chapter 2
after the old unconditional V12 calibration claim caused one avoidable
content retry. The final paused event scored `8.71` with `1` content retry,
`0` API retries, and `0` JSON recoveries. A10 is excluded from comparison;
the project and raw artifacts remain preserved.

## A11 status

A11 is the clean follow-up to A10. It uses V26, which keeps V25's explicit
artifact/window boundary and fixes the A7+ conditional evidence-surface rule in
both the shared contract and prompt hint. Project
`23853c22-0814-4a12-bfe2-c2fdc227ccef` has been created from the fixed seed and
queued as one auto batch for chapters 2-10. The final result remains pending.

## A12 status

A12 is the immediate narrative-quality follow-up to A11. V27 keeps the
V20/V25 state and artifact boundaries, but removes the generation-side V12-V15
evidence checklist pressure. Planner and Writer receive a compact
narrative-first rule; the deterministic contract only adds evidence-surface
rules when the handoff contains a non-empty evidence ledger. Validator and
Extractor keep the backend evidence authority for auditing and publication.

A11 was stopped after its first chapter-2 Planner/Writer pair because the
rendered response was mechanically formatted as an evidence report. A12 uses
a fresh project seeded from the same fixed chapter-1 snapshot. The project and
run directory will be appended here after launch; no A11 files are reused.

A12 was stopped during chapter 2 after Editor/Validator identified a hard
action-ownership conflict. The preliminary score was `8.43`, with `0` content,
API, and JSON retries across `3` LLM calls, but the job was force-saved and
paused without a `chapter_finished` event. It is excluded from ten-chapter
comparison. A13 records the follow-up as V28 rather than modifying A12.

## A13 status

A13 is the clean V28 follow-up to A12. It retains V27's narrative-first
generation surface and adds a shared action-ownership rule: a read-only UI can
change visible information but cannot open a door, grant authorization, or
produce an entity effect. Any entry must be attributed to an explicit character
action or kept as an unknown observation.

A13 uses a fresh project seeded from the same fixed chapter-1 snapshot. The
project and run directory will be appended after launch; A12 remains immutable.

A13 was stopped by user direction after chapter 2 completed and chapter 3
reached Validator/Extractor. Chapter 2 scored `8.57` with 7 LLM calls and zero
content/API/JSON retries in `273.102s`; chapter 3's preliminary quality event
scored `8.71` but has no `chapter_finished` event. A13 is excluded from the
ten-chapter comparison. Its chapter-3 Writer memory context reached `10,485`
characters, and the quality reasons still identified repeated observation /
confirmation and residual audit-style summary language.

## A14 status

A14 is the direct next experiment after A13. It uses V29's compact narrative
execution surface: Planner/Writer no longer receive the accumulated V7-V28
generation hint blocks, and the rendered contract excludes backend-only rule
payloads already owned by the structured handoff and Validator. No model call
was added and hybrid recall remains disabled.

The independent project is `842fe759-8d97-4849-bb35-a4b7dcefad9e`, seeded with
the fixed chapter-1 snapshot from A13. Chapters 2-10 are queued in one auto
batch. Chapter 2 completed with quality `8.57`, 7 LLM calls, `367.936s`
wall-clock, Writer memory context `687-2,097` characters, and content/API/JSON
retries `0/0/0`. Chapter 3 completed with quality `8.57`, 6 LLM calls,
`290.093s` wall-clock, Writer memory context `9,450` characters, and
content/API/JSON retries `0/0/0`. The run was then paused and is excluded from
the clean ten-chapter comparison. Its raw data remains under
`data/research_runs/ariadne-a14-v29-compact-narrative-no-polisher-10ch-20260816/`.

## A15 status

A15 is the direct next experiment after A14. It keeps V29's compact narrative
generation surface and changes only the deterministic handoff projection:
transition history and provenance repetition are removed from generation
prompts while current state, the previous ending, item/evidence ledgers, and
unknown boundaries remain. The first run used project
`e87f29cc-43b7-41c6-9885-f0ce63779982`. Chapter 2 reached a preliminary
`8.43/10` before one valid content retry, but the OpenAI upstream then returned
two `400 Upstream request failed` errors and timed out even on a minimal health
request. It ended without publishing chapter 2 and is excluded from quality
comparison. The raw run remains under
`data/research_runs/ariadne-a15-v30-handoff-compression-no-polisher-10ch-20260816/`;
a clean V30 rerun will use a new project after connectivity recovers.

## A16 status

A16's valid rerun was paused after chapter 2 by user direction. The actual
Writer snapshot contained V29 and V31 and completed without an API or content
retry before the pause, so it is a valid runtime observation but not a quality
comparison: the prose protected the unknown boundary while reading as an
execution checklist. The raw run is retained at
`data/research_runs/ariadne-a16-v31-evidence-ordered-continuity-no-polisher-10ch-20260816-r2/`.

## A17 status

A17 is the direct next experiment after A16. V32 keeps the deterministic
handoff, shared chapter contract, layered memory, character cards, hard
validator, and no extra Polisher. It changes only the prompt assembly surface:
for Planner, Writer, Editor, Validator, and Extractor, V32 replaces the
accumulated V6-V31 hint blocks with one short role-specific block. Planner's
contract output still contains the continuity fields, and the existing V29/V31
branches remain available for older experiment versions.

The research hypothesis is that a smaller instruction surface will preserve
the hard continuity boundary while reducing mechanical, audit-like prose and
content retries. A clean ten-chapter run must use a new project seeded only
with the same chapter-1 snapshot as A16, with `prompt_version=V32`, OpenAI as
the active provider, backup provider disabled, and no shared post-chapter
memory. The first Planner, Writer, Editor, Validator, and Extractor snapshots
must be checked for the V32 marker before the run is allowed to continue.

## A18 status

A18 is the direct follow-up to A17. It keeps V32's compact generation surface
and changes the Extractor memory update protocol: existing-key observations
should use `append_progress`, explicit generated replacements require a
`replacement: true` marker, and the deterministic atom gate allows only
observation-shaped generated state progression. Published/user/frozen/system
atoms and changed hard markers remain blocking conflicts. No model call was
added.

The first A18 run was excluded because the Worker was stale: its event metadata
said `V33`, but its Planner/Writer prompt snapshots did not contain the V32
surface. It remains under
`data/research_runs/ariadne-a18-v33-memory-update-protocol-no-polisher-10ch-20260816/`
with project `3bef94b6-ac05-4400-918e-62f73f316eb2`.

The clean r2 run is
`data/research_runs/ariadne-a18-v33-memory-update-protocol-no-polisher-10ch-20260816-r2/`
on project `491fddc4-9b3f-4549-88b6-d33f28647ae1`, seeded only with chapter 1
from the fixed project `adebad38-563f-4541-befe-20aab04861f9`. Chapter 2 has
published at `8.71/10` with `0/0/0` content/API/JSON retries, `7` LLM calls,
and `332.208s` wall-clock. Chapters 2-4 completed with no content/API/JSON
retries; chapter 4 scored `8.71/10` and reached Extractor publication. The
run was then stopped by user direction before chapter 5 completed, so A18 is a
partial observation and is excluded from the ten-chapter comparison.

## A19 status

A19 is the direct next experiment after the partial A18 observation. V34
assigns one owner to each prompt context block and projects only the latest
active atom per memory key and latest scene block per scope. Full PostgreSQL
history, candidate rows, evidence, and experiment snapshots remain unchanged.
The formal run uses OpenAI as the sole provider, backup disabled, hybrid recall
disabled, and no extra Polisher or summary call. Its run directory and ten
chapter result are pending launch.

The formal run was stopped by user direction after chapter 3. Chapters 2 and 3
completed with scores `8.71` and `8.86`, respectively, and both had zero
content/API/JSON retries. Chapter 2 used `278.525s` and 7 LLM calls; chapter 3
used `238.25s` and 6 LLM calls. The Writer memory-context totals were `1,826`
characters in chapter 2 and `7,127` in chapter 3; chapter 3 had separate
handoff, contract, character-card, and layered-memory surfaces. The run is a
valid partial runtime observation, not a ten-chapter quality comparison. Raw
events remain under
`data/research_runs/ariadne-a19-v34-context-ownership-current-state-no-polisher-10ch-20260816/`.

## A20 status

A20 is the direct follow-up to the A19 observation. V35 keeps A19's memory
authority, atomic publication, no-Polisher control, and provider settings, but
gives only the Writer a deterministic narrative execution brief. The brief
combines the previous ending, current scene, inherited state, executable
chapter actions, closing state, open questions, and unknown boundary. Writer
no longer receives standalone handoff or contract prompt blocks; review Agents
continue receiving the full structured surfaces.

V35 implementation and focused verification passed. The formal ten-chapter
run uses project `2d9f6d38-ca9d-4c34-a161-da6458874e53` and run directory
`data/research_runs/ariadne-a20-v35-writer-execution-brief-no-polisher-10ch-20260816-r2/`.
The first A20 attempt was stopped and retained separately because its telemetry
counted context fields that V35 hid from Writer; it is excluded from formal
comparison. The clean r2 chapter-2 Writer snapshot has the V35 brief, no
standalone handoff or contract blocks, and a breakdown containing only
`writer_execution_brief_context=1177` characters. Its ten-chapter quality and
retry result remains pending.

## A21 status

A21 is the direct follow-up to A20. V36 keeps the V35 Writer execution brief,
the layered-memory authority boundary, the no-Polisher control, and the
OpenAI-only provider configuration. It adds a deterministic
`recording_action_rules` contract and projects it into the Writer brief as
`recording_boundary`.

The change addresses a concrete A20-r2 Validator block: Writer used a notebook,
paper, and pen to satisfy a recording action even though `item_state_ledger`
was empty. V36 explicitly defaults recording to interface state, spoken
recapitulation, pure observation, or an already-listed device. A matching
physical artifact is allowed only when the ledger contains it and the chapter
action permits it.

V36 implementation and focused verification passed (`93 passed`, compileall
passed). The isolated run was paused after chapter 2 completed and chapter 3
Planner started. Chapter 2 scored `8.71`, used `396.66s`, had `1` content
retry and `0/0` API/JSON retries. The retry corrected an interpretation
overreach in which a visible residual receipt fragment was treated as a
definite historical event and a device requirement. The chapter did not
reintroduce unregistered recording artifacts. A21 is a partial runtime
observation and is excluded from ten-chapter comparisons. Raw events remain
under
`data/research_runs/ariadne-a21-v36-recording-action-commitment-no-polisher-10ch-20260816/`.

## A22 status

A22 is the direct follow-up to A21. V37 keeps V36's artifact boundary and V35
Writer execution brief, then adds a shared observed/tentative/investigation
boundary so visible prompts, character guesses, and investigation goals cannot
be collapsed into confirmed history or device intent. It adds no model call,
keeps OpenAI as the sole provider, disables hybrid recall and the Polisher,
and uses a fresh project with the same chapter-1 seed. Implementation and
focused verification are complete. The first launch was excluded at the
startup gate because a stale Worker emitted a V37 event but rendered an old
Planner Prompt; it was paused before Writer execution and retained under
`data/research_runs/ariadne-a22-v37-observation-interpretation-boundary-no-polisher-10ch-20260816/`.
The Worker was restarted and the clean r2 run used the same fixed chapter-1
seed as A18-A21. Chapter 2 completed at `8.71/10` in `345.843s` with `9`
LLM calls and `0/0/0` content/API/JSON retries. Chapter 3 completed at
`8.43/10` in `261.893s` with `8` LLM calls and `0/0/0` retries, then the run
was paused by user direction before chapter 4. Chapter 3 still showed
mechanical repeated observation/confirmation and its Writer memory context
grew to `6,519` characters, while Validator reached `8,507` characters.
A22-r2 is therefore a valid partial runtime observation, not a ten-chapter
quality comparison. Its project is `4a2df247-3dd2-42d1-889b-cf202eb9e618` and
raw artifacts remain under
`data/research_runs/ariadne-a22-v37-observation-interpretation-boundary-no-polisher-10ch-20260816-r2/`.
A21 and A22-r1 remain immutable.

## A23 status

A23 is the direct follow-up to the A22 partial observation. V38 keeps V37's
observed/tentative/investigation boundary, V36 artifact boundary, V35 Writer
execution brief, atomic publication, OpenAI-only provider settings, disabled
hybrid recall, and the no-Polisher control. It adds one compact role-specific
prompt surface for scene motion and duplicate-information compression:
Planner, Writer, Editor, Validator, and Extractor now distinguish a genuine
new delta from repeated reading, confirmation, or summary language.

The change adds no model call, no memory layer, no database field, and no
frontend surface. It is intended to address A22 chapter 3's `8.43` result and
the remaining mechanical prose without weakening hard continuity gates. A23
uses a fresh project from the same fixed chapter-1 snapshot and must pass a
prompt startup gate for the `V38 场景推进与重复信息压缩` marker before any
chapter generation continues. The startup gate passed on project
`a83a1e9c-f0a8-4853-9852-d785a4650d8b`; the first Planner snapshot contained
the V38 marker and the manifest confirmed OpenAI-only execution.

The run was frozen by user direction after chapter 3 and before chapter 4
post-processing completed. Chapter 2 completed at `8.57/10` in `269.167s` with
`7` LLM calls, `70,740/13,512` input/output tokens, context range
`413-4,023`, and `0/0/0` content/API/JSON retries. Chapter 3 completed at
`8.71/10` in `248.110s` with `6` LLM calls, `71,024/12,298` input/output
tokens, context range `4,238-9,031`, and `0/0/0` retries. Chapter 4 reached a
quality event at `8.57/10` but has no final `chapter_finished` event; its raw
partial artifacts remain immutable and are excluded from comparison.

## A24 status

A24 is the direct follow-up to the A23 partial observation. V39 adds a single
evidence-pass and state-delta rule to the existing five-agent prompt surface.
It keeps the same layered memory, character-card, atomic-publication,
OpenAI-only, hybrid-disabled, and no-Polisher controls. Project
`0d6a2899-1831-4515-b7cd-0067ac70cee2` contains only the fixed chapter-1 seed;
its pre-run layered memory summary is zero across evidence, atoms, scene
blocks, and doctrines. The run directory is
`data/research_runs/ariadne-a24-v39-single-evidence-delta-no-polisher-10ch-20260816/`.
The startup gate and ten-chapter result are pending.

## A24 frozen and excluded

A24 is frozen as an exploratory partial result and is excluded from version
comparison. The original events and prompts remain unchanged in
`data/research_runs/ariadne-a24-v39-single-evidence-delta-no-polisher-10ch-20260816/`.
Chapter 2 reached `8.57/10` in `339.394s` with `9` LLM calls and one content
retry. Chapter 3 reached `8.57/10` before the run was paused, and also produced
one content retry. Both retries were caused by soft semantic ambiguity rather
than a hard setting, timeline, object, location, or core-event conflict:
chapter 2 mixed “already entered the tower” with an end-state phrase describing
the decision point; chapter 3 used “press the read key” after the historical
read window had closed, without making clear that this was a local trace scan.
The result confirms that V39 reduced repeated evidence beats but still leaves
the validator too eager to escalate contract wording differences into a full
rewrite.

## A25 startup

A25 is the direct V40 follow-up to the frozen A24 observation. V40 adds a
deterministic end-state boundary across the contract, Writer brief, and all
five Agent prompt surfaces. The validator may accept an explicitly identified
soft contract ambiguity when the published text and the contract agree on the
actual observed state; hard fact, timeline, object, location, and core-event
conflicts remain blocking. No database field, memory layer, frontend surface,
or default model call is added. A25 uses OpenAI / `gpt-5.6-luna`, backup
provider disabled, `chroma_local` embeddings, hybrid recall disabled, and no
Polisher. It starts from a fresh project containing only the fixed chapter-1
seed and clean initial character state, with no shared A24 memory or正文.

- Run ID: `ariadne-a25-v40-end-state-boundary-no-polisher-10ch-20260816`
- Prompt version: `V40`
- Parent: `A24`
- Expected extra default model calls: `0`
- Run directory: `data/research_runs/ariadne-a25-v40-end-state-boundary-no-polisher-10ch-20260816/`
- Status: paused and excluded as a partial sample

A25 was paused at chapter 8 during the Editor step so the next version could
start immediately. Chapters 2-7 completed with quality scores
`8.57, 8.57, 8.43, 8.43, 8.57, 8.57` (`8.52/10` average). All six completed
chapters had zero content retries, zero API retries, and zero JSON recoveries.
The partial sequence still repeated the same query/compare/save/door-test loop
with limited character choice and risk escalation, so it is excluded from the
ten-chapter comparison. Chapter 8 has no `chapter_finished` event. Raw events,
prompt snapshots, and the paused project remain under the A25 run directory.

## A26 planned

A26/V41 was the direct follow-up to the A25 quality observation. It kept V40's
terminal-state and retry boundaries and added a compact role-specific rule for
goal escalation. The run was paused at chapter 5 after the Validator reached
the three-rewrite limit. Chapters 2-4 scored `8.80`, `8.40`, and `8.20`; chapter
5 reached `8.60` after repair but was not published. Content retries were
`0, 0, 1, 3` across chapters 2-5. Hard failures included a disconnected
voice/input path, an identity/causal upgrade from an ambiguous sender label,
and a reversed footprint direction across chapters. A26 is excluded from the
production comparison, with raw events preserved.

## A27 planned

A27/V42 keeps V41's no-extra-call control but narrows the escalation rule to
observable operations only. Identity, sender, source, executor, ownership,
causality, and historical direction are explicitly locked to accepted evidence;
an ambiguous label cannot be used as a plot escalation, and a cross-chapter
direction or ownership change must have an observed transition. Planner and
Writer must choose a safe action/position/goal change when the fact itself is
unknown. Validator keeps hard conflicts blocking and treats only missing
narrative escalation as a warning. A27 starts from the same chapter-1 snapshot
in a fresh project and retains the same provider, embedding, recall, and
Polisher controls.

## A27 skipped

A27/V42 was stopped before producing a valid chapter result: its isolated
project remained paused at chapter 2 Planner with only the fixed chapter-1
seed. It is retained as an unfinished excluded sample; no A28 memory or正文
is derived from it.

## A28 planned

A28/V43 is the direct next research variant after the skipped A27. It keeps
V42's authority lock but permits one explicitly labeled hypothesis/pending
verification explanation to guide a reversible investigation. Every chapter
must still contain one observable choice, action, position, goal, cost, or
risk delta. The A28 validator policy treats only bounded hypothesis wording
issues as local repair; conflicts with accepted facts, timelines, locations,
items, or core events remain retryable hard failures. A28 adds no model call,
memory layer, or frontend surface. It uses the fixed chapter-1 seed, OpenAI

The first A28 attempt (`444f05bb-2a72-4a43-8dee-4278fcf1640c`) was paused after
chapter 2 because the auxiliary Extractor candidate-summary Prompt did not
contain the V43 marker. Its chapter-2 output scored `8.86/10` with zero
content/API/JSON retries, but the run is excluded for the startup-gate
failure. A clean r2 run was created from the same fixed chapter-1 seed:
`f569442d-cf02-4962-9e1f-c3068f305fd3`, job
`d8f9d1af-5223-407d-9fdd-fee617b23e02`, run directory
`data/research_runs/ariadne-a28-v43-bounded-hypothesis-no-polisher-10ch-20260816-r2/`.

The clean A28-r2 run completed chapters 2-10. Generated-chapter quality
averaged `8.601/10`; all 9 generated chapters had zero content retries, zero
API retries, and zero JSON recoveries. Dimension averages were plot `8.778`,
character `8.000`, world `8.778`, writing `8.000`, logic `9.000`, continuity
`9.000`, and foreshadowing `8.667`. It used 54 LLM calls (`6/chapter`),
`1992.89s` summed chapter wall clock, `668503/88699` input/output tokens, and
average memory context of `6035.814` characters. Validator hard issues and
terminal blocks were both zero. Final layered memory counts were
`evidence=9`, `atoms=32`, `scene_blocks=9`, `doctrines=2`. A28 meets the
current numeric gates and is a strong candidate for independent replication,
but character portrayal and writing quality are only at the minimum `8.0`, so
it is not yet the production default.

## A29 status

A29 is the independent V43 replication of A28. It used two isolated projects,
`9d1bf10c-6de7-474b-82c6-614a8e52b99e` and
`1dbc0d0f-3a96-48b8-a42a-39a0f0e00517`, both seeded only with the fixed
published chapter 1 and initial character state. OpenAI / `gpt-5.6-luna` was
the sole provider, backup remained disabled, and both runs started with empty
layered memory.

Both attempts completed chapter 2 at `8.57/10` with six calls and zero
content/API/JSON retries. A29-r1 reached a chapter-3 quality event at `8.71`
and then failed in Extractor after three upstream HTTP 400 responses. A29-r2
failed in Editor during chapter 3 after three upstream HTTP 400 responses.
The final chapter metrics were `1/2/1` content/API/JSON retries for r1 and
`0/2/1` for r2. A direct probe confirmed that the exact failed long Editor
request returns 400 in both JSON and plain-text modes, including with
`max_tokens=2048`, while a minimal request to the same provider returns 200.

A29 is excluded from quality and retry ranking because neither attempt reached
ten chapters. The raw events and prompt snapshots are retained. The next
research action is to isolate the long structured-request compatibility issue
before spending another full ten-chapter run.

## A30 status

A30/V44 tested a compact generation-facing input surface after A29's upstream
HTTP 400 failures. It used project `5d4928b8-4d8e-4429-888e-dc38b1c7e69e` and
run directory
`data/research_runs/ariadne-a30-v44-compact-input-surface-no-polisher-10ch-20260816/`.
The run was paused after chapters 2-4 completed and is excluded from the
ten-chapter ranking. Scores were `8.71`, `8.57`, and `8.57`; retries were
`0/0/0`, `0/0/0`, and `1/0/0` for content/API/JSON. Chapter 4's retry was
caused by the Writer adding unregistered paper and pen for recording. The
first V44 branch had replaced the earlier V36 artifact-boundary rule, so V45
will reintroduce the hard boundary in compressed form while keeping the
smaller review projections. Full details are in `versions/A30.md`.

## A32 status

A32/V46 was paused after chapter 7 and is excluded from the ten-chapter
ranking. Chapters 2-7 quality events were
`8.71, 8.57, 8.71, 8.71, 8.29, 8.00`; content retries were
`1, 0, 1, 0, 0, 1`, API retries `0, 0, 1, 0, 0, 0`, and JSON recovery was
zero throughout. The run used `45` LLM attempts across the six chapter
events. The main observation was unchanged character/writing quality and
continued repetition of record/confirmation explanations; chapter 7 also
left an accepted world-rule conflict for manual review. Full details and raw
artifacts are in `versions/A32.md` and
`data/research_runs/ariadne-a32-v46-dramatic-turn-no-polisher-10ch-20260816/`.

## A34 result

A34/V48 fixed the deterministic world-rule observation merge exposed by A33,
but its first attempt was excluded because the Job started at chapter 1 and
rewrote the fixed seed. The clean r2 run used project
`25bfd0d5-0af8-43e1-a5d3-116737478f27`; chapter 1 stayed published and chapter
2 used the V48 Prompt gate with OpenAI-only routing.

Chapter 2 reached `8.71/10` with 7 LLM calls, 0 API retries, and 0 JSON
recoveries, but paused after 3 content retries. The retries were caused by
evidence-language upgrades from an interface label to a confirmed historical
record and then to sender/request causality. No Extractor hard memory conflict
was recorded. V48 is therefore excluded from the low-retry ranking, while its
raw project and events remain under
`data/research_runs/ariadne-a34-v48-memory-merge-boundary-10ch-20260816-r2/`.

The direct next experiment is A35/V49, which targets local repair and retry
classification for this narrow observation-to-history/causality error class.

## A35 result

A35/V49 passed the fixed chapter-1 startup gate and was intentionally paused
after chapter 3 for the next controlled variant. It is excluded from the
ten-chapter ranking but is a valid partial runtime observation. Chapter 2
scored `8.57/10` with `0/1/0` content/API/JSON retries, `6` successful calls
from `7` attempts, and `306.172s`. Chapter 3 scored `8.57/10` with `0/0/0`
retries, `8` calls, and `248.173s`. Chapter 3 triggered one V49
`local_editor_repair` and passed revalidation without a Writer retry. The
remaining issue is that the force-revision call used a generic repair surface;
V50 tests whether an explicit sentence-local contract makes that repair more
stable.

## A36 startup

A36/V50 is the direct next experiment. It uses project
`b4027c5c-1053-426e-a3ca-85376547f9a3` and run directory
`data/research_runs/ariadne-a36-v50-minimal-observation-patch-10ch-20260816/`.
The fresh project copies only the fixed published chapter 1 and initial
character card from seed project `707eb904-28cb-454b-9dd1-89ff2433de46`; the
layered memory namespace is new. OpenAI / `gpt-5.6-luna` is the sole provider,
backup is disabled, hybrid recall is disabled, and generation starts at
 chapter 2 with `bootstrap_skeleton=false`. The first prompt gate passed.
Chapters 2-4 completed with qualities `8.14/8.57/8.57`, zero
content/API/JSON retries, and no `observation_language_minimal_patch` event.
The optional V50 repair path was therefore not exercised. The Worker was
stopped before chapter 5 by user direction; A36 is a partial observation and
is excluded from ranking. The raw artifacts remain unchanged.

## A37 planned

A37/V51 is the direct follow-up after A36's limited quality result. It keeps
V50's observation-language minimal patch, layered-memory authority boundary,
hard-conflict routing, OpenAI-only provider, disabled backup, disabled hybrid
recall, and no-Polisher controls. V51 adds only a shared prompt surface for
one character choice grounded in existing character-card constraints or
already accepted state, rendered through a visible tradeoff or direction
change. Thin characterization remains a warning and cannot trigger a Writer
retry. No model call, database field, memory layer, or frontend surface is
added. The implementation and prompt tests are recorded in
`docs/plans/2026-08-16-v51-character-agency.md`; the fresh A37 run is pending
launch from the fixed chapter-1 seed.

## A37 first attempt excluded

A37/V51 first ran on project `aea4b0b7-07b1-4f59-95cf-045156add124` from the
fixed chapter-1 seed. Chapter 2 completed at `8.71/10` with `0/1/0`
content/API/JSON retries, `9` LLM attempts, and `338.663s`. Continuity and
foreshadowing were both `9`; character portrayal and writing were both `8`.
The chapter is retained as a runtime observation but excluded because the
optional Editor `destyle` and Extractor `summarize_change_candidates` prompt
snapshots lacked the V51/V50 markers. The character-card extraction branch
also lacked the marker and hit a recursion-limit skip. The auxiliary prompt
surface was fixed and a clean A37-r2 is required before ranking.

## A33 startup

A33/V47 is the direct follow-up. It starts from the same fixed chapter-1 seed
in isolated project `2f513f62-f7ee-4454-90b1-cd312f27c4b2`, with job
`f676448b-8afb-4235-81ba-725eb6590324`. It keeps V46's memory and authority
controls and adds only the narrative-realization prompt surface. The run
directory is
`data/research_runs/ariadne-a33-v47-narrative-realization-no-polisher-10ch-20260816/`.
The ten-chapter result is pending. The first three completed chapters
currently score `8.14`, `8.57`, and `8.57`; all have `0` content retries and
no API or JSON retries. No V50 minimal-patch event has been needed yet, so
this remains an in-progress observation rather than a final ranking result.

The first A33 attempt is excluded because its stale Worker rendered none of the
V47/V46/V19 prompt markers. Its raw artifacts remain under
`data/research_runs/ariadne-a33-v47-narrative-realization-no-polisher-10ch-20260816/`.
The clean r2 run passed the startup gate. Chapter 2 completed at `8.14/10`
with `0/0/0` content/API/JSON retries, 6 LLM calls, `191.987s` wall clock,
`26696/9010` input/output tokens, and average memory context `3467.5`
characters. Chapters 3-10 are still running under the r2 directory.

## A38 partial result

A38/V52 implemented a visible consequence chain on top of V51: a finite action,
an observable response, and a visible change in strategy, risk, position, or
cost. The clean run used project `c4ca3143-fdda-4df3-92e6-1cade69ba908` and
`data/research_runs/ariadne-a38-v52-visible-consequence-chain-10ch-20260816/`.
It completed chapters 2-4 with qualities `8.43`, `8.71`, and `7.29`; content,
API, and JSON retries were `0/0/0`, `0/0/0`, and `0/0/0`, while chapter 4 used
two extra calls for local repair. Chapter 4 continuity was `4/10` because it
replayed chapter 3's completed action and response sequence. A38 is valid
partial evidence but excluded from the ten-chapter ranking. The full record is
in `docs/research/novel-memory-continuity/ariadne/versions/A38.md`.

## A39 planned

A39/V53 is the direct follow-up. It adds a deterministic completed-event ledger
and previous terminal state to the existing handoff, then requires a non-empty
`new_stage_delta` shared by Planner, Writer, Editor, Validator, and Extractor.
It keeps V52's low-retry and authority rules, adds no model call, and starts
from a fresh project and memory namespace. The implementation plan is
`docs/plans/2026-08-16-v53-cross-chapter-stage-ledger.md`; the version record is
`docs/research/novel-memory-continuity/ariadne/versions/A39.md`.

## A39 partial result

A39/V53 ran from the fixed chapter-1 seed in isolated project
`94fab255-5f91-478e-a780-e505dde2af74`, using OpenAI / `gpt-5.6-luna`, no
backup provider, hybrid recall disabled, and a new layered-memory namespace.
Chapters 2 and 3 published at `8.71` and `8.57`; both had continuity `9/10`
and `0/0/0` content/API/JSON retries. Chapter 4 reached a best evaluated
quality of `8.57` and continuity `9`, but paused after three recorded content
retry events. The errors were same-chapter duplicate submission and the
unknown field label `不可见`, not cross-chapter replay. A39 proves the
cross-chapter ledger direction but fails the low-retry runtime gate and is
excluded from formal ranking. Raw artifacts remain under
`data/research_runs/ariadne-a39-v53-cross-chapter-stage-ledger-10ch-20260816/`.

## A40 planned

A40/V54 is the direct next version. It keeps V53's cross-chapter ledger and
adds a bounded unique-action ledger plus a narrow Editor-local repair path for
same-operation resubmission and unknown-label over-assertion. The plan is
`docs/plans/2026-08-16-v54-intra-chapter-action-repair.md`; the version record
is `docs/research/novel-memory-continuity/ariadne/versions/A40.md`.

## A40 partial result

A40/V54 was paused before Writer started chapter 3 and is excluded from the
formal ten-chapter ranking. Chapter 2 completed at `8.71/10` in `232.757s`
with `6` LLM calls and zero content/API/JSON retries. The scores were
plot `9`, character `8`, world `9`, writing `8`, logic `9`, continuity `9`,
and foreshadowing `9`. The chapter avoided the known duplicate-operation
failure, but the review still noted repeated unknown-information explanation
and procedural query language. Chapter 3 has only a Planner artifact. Raw
events and prompts remain under the A40 run directory.

## A41 planned

A41/V55 directly follows A40. It adds a single shared `primary_action` turn:
one core action, one observable response, one character decision or cost, and
one new stage. V54's action ledger remains backward-compatible but is no
longer the main narrative driver. V55 adds no model call, database field,
memory layer, or frontend surface. The implementation plan is
`docs/plans/2026-08-16-v55-primary-action-turn.md`; the version record is
`docs/research/novel-memory-continuity/ariadne/versions/A41.md`.

## A41 partial runtime

A41/V55 is running from fresh project
`d737deae-f935-4d86-ae6d-b8d2632ed39b`, with the new memory namespace and the
fixed published chapter 1 only. Chapters 2-6 currently score
`8.57, 8.57, 8.71, 8.57, 8.71`; continuity is `9` in each. Content retries are
`0, 0, 0, 0, 0`, API retries are `0, 1, 0, 0, 0`, and JSON recoveries are all zero.
The run has used `32` LLM calls and `1119.939s` summed chapter wall time, with
`232747/51517` input/output tokens. V55's generated Planner output contains
the shared `primary_action` object, and no cross-chapter replay or hard
conflict has appeared. Chapter 7 is in progress; raw artifacts remain under
`data/research_runs/ariadne-a41-v55-primary-action-turn-10ch-20260816/`.

## A42 planned

A42/V56 is the direct next version after the A41/V55 quality observation. The
implementation plan is `docs/plans/2026-08-16-v56-character-driven-tension.md`;
the version record is `docs/research/novel-memory-continuity/ariadne/versions/A42.md`.
It preserves V55's single external action and adds a source-bounded
`character_turn` so Planner and Writer share the character goal, pressure,
choice basis, personal cost, and state change. It adds no default model call,
database field, memory layer, or frontend surface. A41 is paused and its
partial artifacts remain excluded from ranking.

## A42 runtime update

The first A42 launch was excluded after stale Worker processes failed to load
the V56 code: its Prompt snapshots lacked the V56 marker and its first quality
event was incomplete at five dimensions. The artifacts remain preserved under
`data/research_runs/ariadne-a42-v56-character-driven-tension-10ch-20260816/`.

A clean A42-r2 run is active from fresh project
`93bf248d-bb53-483b-acb3-d7e00dd551ac`, with artifacts under
`data/research_runs/ariadne-a42-v56-character-driven-tension-r2-10ch-20260816/`.
The Prompt gate passed for Planner and Writer. Chapter 2 currently scores
`8.43/10` with all seven dimensions complete, zero content/API/JSON retries,
and one local Editor repair. The run remains in progress and is excluded from
formal ranking until chapters 2-10 complete.

## A43 result

A43/V57 tested the compact role-specific surface intended to remove the
accumulated V45-V56 audit chain. Its first launch was excluded because the
Worker was stale and its Writer snapshot lacked V57. The clean r2 run used
project `1ffa8571-f236-4ef6-a9f4-30f6adb66723` and
`data/research_runs/ariadne-a43-v57-compact-character-surface-r2-9ch-20260816/`.

Chapter 2 passed the V57 prompt gate and completed with `8.0/10`; dimensions
were plot `8`, character `7`, world `8`, writing `8`, logic `8`, continuity
`9`, and foreshadowing `8`. Content/API/JSON retries were `0/0/0`. The Planner
omitted both `primary_action` and `character_turn`, so the Writer fell back to
a procedural question/record/wait loop. A43 was paused before chapter 3 and
is excluded from ranking. The raw project, prompts, response, and quality
event remain preserved. A44/V58 adds explicit non-empty turn requirements and
deterministic source-bounded fallback projection.

## A44 planned

A44/V58 is the direct follow-up to the A43 failure. It keeps V57's compact
generation surface but makes `primary_action` and `character_turn` required,
non-empty Planner outputs with fixed fields. The shared contract fills only
missing fields from existing `character_goals` and `primary_action`, without a
new model call or invented facts. A fresh fixed chapter-1 seed, OpenAI-only
routing, disabled backup, disabled hybrid recall, and local Chroma embeddings
are required. The first Planner and Writer snapshots must show V58 and a
non-empty normalized turn before the batch continues.

## A44 partial result

A44/V58 passed its startup gate on project
`72e06a86-c3ed-44be-a3ee-6ee5c80e9389` and run
`ariadne-a44-v58-structured-character-turn-9ch-20260816/`. Chapter 2 completed
at `8.71/10` with dimensions `9/8/9/8/8/10/9` for plot, character, world,
writing, logic, continuity, and foreshadowing. It used `6` successful LLM
calls, `7` attempts, `0` content retries, `1` API retry, `0` JSON recoveries,
and `448.81s` wall-clock time. The Planner output contained non-empty
`primary_action` and `character_turn`, and the Writer prompt received the same
contract. This is valid partial evidence, but it is excluded from the formal
ten-chapter ranking because the run was stopped after chapter 2 for the next
controlled variant. Raw events, prompts, responses, and memory snapshots remain
preserved under the run directory.

## A45 planned

A45/V59 is the direct follow-up to the A44 observation. It keeps V58's
structured turn, layered-memory authority boundaries, retry policy, provider,
embedding, and no-extra-call controls. V59 changes only the role-specific
realization hints: Planner, Writer, Editor, Validator, and Extractor use the
same action-first order of scene pressure, character choice, immediate visible
consequence, one necessary reveal, and new state. The goal is to reduce
procedural question/record/explain prose and improve character portrayal and
writing quality without increasing content retries or model calls. The plan is
`docs/plans/2026-08-16-v59-action-first-realization.md`; the version record is
`versions/A45.md`. A fresh fixed chapter-1 seed and V59 prompt gate are required.

The first A45 launch was excluded at the startup gate. The V59 Planner hint
had replaced V58's explicit object-shape instruction, and the model returned
string values for `primary_action` and `character_turn`; the backend rejected
the schema before Writer started. The raw failed launch remains under
`data/research_runs/ariadne-a45-v59-action-first-realization-9ch-20260816/`.
V59 was repaired to restate the fixed fields, and a clean A45-r2 must start
from a fresh project and memory namespace.

## A45 runtime observation

A45-r2 passed its startup gate and was intentionally stopped after chapter 3
for the next controlled variant. Chapters 2 and 3 scored `8.71` and `8.57`,
with `0/0/0` content/API/JSON retries and `6` successful LLM calls each.
Wall-clock times were `267.777s` and `417.805s`; average memory context grew
from `3983` to `5892` characters. The chapters preserved continuity at `9/10`
and `8/10`, but the prose still leaned on device query, record, and explanation
as the main visible event. This is valid partial evidence, excluded from the
ten-chapter ranking, and retained under
`data/research_runs/ariadne-a45-v59-action-first-realization-9ch-20260816-r2/`.

## A46 planned

A46/V60 is the direct follow-up. It keeps V59's structured turn, memory and
retry controls, and adds only an external-consequence boundary: a choice must
change a scene state outside the interface (position, access, item, risk, time,
relationship, or investigation direction), and the ending must be concretely
different from the opening. It adds no model call, field, memory layer, or
frontend surface. The plan is
`docs/plans/2026-08-16-v60-external-consequence.md`; the version record is
`versions/A46.md`.

## A46 partial runtime

A46 passed its clean startup gate with project
`1bc6aa0f-4da5-4558-8e2e-37c0236ba118`, OpenAI / `gpt-5.6-luna`, disabled
backup and hybrid recall, and local Chroma embeddings. Chapter 2 completed at
`8.71/10` with seven dimensions `9/8/9/8/9/9/9`; content/API/JSON retries were
`0/1/0`, successful calls/attempts were `6/7`, and wall clock was `413.411s`.
The body shows the intended external consequence: Lin Mo moves from a
retreatable distance to the device, does not enter the tower, and changes the
investigation direction from device output to who previously stood at the
door. The evaluator still found repeated explanation of device limitations.
Chapter 3 has entered Planner and the run remains active; no ten-chapter
ranking conclusion is made yet. Raw artifacts are under
`data/research_runs/ariadne-a46-v60-external-consequence-9ch-20260816/`.

## A49 planned and runtime

A49/V63 is the direct follow-up to A48/V62. It keeps the stage-breakthrough,
state-progression, character-turn, authority-boundary, OpenAI-only, no-extra-
call, and low-retry controls, and adds only a prompt-level chapter-closure
rule: every chapter must define one locally judgeable objective and realize
goal -> resistance -> choice -> result. A result may be success, failure,
cost, or a concrete condition ruled out; a new location or new unknown alone
does not count. The plan is
`docs/plans/2026-08-16-v63-chapter-closure.md`; the version record is
`versions/A49.md`.

The clean run uses project `fbde6fc8-328c-4ba8-9d59-f33a28a7d280` and
`data/research_runs/ariadne-a49-v63-chapter-closure-10ch-20260816/`. Its
startup gate passed with V63 markers in all five Agent prompt snapshots,
OpenAI / `gpt-5.6-luna`, backup and hybrid recall disabled, and an empty new
layered-memory namespace before chapter 2. Chapter 2 published at `8.71/10`
with dimensions `9/8/9/8/9/9/9`, `0/0/0` content/API/JSON retries, `6/6`
successful calls/attempts, `205.603s` wall-clock time, `59,392/9,329`
input/output tokens, and average memory context `3,856.33` characters. The
chapter ruled out real-time communication and changed the investigation
direction toward receipt time/source. Chapter 3 is in progress; no
ten-chapter ranking conclusion is made yet.

## A50 runtime update

A50/V64 is the direct follow-up to A49/V63. It keeps V63's chapter closure and adds a prompt-only inherited-state boundary: `completed_event_ledger`, `previous_terminal_state`, and `inherited_state` are opening conditions, not actions to replay. The implementation plan is `docs/plans/2026-08-16-v64-cross-chapter-stage-transition.md`; the version record is `versions/A50.md`. No schema, database table, memory layer, or model call was added.

The clean run uses project `3d4b20af-eeea-4462-9159-f33a28a7d280` and artifacts under `data/research_runs/ariadne-a50-v64-cross-chapter-stage-transition-10ch-20260816/`. The startup gate passed with V64 markers in Planner and Writer prompts, OpenAI / `gpt-5.6-luna`, local Chroma embeddings, disabled backup, and disabled hybrid recall. Chapters 2 and 3 have completed with available quality averages `8.4` and `8.4`; both used `6/6` calls/attempts and `0/0/0` content/API/JSON retries. Wall-clock times were `210.774s` and `234.404s`, with input/output tokens `55,503/8,892` and `70,898/10,878`. The first two chapters moved into new investigation stages without the V63 failure mode of replaying the prior chapter's completed exit or unchanged-device state. Chapter 4 is in progress; the ten-chapter ranking remains pending.

## A51 / V65 result

A51/V65 is the direct follow-up to A50/V64. V64's chapter 5 exposed two source-boundary overclaims: a drag mark was written as proof that the先行者 carried and dragged an item, and an interface line was written as proof that a real object had moved. V65 keeps the cross-chapter stage boundary but adds a shared observation -> bounded inference -> unresolved boundary rule. It routes this narrow class to the existing Editor local-repair path when no accepted fact, actual item state, location, timeline, character state, or core event is changed. The clean run completed chapters 2-10 with quality `8.333`, continuity `8.778`, foreshadowing `8.444`, content/API/JSON retries `0/0/0`, two local repairs, and `58/58` LLM calls/attempts. It is below the overall quality gate and is not the production choice. The plan is `docs/plans/2026-08-16-v65-evidence-boundary-gate.md`; the version record is `versions/A51.md`.

## A52 / V66 partial result

A52/V66 is the direct follow-up to V65. It replaces the chained generation hint surface with a compact role-specific execution surface focused on one concrete character choice, visible response, personal cost, and a changed terminal state. The run was paused by user direction after five chapters completed and chapter 7 entered its hard-conflict repair path. Six preliminary quality events averaged `8.57`, with preliminary character portrayal `8.33` and continuity `9.0`; all recorded content/API/JSON retries were `0/0/0`. Because the run is incomplete and chapter 7 did not finish, it is excluded from formal ranking. Full details are in `versions/A52.md`; all raw artifacts remain under `data/research_runs/ariadne-a52-v66-compact-character-texture-10ch-20260816/`.
