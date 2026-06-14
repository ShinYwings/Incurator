# Synthesis / Defense

Date: 2026-06-13 | Agent Persona: system_synthesizer

The red-team's A1+A2+A3 collapse the proposal's complexity and remove its two
worst risks (R1 FS split-brain, R2 query-path leak / D2 holdout breakage). The
final design gates visibility at **write/materialization time**, not read time:

**Resolved design (adopted into the Master Plan):**

1. **Staged units never become served artifacts until publish.** A staged
   generation's `knowledge_units` rows exist (`generation_id=gen_S`,
   gen status `staged`) but the compiler does NOT emit ATM pages, build graph
   linkage, or materialize search docs for them while staged. Therefore serving
   surfaces (search.query, evidence) need **no change** — they read what is
   materialized, and only authoritative-generation units are ever materialized
   (A2). The D2-pinned retrieval/query files are untouched.

2. **Emit/materialize AFTER publish, from the DB (A1).** Publish is a single DB
   transaction (flip gen_S→authoritative, retire gen_A rows). ATM pages + graph
   + search materialization are then (re)emitted from the now-authoritative
   units. Projections are disposable, so on any FS/materialization failure they
   re-emit from the authoritative DB (DB is truth) — no staging dir, no
   split-brain. Discard deletes only staged `knowledge_units`/`claim_supports`
   rows; no ATM/search were ever written for them.

3. **Stable-id reuse stays at STAGE time (A3),** generation-scoped: reconcile
   staged candidates vs the prior authoritative units before graph/materialize,
   so the L2→L3/L4 closure is built against final ids (resolves R3).

4. **Search visibility = materialization-only (A2).** No `search_documents`
   schema change, no query-path join. The materializer reads
   `list_serving_units` (authoritative + verified). (Drops the proposal's
   `search_documents.generation_id` column — simpler, and keeps `db_sync`/holdout
   untouched.)

5. **Migration (A4):** deterministic synthetic generation id per legacy source,
   `GEN-mig-<source_id>`, status authoritative; legacy verified units attributed
   to it. NULL generation_id thereafter = not a Plan-B claim.

6. **Invariant (A5), added to SCHEMA §20.3/§20.5:** an authoritative generation
   MAY contain non-verified (unchecked/uncertain/failed/stale) units — stored
   and audited, never served. Served = authoritative-gen ∧ verified ∧
   not-retired. Visibility no longer keys on `support_status` alone.

7. **Publish guards (R6/R7):** refuse to publish a staged generation with zero
   units when a non-empty authoritative generation exists (guard against
   silent loss); a half-failed publish is repairable by re-materializing from
   the authoritative DB (idempotent), so the unchanged-content short-circuit
   first verifies the authoritative materialization is present.

This keeps the blast radius to: the compiler write path (`compile.py`,
`graph_index.py`, ATM emit, `materializer`) + `list_eligible_knowledge_units`
split into serving/compiler variants + a migration. Serving READ paths and the
D2-pinned retrieval files are out of scope.
