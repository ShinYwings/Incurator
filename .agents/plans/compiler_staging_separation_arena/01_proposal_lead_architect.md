# DB/Compiler Proposal: Copy-On-Stage Generation Isolation

Date: 2026-06-13 | Agent Persona: lead_architect (Compiler/DB)

## 1. Core Logic & Implementation

### Visibility model — generation status is the single gate

A `knowledge_unit` is **served** iff its owning generation is `authoritative`.
Generation status (`compiler_generations.status`) is the one source of truth for
visibility; no row is ever read by serving surfaces because of `support_status`
alone.

```sql
-- Serving eligibility (query / evidence / search materialization):
SELECT ku.* FROM knowledge_units ku
JOIN compiler_generations g ON g.id = ku.generation_id
WHERE ku.retired_at IS NULL
  AND ku.support_status = 'verified'
  AND g.status = 'authoritative';

-- Compiler-internal eligibility (building ATM/graph/search for ONE staged gen):
SELECT ku.* FROM knowledge_units ku
WHERE ku.retired_at IS NULL AND ku.support_status = 'verified'
  AND ku.generation_id = :staged_gen_id;
```

`list_eligible_knowledge_units` splits into two functions:
`list_serving_units(db, source_id=None)` (authoritative-only) and
`list_generation_units(db, gen_id)` (compiler-internal, one generation). Every
serving caller (search materializer, query/evidence, ATM emit-for-serving) moves
to the former; the compiler's staged build uses the latter.

### Copy-on-stage compile flow (changed source)

```python
def recompile_source(db, source_id, *, _inject_failure=None):
    # 1. Unchanged-content short-circuit (idempotency, §26.3) — UNCHANGED from P6.
    prior = get_authoritative_generation(db, source_id)
    if prior and fingerprint(db, source_id) == prior.audit.content_hash:
        return summary(prior)

    # 2. Stage: brand-new generation owns brand-new rows.
    gen_S = create_compiler_generation(db, source_id, status='staged')
    try:
        stage_units(db, source_id, gen_S)        # insert KU rows w/ generation_id=gen_S, NEW ids
        for u in list_generation_units(db, gen_S):
            validate_claim_support(db, u.id)
        stage_projections(db, gen_S)             # ATM pages → staging dir; search docs tagged gen_S
        if _inject_failure: raise RuntimeError(_inject_failure)
        report = run_compiler_audit(db, scope=gen_S)
        if report.publish_blocking: raise RuntimeError(report.publish_blocking)

        # 3. Atomic publish (single txn): swap gen_S in, retire gen_A.
        with db.transaction():
            reconcile_publish(db, source_id, staged=gen_S, prior=prior)  # stable-id reuse
            publish_compiler_generation(db, gen_S)   # gen_S→authoritative, gen_A→discarded
            swap_search_materialization(db, source_id, gen_S)  # activate gen_S docs, drop gen_A docs
            promote_atm_pages(db, gen_S)             # move staging-dir pages → live collections dir
    except Exception:
        discard_generation_artifacts(db, gen_S)      # delete staged rows/docs/staging-dir pages
        raise
    return summary(get_authoritative_generation(db, source_id))
```

### Stable-id reuse at publish (`reconcile_publish`)

Idempotency on UNCHANGED content is the short-circuit (no staging). On CHANGED
content, per-claim stability is handled here:

- **unchanged claim** (staged `semantic_hash` + whitespace-normalized statement
  matches a `prior` claim): delete the staged duplicate row; carry the prior row
  forward by `UPDATE knowledge_units SET generation_id = gen_S WHERE id = prior_id`.
  The stable id and its `claim_supports` survive.
- **changed / new claim**: keep the staged row (new id).
- **removed claim** (prior unmatched): leave it owned by gen_A → it becomes
  invisible the moment gen_A flips to `discarded` (no per-row retire needed for
  visibility, but set `retired_at` for audit clarity).

This reuses the existing `reconcile_source` matching predicate (semantic-hash
candidate + exact normalized statement), relocated to publish time.

### Staging search + projections

- **search_documents / search_chunks**: add `generation_id` to `search_documents`
  (NULL = legacy/authoritative-by-migration). Materialization for a staged gen
  writes docs tagged `generation_id=gen_S`. Search QUERY joins
  `search_documents → compiler_generations` and filters `status='authoritative'
  OR generation_id IS NULL`. `swap_search_materialization` deletes the prior
  source's authoritative-gen docs and clears the tag on gen_S docs (or flips by
  generation status — they're already gen_S, which is now authoritative).
- **ATM markdown pages**: staged pages are written under
  `.curator/staging/atoms/<gen_S>/` and moved into `02_Atoms/` only at
  `promote_atm_pages`; discard deletes the staging subdir. (Projections are
  disposable, so a simpler alternative is to defer ALL ATM writes to publish and
  emit from `list_generation_units(gen_S)` then.)

### Migration (legacy `generation_id IS NULL`)

One-time v8.x forward migration: for each source with verified units having
`generation_id IS NULL`, create one synthetic `authoritative` generation and
attribute those units to it. After migration, NULL `generation_id` means "not
compiled by Plan B" and is never served as a Plan-B claim. (No permanent NULL
escape hatch — repo invariant.)

## 2. Pros & Cons

**Pros**
- Spec-literal §26.3: staged rows are physically present but gated by generation
  status; serving cannot see them. Publish/discard are single transactions.
- Reuses the existing generation table + reconcile predicate; no mirror tables
  for knowledge_units.
- Idempotency short-circuit is untouched; F7 reconcile predicate is reused.

**Cons / limits in the current codebase**
- Touches the hot compile path (`compile_source_l2`), search materialization,
  and every serving read of `list_eligible_knowledge_units` — wide blast radius.
- `search_documents` needs a schema column (`generation_id`) + a synced/migrated
  change; search QUERY must join generations (perf: one indexed join).
- ATM staging-dir + promote/discard adds filesystem lifecycle to compile.
- `reconcile_publish` at publish time is more complex than today's in-place
  reconcile; the transaction spans rows + search docs + filesystem (filesystem
  moves are not transactional — need a careful order: DB commit first, then FS
  promote, with a re-emit-from-DB fallback on FS failure).
