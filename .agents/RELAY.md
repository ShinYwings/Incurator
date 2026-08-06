# RELAY — v0.43.0 shipped; `wiki build` running; next code item is B4

## Goal

Land the System Integrity Consolidation milestone (B2–B7). v0.43.0 unblocked
L3/L4 by lowering the relation-corroboration threshold; the user is running a
full `wiki build` on the real vault right now, and two queued workstreams —
B3's `l4_status` semantics and the whole retrieval-layering item — cannot be
judged until that build repopulates `community_reports` / `synthesis_nodes`.

## Plan Reference

- Master plan: `.agents/plans/03_system_integrity_consolidation.md` (B1–B7).
- Arena record: `.agents/plans/system_defect_audit_arena/` — 4 inspector
  proposals, 5 critiques, synthesis, and the three Gate-G0 passes.
  **These files lived only on `chore/system-defect-audit-arena` and were never
  merged; they are rescued onto this branch.** Do not delete that branch until
  this branch's PR merges.
- Live queue: `.agents/ROADMAP.md`. Raw evidence not yet planned:
  `.agents/USER_REPORT.md` (3 open items).

## Analysis And Reasoning

**The v0.43.0 finding is the template for the rest of this milestone.** No
Arena inspector could find it, because every inspector audited code-vs-spec
conformance and the code conformed. Measuring the *real vault* is what surfaced
it: SYSTEM_BEHAVIOR §27.2 required ≥2 distinct verified source lineages to admit
a relation, and 717 of 722 relations had exactly 1 — so 99.3% of the graph was
quarantined, communities could not form, and L3/L4 skipped for 34 of 37 sources.
The threshold contradicted the project's own philosophy (a Permanent Note is a
SINGLE idea; the value is linking such notes across sources). Verified on a DB
copy: active relations go 5 → 651 with no re-extraction. `copied_source_only`
was retired outright rather than re-scoped, because the lineage hash is
source-file-grained, so "N rows, 1 lineage" is ordinary restatement — and
retiring the outcome keeps the partition disjoint, which is what `ba4b2a3`
raised the threshold to protect in the first place.

The two remaining P1/DESIGN items in `USER_REPORT.md` have the **same shape**:
code conforms to spec, and the spec diverges from stated design intent.

1. `local` (`retrieval/evidence.py:440-447`) resolves entities → their L1 spans
   → flat search hits, never consulting `synthesis_nodes` or `community_reports`.
   SYSTEM_BEHAVIOR §17 describes exactly that, so the spec is what must be
   revisited against the user's stated intent ("query should descend
   L4→L3→L2→L1→source; splitting L1–L4 was partly to avoid the cost of scanning
   L1 every time").
2. Formula availability is a **retrieval-ranking** problem, not the L2 support
   gate. All 105 `span_type='equation'` spans and all 11,052 L1 spans are
   already in `search_documents` regardless of `support_status`; a real
   formula-dense query returned 27 items with exactly 1 containing LaTeX, the
   rest bibliography lines and bare headings. Loosening the support gate — the
   fix I first proposed — would not have delivered the stated outcome.

## Progress Status

- **Shipped**: v0.41.1 → v0.43.0 across 6 merged PRs (deferred-view crash,
  PDF.js canvas collision, manifest-only version identity, `setup.sh` alias
  provisioning, Zotero profile edit loss, null-byte CLI arg, Quick Query
  document identity, B1 plugin lifetime/teardown, corroboration gate).
- **Gate G0 is CLOSED** — all three missing Arena passes ran.
- **Decisions locked**: B3 Q1 = `l4_status='error'` (this makes B3 a Minor);
  B3 Q2 = delete the dead L2 checkpoint-resume; B2 Q5 = no migration needed
  (zero backslash relpaths); B2 Q6b = Windows is not supported, now or later.
- **`.agents/` and branches cleaned this session**: `USER_REPORT.md` triaged
  from 8 entries to the 3 that are still open, `ROADMAP.md` rewritten to
  current reality, merged branches deleted.

## Critical Context / Blockers

- **`wiki build` is running on the real vault.** Do not mutate vault state, do
  not run mutating `wiki` commands, and do not cancel the job. Source 36 (the
  MVG book) alone holds 8,692 of the vault's 11,052 source_spans, and a CLI
  provider round-trip costs 8.2–12.2 s — the wait is scale, not a hang.
- Measured provider facts, do not re-derive: CLI provider round-trip 8.2–12.2 s
  and flat across model and effort; CLI binary start 0.29 s; Incurator backend
  round-trip 0.20 s; warm local Ollama 0.26–0.32 s. The dominant latency is the
  provider service handshake, which Incurator cannot shorten. Do not propose
  micro-optimizing Incurator paths that are already sub-second.
- The D2 frozen holdout is CONSUMED (`run_count: 3`). Never rerun it; re-arming
  requires a written non-impact proof.
- Runtime venv is `<repo>/.venv` (`./setup.sh`); dev/validation venv is
  `<repo>/.venv-dev` via `scripts/backend-check`. Never create
  `backend/.venv` or backend-local caches.
- `curate.yml` exists ONLY in `01_Workspaces/<project>/`. Vault-scoped config
  is `.curator/settings.yml`. (Repeated correction — do not conflate them.)

## Update (2026-08-06) — v0.44.0 shipped; build finished; artifacts audited

PRs #117 (Arena rescue + agent-workspace cleanup) and #118 (B4, v0.44.0) are
merged. The `wiki build` completed and **v0.43.0 is confirmed on real data**:
`graph_relations.lifecycle_status` is now 782 `active` / 96 `quarantined`
(all `bridge_risk`, zero `copied_source_only`) against 5 active before, and
26 of 36 sources reach `l4_status='done'` where 34 of 37 previously skipped.
233 community reports and 4 synthesis nodes exist where there were 6 and 3.

The L4 prose is genuinely good — four accurate cross-source themes with stated
limitations — so the knowledge system works. The audit of
`.curator/Collections/` nevertheless produced five findings, all recorded in
`USER_REPORT.md` (2026-08-06) and queued as ROADMAP item 3.

Two things NOT to re-derive:

1. **`community_reports.detect_communities` is dead code.** It reads all
   relations with no `lifecycle_status` filter, which looks like a §27.4
   "active-canonical input only" violation. It is not — production uses
   `db.rebuild_graph_generation` → `connected_components(only_active=True)`.
   Verified from the artifacts: reports cite 782 active relation ids and zero
   quarantined, and the 233-component / 176-largest profile matches active-only
   exactly (all-relations gives 157 / 263). Its docstring is stale.
2. **The formula picture did not change.** `preserved_in_text|failed` is 498
   (was 490) and `preserved_in_text|verified` is still 86. The corroboration
   fix governed relations, not claim support — consistent with the earlier
   correction that formula availability is a retrieval-ranking problem.
   ROADMAP item 2 still stands, now judgeable against a populated L3/L4.

## Immediate Next Action

**B4 is the next unblocked code item and needs no build result and no open
decisions**: remove `wiki query --update` together with its
`add_atom_from_insight` path — it is an Exhibition-era leftover, so the fix is
removal, not better error reporting (this supersedes Arena finding eh-1) — and
fix eh-3, where a secret-decryption failure is reported to the user as a
missing API key.

When the build finishes, run `/tmp/measure_after_build.sh` to judge v0.43.0
(expect `graph_relations.lifecycle='active'` to jump and L3/L4 to populate),
then re-measure the `local`-route and formula-ranking items before planning
ROADMAP item 2.
