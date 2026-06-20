# Architecture Proposal: RAG Systemic Hardening
Date: 2026-06-20 | Agent Persona: lead_architect (The Proposer)

Sequencing rationale: ship in increasing order of blast radius — **06 → 03 → 02 → 01**.
06 is a pure refactor inside an existing contract; 03 reuses existing snapshot +
lint machinery; 02 adds a new edge class + traversal rule; 01 is a methodology /
eval-harness change. Each phase is independently shippable and revertable.

## 1. Core Logic & Implementation

### P-06 — Explore through ContextService
Today `run()` forks at `route != "explore"`. The fix collapses the fork:

1. Admit `explore` to `_ADMITTED_ROUTES` (`context_service.py:29`) **but** mark it
   as a *fetch-grounding* route, not a synthesis route. `context_fetch` already
   builds the pack via the admitted path; explore just needs its pack.
2. In `run()`, always call `ContextService.context_fetch(request)` first. For
   `explore`, pass the returned normalized pack into `_run_explore` instead of a
   legacy `EvidencePack`.
3. Refactor `_run_explore(request, pack, ...)` to consume the context-pack dict
   (`pack["items"]`, `pack["source_span_ids"]`) for its `primer_block` /
   `valid_span_ids_block`, exactly as `_run_answer_from_context` already does.
4. Delete the manual `QTR-*` minting + `_build_retrieval_trace` + standalone
   `db.insert_query_trace` block in the explore branch; the
   `_update_context_trace_after_synthesis` path now records the explore synthesis
   action (`action_type:"explore"`) on the same `QTR-*`/`CTXA-*` trace.

```python
def run(self, request):
    ...
    context_pack = ContextService(self.paths, self.client).context_fetch(request)
    result = QueryResultV031(... from context_pack ...)
    if context_pack["route"] == "explore":
        self._run_explore_from_context(request, context_pack, spec_hash, result)
    else:
        self._run_answer_from_context(request, context_pack, spec_hash, result)
    self._update_context_trace_after_synthesis(result, latency_ms=...)
    return result
```

Route admission still degrades a *disabled* explore to `local` via `_admit_route`;
the safety/rollback contract is unchanged — explore simply stops being a *second
retrieval pipeline*.

### P-03 — Soft-snapshot rebase + pipeline healing
**(a) Soft rebase** in `context_expand` (`context_service.py:743`). Today:
`if expected_snapshot_id != current_snapshot_id: return _conflict_response(...)`.
Replace the hard reject with an intersection test:

```python
if expected_snapshot_id != current_snapshot_id:
    changed = _changed_nodes_between(self.paths, expected_snapshot_id, current_snapshot_id)
    cited = _pack_cited_node_ids(context)           # spans/atoms/concepts in the pack
    if changed & cited:
        return _conflict_response(expected, current)  # real conflict — keep strict
    # non-intersecting: auto-rebase onto current snapshot, annotate the action
    snapshot = _snapshot(self.paths, policy_hash=..., request=...)
    rebased = True
```

`_changed_nodes_between` is derived from `_source_epoch` deltas (the epoch already
hashes per-source content). The rebase records a `rebased_from`/`rebased_to` field
on the `CTXA-*` action so the trace is auditable. When epoch deltas cannot be
computed cheaply, fall back to the strict conflict (fail safe, never fail open).

**(b) Pipeline healing** — a new `wiki integrity heal` subcommand + a callable
`integrity.heal(paths)` that wraps the existing `compiler_integrity` checks
(`lint.py:1332`). It scans for orphaned `source_span_ids` / unresolved locators,
and for each either (i) re-resolves it from the live DB, (ii) flags it
`lifecycle_status="quarantined"` with a reason, or (iii) emits a `LintIssue` for
human review. Runs async via the existing job queue (`ingest_jobs`/`job_events`)
so it never blocks the synchronous fetch path. No new tables.

### P-02 — Soft-link edges + giant-component quarantine
Reuse `graph_relations`. Add a relation *kind* `soft_alias` (candidate alias)
distinct from extracted semantic relations:

- **Generation**: a lexical+embedding candidate-alias pass over `graph_entities`
  proposes `soft_alias` edges with a confidence weight (e.g. "LLM"↔"Large Language
  Model"). It writes `graph_relations(kind="soft_alias", lifecycle_status="proposed",
  confidence=...)`. Never mutates `graph_entities` identity.
- **Traversal rule**: factual routes (`local`/`source-section`/`global`) skip
  `kind="soft_alias"`. Only `explore` may traverse them, and each hop pays a fixed
  budget penalty (so a giant alias cluster cannot drain the pack).
- **Giant-component quarantine**: during compilation, compute per-node degree /
  community share. If a node's community covers more than `N%` of the vault, set
  `quarantine_reason="giant_component_hub"` (column already exists, `db.py:358`) and
  exclude it from automated traversal. Emit a `compiler_integrity` finding.

```sql
-- no new table; new enum values only
-- graph_relations.kind: 'semantic' | 'soft_alias'
-- graph_relations.lifecycle_status: ... | 'proposed' | 'quarantined'
-- graph_entities / graph_relations.quarantine_reason: ... | 'giant_component_hub'
```

### P-01 — Real-world sampling + noise injection
**(a) Fixture promotion**: a `wiki atlas promote-failures` command reads recent
`FBK-*` events of type `irrelevant`/`incorrect`/`insufficient`, and emits
*candidate* Failure Atlas cases (`docs/specs/failure_atlas/cases/Fxx.yml` siblings,
in a `candidates/` subdir) carrying the real query + retrieved evidence ids. These
are human-reviewed before promotion to the frozen suite (never auto-frozen — keeps
the oracle honest without letting noise corrupt the gold set).

**(b) Noise injection**: extend the eval harness (`backend/tests/test_failure_atlas_*`
+ `failure_atlas_holdout.py`) with a `noise` transform applied to fixture inputs
(strip headers, corrupt a markdown table, inject OCR-style substitutions). Add a
resilience metric: retrieval recall must not drop below a floor under noise. The
`fixture_corpus.yml` gains a `noise_profiles` block.

## 2. Pros & Cons

**Pros**
- Every phase reuses existing machinery (admission, snapshot/epoch, `graph_relations`
  columns, `compiler_integrity`, FBK loop) — minimal new surface, low migration risk.
- Soft-links solve recall without violating the no-auto-merge invariant.
- Soft-rebase removes the worst UX cliff (mid-conversation paralysis) while staying
  fail-safe on genuine conflicts.
- Fixture promotion closes the oracle-overfitting loop with a human gate.

**Cons / limits**
- `_changed_nodes_between` needs a cheap epoch delta; if the epoch is a single
  vault-wide hash today, P-03(a) needs a per-node/per-source epoch granularity
  first (a real schema/contract question for P0 to measure).
- Soft-alias generation is an LLM/embedding pass → cost + a new prompt contract.
- Noise injection risks making the suite flaky if the floor is mis-tuned.
- Giant-component threshold `N%` is a magic number needing empirical calibration.
