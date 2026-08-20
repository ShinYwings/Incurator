# Defense: F1 and F2 measured

Date: 2026-08-21 | Agent Persona: lead_architect (responding), with schema_guardian

> **This document was rewritten after a second pass.** The first version claimed
> F1 showed the proposal's premise "wrong in practice" and that partials would be
> reported as knowledge across five surfaces. Measuring further shows that
> overstated the severity, and got the direction wrong: the codebase's *writer*
> side already agrees with the proposal. The corrected finding is below, and it
> is the one the plan is built on.

## 1. F2 — the cost, measured

Benchmark on a copy of the live DB (233 MB), source 45 (Hartley, 8,905 spans,
277 batches as actually run). Units per batch bracketed by the observed
unit-to-span ratio: 32/batch (1 unit per span) to 93/batch (source 37's measured
2.9). Script: `scratchpad/f2_bench.py`.

| units/batch | bulk (current) | per-batch (proposed) | one batch: median / p95 / max |
|---|---|---|---|
| 32 (8,864 total) | 0.52 s | 2.52 s (4.8x) | 8.9 / 10.0 / 36.0 ms |
| 93 (25,761 total) | 1.32 s | 5.02 s (3.8x) | 17.9 / 21.7 / 67.4 ms |

`db.connect()` alone is 1.83 ms and is paid 277 times = 0.51 s of that.

**4x sounds bad and is irrelevant.** The comparison that decides it is against
the LLM call the batch just made. Over 1,811 real `knowledge_unit_extract` runs
in the live DB: **median 18,631 ms**, mean 22,747 ms, max 132,271 ms.

So per-batch persist adds **9–18 ms to an 18.6 s batch — 0.05% to 0.1%** — and
2.5–5.0 s to an extraction phase that is 277 × 18.6 s ≈ **86 minutes**. The
absolute numbers are seconds against hours. **F2 is answered; cost is not an
objection.** Lock granularity improves too: 277 locks of ~9 ms each instead of
one held for 0.5–1.3 s.

## 2. F1 — the readers, enumerated as demanded

27 reads of `knowledge_units`. **15 do not filter on `generation_id`.** The red
team was right that the proposal had not audited them. It was wrong about what
the audit would show.

**Safe — scoped by primary key.** `claim_support.py:201`, `:560`,
`_entities.py:372` and friends read `WHERE id = ?`. A caller holding a unit id
already knows what it has.

**Safe — joined to a generation.** `materializer.py:269` joins
`compiler_generations` on `ku.generation_id`, so a NULL cannot match. **The
search corpus cannot see a partial.** That is the reader that mattered most and
it is already correct.

**Safe by ordering — `reconcile_source` (`:645`).** This one both retires units
and stamps `generation_id`, so an unfiltered read here would be the one genuinely
dangerous site. It is not, because of when it runs: `compile.py:418` stamps
every `ku_result.unit_ids` with the staged `gen_id` immediately after extraction
returns, and `reconcile_source` runs later, at `:449`. By then this run's units
are not NULL. A *previous* run's partial is either discarded by
`_discard_unpublished_units` or kept as this run's candidate — and reconcile
skips candidates (`if unit_id in candidate_ids: continue`).

**Not publish-blocking, verified three ways.** `publish_blocking` is
`dangling_supports | formula_inconsistencies | staged_leftovers`; it excludes
`unsupported_claims`. A partial contributes to none of the three:

- `dangling_supports` — `_discard_unpublished_units` deletes `claim_supports`
  *before* the units, keyed on exactly `generation_id IS NULL AND retired_at IS
  NULL`. A discarded partial leaves nothing dangling.
- `formula_inconsistencies` — `formula_status` defaults to `'not_applicable'`,
  which is neither of the two values that trigger the check.
- `staged_leftovers` — counts authoritative generations, which a partial has not
  got.

`wiki lint` classes `unsupported_claims` as **INFO**, so it still exits zero.

**What is actually exposed**, then, is narrow and none of it is corruption:

| site | effect of a durable partial |
|---|---|
| `claim_support.py:490` | inflates `unsupported_claims` → INFO lint lines, one per unit. For Hartley that is ~25,000 lines: a usability failure, not a correctness one |
| `claim_support.py:520` | partial units group with published ones by `semantic_hash` → false `duplicate_candidates` hints |
| `synthesis_audit.py:159` | `SELECT * FROM knowledge_units` with **no filter at all** — pulls partials into dependency collection when spans intersect |

## 3. What that means for the design

The proposal's premise holds where it counts. `_discard_unpublished_units`
already keys on `generation_id IS NULL AND retired_at IS NULL` to mean
"extracted, not authoritative" — **the writer side is already built on exactly
the invariant the proposal wants to lean on**, and the publish path stamps
`generation_id` as its first act. The disagreement is confined to read-side
telemetry.

So the choice the first draft posed — patch five readers, versus a separate
staging table — is not balanced. A staging table duplicates the
`knowledge_units` + `claim_supports` schema to solve INFO-level lint noise and
one unfiltered audit scan, and it re-opens what v0.52.0 removed. **Take the
filters.** Three sites need `generation_id IS NOT NULL`; today that is provably
inert (partials never survive a call), so the change can be validated by running
the audit on the live DB before and after and diffing the report.

The residual risk is a future reader written the same way — and
`synthesis_audit`'s unfiltered `SELECT *` shows the habit is real. That is worth
one structural test asserting no table-wide read of `knowledge_units` outside
the ingest path lacks the filter, in the manner of `test_workspace_hygiene.py`.

## 4. Still outstanding

F3 (`_config_key` not provably covering the prompt), F4 (test the conditional
discard), F5 (no expiry, nothing surfaces partials) and F6 (changed source)
remain conceded and unaddressed. F5 is now cheaper than it looked: partials are
INFO-visible in `wiki lint` rather than invisible.
