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

## (c3) done — 02_Wiki promotions carry source graph/backlinks
- `query.resolve_source_links(paths, span_ids)` + `_sources_footer`; `save_wiki_page`
  gains `source_links=` → deterministic `## Sources` footer (deduped).
- Threaded optional `source_span_ids` through `plugin_api.promote_answer`, the MCP
  `promote_answer` tool, and both CLI promotion sites (track `last_source_span_ids`).
- Visible `02_Wiki/` note → source `[[04_Resources/…]]` links → native Graph/backlinks.
- Tests: test_query_source_links.py (footer dedup, promote end-to-end, resolve).
  44 passed across query/mcp/synthesis suites. ruff+mypy clean.
- Docs: SYSTEM_BEHAVIOR + MCP_USER_GUIDE (+KR).
- Obsidian block-ref syntax confirmed via docs: `[[file#^blockid]]` (caret after #);
  curator-link parser already preserves `#heading`/`#^block` subpaths (tested).

## Plugin-TS pass-through — DONE
- CLI `plugin promote --source-span-ids '[...]'` (JSON) → plugin_api.promote_answer.
- `incuratorClient.promoteAnswer(q, a, ws?, sourceSpanIds?)` sends `--source-span-ids`
  JSON when provided. NOTE: promoteAnswer has no production UI caller yet (plumbing
  is ready; a future "save to wiki" action would pass `lastQueryTrace.source_span_ids`).
- Tests: backend CLI passthrough (test_query_source_links) + 2 plugin client tests.
  Plugin 480 passed, tsc/build OK; backend CLI 9 passed; ruff/mypy clean.

## Immediate Next Action
Milestone-6 complete: (a) chat source citation, abstraction-tracing verification,
(c3) 02_Wiki graph/backlinks, plugin-TS pass-through. (b) opened-page body link
SKIPPED (deprioritized). Next: version bump v0.18.0 across 3 manifests + spec
titles (test_spec_sync) + CHANGELOG, then PR.
