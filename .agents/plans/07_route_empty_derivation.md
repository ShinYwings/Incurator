# v0.65.0 Master Implementation Plan — Route the empty derivation

Arena record: `.agents/plans/route_intent_arena/`
(`00_problem.md`, `02_synthesis.md`)

## 1. Objective

A knowledge question the extractor finds **no search target** in is a question
about the corpus, not about an entity in it. Route it to `global`, which is built
to work without a query, instead of laundering the empty derivation through
`(english_query or question)` into a raw-Korean `local` search.

Measured on the live vault for the briefing's case 2:

| route | result |
|---|---|
| `local` (today) | **8 items**, all raw-Korean FTS5 hits, **0 entities, 0 of 417 community reports** |
| `global` | **10 community reports**, no warnings |

## 2. Explicit Non-Goals

- **Not** fixing case 1 (intent dropped from a non-empty query). That needs a
  derived intent signal — Arena proposal A — and is its own release. This plan
  must not silently appear to cover it; a test pins that it still routes `local`.
- **Not** changing `working_query`'s fallback. For the never-derived state the
  fallback is still the best available behaviour, and for the routed state
  `global` ignores the query anyway. Changing it would touch three consumers for
  no gain.
- **Not** touching `derive_search_query`'s signature, its prompt, or any prompt
  contract version.
- **Not** fixing `plugin_api/query_api.py:146`. It is real, it is **not the chat
  path** (Arena correction 1), and pricing it as one is how this item got
  misdiagnosed twice.

## 3. Strict Quality Conditions & Release Gates

- `scripts/backend-check pytest`, `ruff`, `mypy` clean before each phase ends.
- `npx vitest run -c ./plugin/vitest.config.ts` green (no plugin change expected;
  the gate stays because the version bump touches plugin manifests).
- Live check on the real vault: case 2 flips to `global` with community reports;
  **case 1 still routes `local`** — the known gap stays visible, not papered over.

## 4. Locked Design Decisions (Arena Consensus)

**D1 — An empty derivation is a named state, not an absent value.**
`QueryRequest.english_query_status` ∈ `{"unset", "derived", "no_search_target"}`,
defaulted to `"unset"` so every existing constructor keeps its behaviour.
`(english_query or question)` collapses three distinct states into two; naming
the third is the whole fix.

**D2 — Route through `_pick`, never by setting `mode`.** Setting `mode="global"`
at the call site works and touches one fewer file, but writes
`"explicit --mode"` into the trace of a user who passed no mode. In a system
whose product *is* traceability that is a bad trade. `_pick` also degrades
correctly when `curate.yml` forbids `global`, and records why.

**D3 — `global` is correct here by construction, not by guess.**
`evidence.py:341` — `if not query_terms: return rep.get("rank", 0.0)`;
`evidence.py:382` `_synthesis_items` takes no query. Meanwhile `local` seeds
entities from `seed_terms(query)`, and `seed_terms("")` returns `[]`.

**D4 — Deliver the warning `evidence.py:193-198` already promises.** It states
that `context_fetch` warns when a non-English question reaches seeding;
`context_service.py` never inspects `english_query` at all. A documented
invariant with no implementation is why A1 was misdiagnosed twice. This ships
even if the rest is contested.

**D5 — Forward-compatible with proposal A.** An `intent` signal never subsumes
this case: an intent of `local` attached to an *empty* query is still an empty
query hitting `seed_terms → []`. D1's branch stays correct after A lands.

## 5. Scope Exclusions & Stop Conditions

- **STOP if `global` on an empty query proves not to return reports** on the
  testbed as it did on the live vault. The whole plan rests on D3.
- **STOP if `english_query_status` cannot be set unambiguously** at
  `context.py:80` — i.e. if `is_knowledge=True` with an empty query turns out to
  be reachable for a reason other than "no search target".
- Out of scope: case 1, `query_api.py`, and the instrumentation gap (§7).

## 6. Evidence Ledger

`.agents/plans/07_route_empty_derivation_evidence.md`, created immediately before
P1. Records the rollback anchor, the live-vault before/after for both cases, and
the testbed run.

## 7. Execution Phases (TDD + CI at each phase)

**P1 — Name the state.** `english_query_status` on `QueryRequest`
(`retrieval/models.py`), set at `plugin_api/context.py:80`.
*Verify:* a stubbed client returning `{"search_query": "", "is_knowledge_question": true}`
produces `english_query_status == "no_search_target"`; `is_knowledge=False` still
short-circuits at `context.py:63` and never reaches the router.

**P2 — Route it.** One branch in `choose_route` after the `source_key` check and
before `q = request.working_query`.
*Verify:* `no_search_target` + reports → `global`; + `curate.yml` allowing only
`local` → degrades to `local` **with the reason naming the downgrade**;
`"derived"` with a non-empty query → unchanged; `"unset"` → byte-identical on all
existing router tests.

**P3 — Land the promised warning (D4).** In `build_evidence`, when the status is
`"unset"` and `seed_terms(q)` is empty.
*Verify:* the test fails against today's code — that is the point.

**P4 — Docs and specs.** `SYSTEM_BEHAVIOR.md` §17 routing rules,
`USER_GUIDE.md` + `_KR.md`. 0.64 → 0.65 changes the minor line, so **all four
spec titles bump** and `test_spec_sync.py` must pass.

**P5 — Live validation (release gate).** Both briefing questions through
`wiki plugin context fetch` on the real vault: case 2 → `global` with non-empty
`community_report_ids`; case 1 → still `local`, recorded as the known gap.

## 8. Filed, not fixed

- **Case 1 → ROADMAP A1**, rewritten to carry proposal A's shape.
- **`curator.query_router` is registered, pinned in two specs, and has zero
  production call sites.** Per CLAUDE.md *"any divergence means both are wrong
  until reconciled"*: either A's intent lands on that contract id or the spec
  drops it. New ROADMAP item.
- **The system cannot report this class of event.** `query_traces` stores
  `question_hash`, `prompt_runs` stores hashes, `retrieval_trace_json` records
  `is_cjk` but never the query or its emptiness — so "the extractor found no
  search target" is invisible after the fact. New ROADMAP item; it is why this
  took three diagnoses.
