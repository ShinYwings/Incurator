# Critique on lead_architect proposal (Schema & Migration)
Date: 2026-06-20 | Agent Persona: schema_guardian + source_pair_analyst (The Validators)

## 1. Vulnerabilities & Flaws

### Schema integrity (P-02 is the only real schema change)
- **`graph_relations.kind` does not exist yet.** The proposal treats `kind` as
  present; it is not in the `CREATE TABLE graph_relations` block (`db.py:358`). This
  requires a real `_migrate_vN_*` function (next after v9), forward-only, with a
  default `kind='semantic'` backfill so existing rows remain valid factual edges.
  `PRAGMA integrity_check = ok` and `schema_version` bump are mandatory post-migration
  gates (precedent: §26.5 v9, SYSTEM_BEHAVIOR §-migration blocks at lines 1790/2059).
- **Enum widening must not break the frozen quarantine reason codes.** `db.py:40`
  declares "Frozen relation quarantine reason codes." Adding `giant_component_hub`
  widens a *frozen* set — that is a contract change requiring `SCHEMA.md` update and
  a `test_spec_sync`-visible minor bump. Do not append silently.
- **Idempotent unchanged-rebuild invariant (§-2084).** Soft-alias generation must be
  deterministic for an unchanged corpus, or `wiki sync` re-running will churn
  `graph_relations` and break the "unchanged rebuild is identical" gate. The
  candidate-alias pass needs a content-hash guard like `compiler_generations`.
- **Unique index collision.** `idx_graph_entities_name (canonical_name, entity_type)`
  is UNIQUE. Soft-aliases must live in `graph_relations`, NOT as duplicate
  `graph_entities` rows — confirm the generator never tries to insert an alias as an
  entity (would throw on the unique index, or worse, merge identities).

### DAG / source-pair impact (P-06, P-03)
- **P-06 must preserve L1→L4 provenance.** The explore path currently surfaces
  `insight_candidate` rows tied to `source_event_id=trace_id`. Routing through
  `context_fetch` must keep `cand.source_span_ids` pointing at real L1 spans, or the
  backprop/promotion path (`02_Wiki/` HITL) loses grounding. Add an assertion that
  every promoted insight candidate's spans resolve to live `source_spans`.
- **P-03 healing touches `claim_supports`/`source_spans`.** Re-resolving orphaned
  spans must respect the `knowledge_units`→`claim_supports`→`source_spans` chain; a
  naive delete of an orphaned span id would cascade-break L2 atoms that legitimately
  reference it. Healing must quarantine, never hard-delete, span references.

### Spec synchronization (all phases)
- Each phase that changes a contract MUST update, in the same commit:
  `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md` (§31.x for 06/03, new §for 02/01),
  `docs/specs/curator_schema/SCHEMA.md` (graph_relations for 02), and the matching
  `docs/guides/*` + `_KR.md`. A minor bump touching the `MAJOR.MINOR` line forces the
  spec-title sync across all four spec files (`test_spec_sync`).

## 2. Suggested Alternatives
1. **One migration per schema-touching phase**, never a batch migration — keeps
   rollback anchors tight. P-02 owns exactly one `_migrate_vN_graph_soft_links`.
2. **Backfill `kind='semantic'`** for all existing `graph_relations` rows in the
   migration; assert count-preservation (no rows lost) as a migration test.
3. **Soft-alias generation gated by a `compiler_generations`-style hash** so an
   unchanged corpus yields zero new edges (idempotency gate).
4. **Healing = quarantine-only** on `lifecycle_status`; deletion is out of scope and
   explicitly a Non-Goal.
5. **Promote `noise_profiles` + atlas `candidates/` into `docs/specs/failure_atlas/`**
   so the eval contract stays spec-first and version-pinned.
