# Critique on Copy-On-Stage Generation Isolation

Date: 2026-06-13 | Agent Persona: red_teamer + schema_guardian + source_pair_analyst

## 1. Vulnerabilities & Flaws

**R1 — Filesystem/DB split-brain on publish.** The proposal commits the DB txn,
then moves ATM staging-dir pages into `02_Atoms/`. If the process dies between
the two, the DB says authoritative but the live pages are missing (or stale
gen_A pages linger). Filesystem moves are not in the DB transaction.

**R2 — Search QUERY now joins `compiler_generations` on every search.** Every
read path (`search.query`, evidence packs, `materialize_chunks`) must add the
join + filter. Miss one caller and staged docs leak — the exact defect we are
fixing, reintroduced silently. The D2 holdout pins `lexical.py`/`engine.py`/
`fusion.py` SHA — a query-path change there is NOT metric-neutral and breaks the
holdout legitimately (cannot just re-arm).

**R3 — `reconcile_publish` carries gen_A rows into gen_S by re-pointing
`generation_id`.** But gen_A's units may be cited by L3/L4 (community reports,
synthesis) via `artifact_dependencies` and by graph entities. Re-pointing the
unit's generation_id is fine (id stable), but the gen_A row's claim_supports,
dag_edges, and graph linkage must remain consistent. Changed claims get NEW ids
→ every downstream artifact citing the OLD changed-claim id is now dangling.
This is the F7 closure problem at L2→L3/L4 scale; the proposal hand-waves it.

**R4 — `support_status='verified'` is still load-bearing.** If visibility keys on
generation status, an uncertain/failed unit inside an authoritative generation is
correctly excluded by `support_status='verified'` — but a staged generation that
publishes with a still-`unchecked` unit (validate not run / model unavailable)
would hide it correctly, yet `recompile_source` audits `publish_blocking` which
EXCLUDES unchecked. So an authoritative generation can contain unchecked units
that are simply never served. Is that intended? Need an explicit invariant:
"authoritative generation may contain non-verified units; they are stored,
audited, but not served." Confirm against §20.3.

**R5 — Migration ordering vs `db_sync`.** `compiler_generations` and the new
`search_documents.generation_id` are synced tables. A device that imports a
pre-migration DB then runs the migration must converge with a device that
migrated first. Synthetic-generation ids must be DETERMINISTIC (content-derived,
not random `GEN-<uuid>`) or two devices mint different ids for the same legacy
units → LWW conflict / duplicate authoritative generations per source (violates
§20.5 #4).

**R6 — Idempotency short-circuit hides a real staleness bug.** The short-circuit
returns the prior summary when `content_hash` matches. But if a PRIOR publish
half-failed (R1) leaving FS stale, the short-circuit will never repair it
(content unchanged → no recompile). Need a "repair/verify authoritative" path,
or make discard/publish fully recoverable.

**R7 — Empty staged generation = data loss.** If extraction yields zero units
(parse produced no claims) but the audit "passes" (nothing to block), publish
would flip an EMPTY gen_S authoritative and discard a non-empty gen_A — silently
deleting the prior good compile. Need a guard: a staged generation with fewer
units than prior, or zero, requires an explicit reason / blocks publish.

**R8 — Blast radius vs the 810-test suite.** Splitting `list_eligible_knowledge_
units` into serving/compiler variants touches `compile.py`, `graph_index.py`,
`materializer.py`, `evidence.py`, `query.py`, `search.py`. Each has tests
asserting current (generation-agnostic) behavior. Expect a large red→green churn;
risk of masking a real regression as "expected test update."

## 2. Suggested Alternatives

- **A1 (R1/R3/R7):** Defer ALL ATM page writes + graph re-emit to publish, emit
  from `list_generation_units(gen_S)` AFTER the DB commit, and on FS failure
  re-emit from the authoritative DB (projections are disposable → DB is truth).
  This removes the staging dir and makes FS strictly derivable. Add a publish
  guard: refuse to publish a gen with 0 units when a non-empty authoritative gen
  exists unless `--allow-empty`.
- **A2 (R2):** Gate search visibility at MATERIALIZATION, not query. Only
  authoritative-generation units are ever materialized into `search_documents`
  (staged docs are simply never written until publish). Then `search.query`
  needs NO change and the D2-pinned retrieval files are untouched. Staging emits
  search docs only at `swap_search_materialization` (publish). This is strictly
  simpler and keeps the holdout valid.
- **A3 (R3):** Keep stable-id reuse at STAGE time (reconcile staged candidates vs
  prior authoritative BEFORE building graph), so downstream artifacts are built
  against final ids and the L2→L3/L4 closure is consistent within the staged
  generation — same as today's `reconcile_source`, just generation-scoped.
- **A4 (R5):** Synthetic migration generation id = `GEN-mig-<source_id>` or a
  hash of `(source_id, schema_version)` — deterministic across devices.
- **A5 (R4):** Add the explicit invariant to SCHEMA §20.3 / §20.5: an
  authoritative generation MAY hold non-verified units (stored + audited, never
  served); visibility = authoritative-gen ∧ verified ∧ not-retired.
