# Cross-Agent Relay State

## Status
v0.17.0 (curator wikilink resolution) shipped via PR #40 (open). NEW follow-up:
external-source link resolution. Plan drafted, awaiting user approval + a (c)
graph/backlinks decision (Universal Strict Workflow Step 4 STOP).

## Goal
Make source documents OUTSIDE `.curator/` (04_Resources, 05_Assets, 03_Notes)
reachable from the knowledge that cites them, across (a) chat/popover answers,
(b) opened DAG pages, (c) graph/backlinks. KEEP the v0.17.0 curator-link feature.

## Key constraint (must resolve before (c))
Graph/Backlinks only index links from VISIBLE files; the curator pages linking to
sources are hidden, so source↔knowledge graph edges need a visible bridge file
(= Option B territory). Plan recommends (c3) hybrid: native graph/backlinks only
for human-promoted visible `02_Wiki/` knowledge; trace panel for the hidden DAG.

## Plan Reference
`.agents/plans/06_external_source_links.md` (PLAN_TEMPLATE-compliant, v0.18.0).
(a) backend query.py source surfacing + cite contract; (b) verify native
resolution / optional body `## Source` link; (c) fork c1/c2/c3.

## (c) decision: LOCKED (c3) Hybrid
Native graph/backlinks only for visible `02_Wiki/` promotions (they get
`[[source]]` links); hidden DAG uses trace panel.

## Branch
On `feature/external-source-links` (from master; PR #40 + #41 merged).

## P0 findings (verification, done)
- DB provenance → source path: CONFIRMED. `source_spans(id, source_id, relpath)`
  maps every SPAN- id to its real source relpath; `sources(id, relpath)` likewise.
  Testbed proof: spans → `04_Resources/smoke_routed_paper.md` etc. (real visible
  `.md` files). L1 contexts also carry frontmatter `source_path: [[04_Resources/…]]`.
- Layer coverage: L1/L2 resolve directly (context source_id / atom source_span_ids);
  L3/L4 need DAG traversal (`concepts.dependencies` → atoms; `synthesis.core_concepts`
  → concepts → atoms → spans → source). Schema supports it; testbed is L1-only so
  L2–L4 traversal is unverified on live data (documented gap).
- Source targets are REAL visible vault files → resolve natively in Obsidian.
- PENDING (needs Obsidian GUI, can't run headless): confirm body `[[04_Resources/…]]`
  / `![[05_Assets/…]]` resolve from an opened HIDDEN page, and whether the
  frontmatter `source_path` pill is clickable. Proceeding on documented Obsidian
  behavior (linkpath resolves against the global index regardless of source loc).

## Progress (P2 (a) done — abstraction tracing verified + chat source citation)
- KEY FINDING: RAG stabilization BUILT abstraction→source provenance
  (materializer `_first_source_id` + per-record `source_span_ids`) but never
  ASSERTED it, and `_first_source_id` keeps only ONE source (multi-source loss).
- Added `db.sources_for_spans(span_ids)` — forward trace span→source_id→
  sources.relpath, returns ALL distinct origins in span order. Verified by
  `test_abstraction_source_trace.py` (single, dedup/order, multi-source synthesis,
  unknown/empty).
- `query.py` now resolves each hit's source docs and surfaces `Source document(s):
  [[04_Resources/…]]` in the synthesis prompt + cite contract (only `.md` stripped,
  other exts kept). Tests: `test_query_source_links.py`. No regressions (28 passed
  in synthesis/query suites).
- Docs: SYSTEM_BEHAVIOR (source-citation contract) + PLUGIN_GUIDE/KR.

## Immediate Next Action
Commit this chunk. Remaining milestone-6 phases: (b) opened-DAG-page body
`## Source` link if needed (user said don't fret GUI link-checking, just keep
format right — chat format done); (c3) promotion-to-`02_Wiki` source links for
native graph/backlinks; then version bump v0.18.0 + PR. Decide with user whether
(a)+verification is the priority deliverable or continue (b)/(c3).
