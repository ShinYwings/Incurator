# Critique on Master Plan B2 (Second Review Round)

Date: 2026-06-13 | Agent Persona: red_teamer (external reviewer)

All three accepted as REAL against the v1 master plan. Verbatim:

## 1. Vulnerabilities & Flaws

**Fatal Flaw 1 — The Primary Key Paradox (stable-id reuse at stage time is
impossible).** Item 4 ("stable-id reuse stays at STAGE time") contradicts the
byte-identical-prior-state guarantee. `id` is the PK of `knowledge_units`; the DB
cannot hold both the authoritative `KU-1` and a staged `KU-1` as separate rows.
If `reconcile_source` updates `KU-1` in place during staging, it mutates the
authoritative row before the gate, destroying rollback.
> Rewrite: defer stable-id reconciliation to PUBLISH time. Staged units get
> temporary ids (`KU-temp`). On a passing audit, the atomic publish transaction
> merges `KU-temp` into the stable `KU-1` row, sets `KU-1.generation_id=gen_S`,
> rewrites downstream JSON array references (e.g. `graph_entities`) from
> `KU-temp` to `KU-1`, and deletes `KU-temp`.

**Fatal Flaw 2 — Graph leakage (unstaged L2 graph entities).** Item 1 ignores
that `compile_source_l2` immediately upserts `graph_entities`/`graph_relations`,
which have NO `generation_id` and so bypass the publish gate — instantly visible,
and permanently leaked (with dangling refs to discarded staged units) if the
compile later fails.
> Rewrite: do NOT upsert graph output during staging. Serialize it (e.g. in
> `compiler_generations.audit_json`) and run the `upsert_graph_entity`/relation
> calls strictly inside the post-audit atomic publish transaction.

**Fatal Flaw 3 — Zero-unit publish guard violates source truth.** Item 8's
unconditional block traps the authoritative generation stale when a user
legitimately empties a source (zero claims is the correct deterministic outcome),
forcing the index to serve deleted claims forever.
> Rewrite: remove the zero-unit publish guard. A successful zero-unit generation
> is valid and must publish, retiring the old authoritative units.

## 2. Verification against the codebase (this agent)

- `graph_entities.knowledge_unit_ids` and `graph_relations.knowledge_unit_ids`
  (db.py:296) are JSON arrays of unit ids → confirmed downstream-reference
  surface for the Flaw 1 publish-time rewrite. Also rewrite/repoint:
  `claim_supports.knowledge_unit_id`, `artifact_dependencies` (artifact_id /
  depends_on_id), and `dag_edges` rows that reference the temp unit/atom.
- `graph_index.extract_entities_and_relations` currently extracts (LLM) AND
  upserts in one call → Flaw 2 requires splitting extract (staging, against temp
  ids, serialized) from persist (publish txn, rewritten to stable ids).
- Flaw 3: a FAILED extraction already returns `ku_result.ok=False` → compile
  errors without publishing, so removing the guard does not reintroduce silent
  loss from extraction failures; only a SUCCESSFUL empty extraction publishes
  empty (correct). Keep a non-blocking audit log when a publish retires N>0
  prior units down to 0.
