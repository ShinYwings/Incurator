# Critique on lead_architect proposal
Date: 2026-06-20 | Agent Persona: red_teamer (The Adversary)

## 1. Vulnerabilities & Flaws

### P-06 — the explore migration hides a behavioral regression
- **Insight-candidate provenance drift.** Legacy `_run_explore` builds
  `valid_span_ids` from `pack.source_span_ids` (an `EvidencePack`). The context
  pack orders/filters spans differently (budget omission, dedup). If explore now
  grounds on the *budgeted* pack, some spans the old path saw are dropped →
  `create_insight_candidate` may reject candidates that used to pass validation.
  This is a silent recall regression masked as "unification." **Demand a parity
  test**: same question, assert explore insight-candidate ids are a superset (or
  documented subset) of the legacy path before deleting `build_evidence` usage.
- **Route admission contradiction.** `test_context_fetch_does_not_admit_explore_route`
  currently *pins* explore exclusion. Admitting explore flips a tested contract —
  that test must be rewritten, not deleted silently, and §31.8 updated in the same
  commit or the spec-sync test fails.
- **Double synthesis action.** If `run()` always calls
  `_update_context_trace_after_synthesis`, explore (which already inserts its own
  trace today) could double-write. Verify exactly one `QTR-*` row and ordered
  `CTXA-*` actions.

### P-03 — soft-rebase can fail OPEN (correctness hole)
- **The intersection test is only as good as `_changed_nodes_between`.** If the
  epoch is a coarse vault-wide hash (likely), you cannot compute which nodes
  changed, so `changed` is unknowable. The proposal's "fall back to strict" is the
  *only* safe branch — but the tempting optimization is to assume non-intersection
  and rebase, which would serve **stale evidence as fresh**. That is worse than the
  paralysis it fixes. **Hard rule: no rebase unless per-node change detection is
  proven; otherwise this phase ships as a no-op + a measured P0 spike.**
- **Heal worker mutating during a live fetch.** `integrity.heal` flipping
  `lifecycle_status` to `quarantined` mid-conversation changes the epoch → triggers
  the very `snapshot_conflict` we're trying to soften, and can quarantine a node the
  agent is actively citing. Healing must be **advisory by default** (flag, don't
  mutate) unless run in a maintenance window.

### P-02 — soft-links re-introduce the giant component by the back door
- **Explore traversing soft-aliases = the giant component, deferred.** A budget
  penalty per hop is not a cap; a dense alias cluster ("AI"↔"ML"↔"DL"↔…) still
  explodes combinatorially. **Require a hard hop-count / fanout cap on soft-alias
  traversal, not just a soft penalty.**
- **`soft_alias` confidence has no calibration source.** An LLM/embedding score is
  not a probability. Threshold drift will either flood the graph with junk aliases
  or generate none. Needs a labeled validation set (overlaps with P-01 atlas).
- **Quarantine is destructive to recall if `N%` is wrong.** Quarantining "AI" in an
  AI-research vault removes the single most-connected legitimate hub. The threshold
  must be vault-size-relative AND have an allowlist override, or it silently guts
  recall on-topic.
- **Migration ordering.** Adding `kind`/new `lifecycle_status` enum values to
  `graph_relations` while a v9 graph exists must be forward-only and idempotent
  (the `idx_graph_relations_lifecycle` note at `db.py:381` warns IF-NOT-EXISTS
  CREATE TABLE won't add columns to a pre-existing table — a real migration is
  required, not a CREATE-IF-NOT-EXISTS).

### P-01 — the promotion loop can poison the oracle
- **Self-fulfilling fixtures.** Promoting failing queries the *current* retriever
  marked `incorrect` bakes the current retriever's blind spots into the gold set as
  "expected." If a human rubber-stamps them, you optimize toward today's errors.
  The human gate must include the *correct* expected answer, sourced independently —
  not just the failed retrieval transcript.
- **Noise injection flakiness.** A recall floor under random OCR corruption is
  inherently noisy; seed determinism is mandatory (`Math.random`-style nondeterminism
  in fixtures will make CI flap). Pin the noise seed in `fixture_corpus.yml`.

## 2. Suggested Alternatives
1. **Gate P-03(a) behind a P0 measurement** of epoch granularity. If coarse, split
   into P-03(a-pre): per-source epoch column, before any rebase logic ships.
2. **Soft-alias traversal: hard fanout cap (e.g. ≤3 alias hops, ≤K nodes) + budget
   penalty**, both. Penalty alone is insufficient.
3. **Quarantine = advisory flag + traversal de-prioritization first**, hard exclusion
   only behind an explicit allowlist/denylist reviewed by a human.
4. **Healing defaults to dry-run** (`wiki integrity heal --report`); `--apply` is opt-in
   and refuses to run while any pack's snapshot is younger than a cooldown.
5. **Atlas promotion requires an independent expected-answer field**; reject candidates
   that only carry the failed transcript.
