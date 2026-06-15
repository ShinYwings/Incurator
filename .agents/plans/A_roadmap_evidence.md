# Plan A Evidence Ledger (Coding-Time)

Date: 2026-06-15
Branch: `feature/plan-a-rag-retrieval-provenance`
Rollback anchor: `ec93a22e680d1df36c63f6bb08aadf7f4b42b4ef`
(= chore(project): initialize milestone A, one commit atop merged master at
`a32d31b21ccfb894242508522dec28e632f48043` which is Plan C v0.9.0 merge)

This is the coding-time ledger required by Plan A
(`.agents/plans/A_rag_retrieval_provenance.md` — "Required Program-3 Baseline
Snapshot"). It records entry-gate pass evidence, baseline state, and rollback
requirements before any implementation code is written.

## Hard Entry Gate Audit (P0 Pass Criteria)

All four hard entry gates verified:

| Gate | Evidence | Status |
|------|----------|--------|
| Program 1 (D1/Plan E/D2) merged | v0.6.0 (D1), PR #26 (Plan E), v0.7.0 (D2) | **PASS** |
| Program 1 observability substrate (QTR) | `db.insert_query_trace` + `query_traces` table; `QTR-*` id used in orchestrator | **PASS** |
| Program 2 (Plan B / Plan C) merged | v0.8.0 (Plan B), v0.9.0 (Plan C) | **PASS** |
| Program 2 compiler audit passes | `wiki lint` Compiler Integrity surface live; full test suite 877/8 | **PASS** |

Full test suite at rollback anchor:

```
uv run --directory backend pytest -q
  → 877 passed, 8 xfailed   (2026-06-15)
```

The 8 strict-xfail oracles:
- F3/F4/F5 → Plan A P3 (policy enforcement, bounded routes, explicit omissions)
- F6/F8/F9 → Plan C follow-up (synthesis fallback, homonym merge, authored links)
- F11/F12 → Plan F (explore followups, pack parity)

No Plan A oracle has been added yet; F3/F4/F5 pre-exist in
`tests/test_failure_atlas_repro.py` and are the targets Plan A turns green.

## Current Repository And Serving Reality

- Backend/plugin version at baseline: `0.9.0`
  (`backend/pyproject.toml`, `plugin/package.json`, `plugin/manifest.json` agree)
- `state.sqlite` schema version: `9`
  (Plan C additive v9 migration for entity resolution / graph quality tables)
- `build_evidence()` — no `policy` parameter; orchestrator resolves
  `CurationPolicy` but does not forward it (F3 gap; confirmed in
  `retrieval/evidence.py` lines 179-181 and `retrieval/orchestrator.py` lines
  80-84).
- Global route (`route == "global"`) — loads ALL community reports via
  `_report_items()` + all synthesis nodes, query-independently and unbounded
  (F4 gap; confirmed in `retrieval/evidence.py` lines 208-222).
- `EvidencePack.evidence_block()` — silent 16,000-char hard cutoff with no
  omission marker (F5 gap; confirmed in `retrieval/models.py` lines 68-77).
- `source_span_ids` in search hits — PRESENT in current code (line 73:
  `source_span_ids=hit.source_span_ids`); the planning-time observation about
  this gap is superseded by Plan B changes. Not a Plan A target.
- No `RTR-*` retrieval execution ID anywhere in the retrieval path; QTR traces
  exist in `query_traces` with `retrieval_trace_json` field.
- `EvidenceItem` has no `locator` field; no `StructuredLocator` dataclass exists.
- `QueryOrchestrator.fetch_context` and `.run` both call `build_evidence(paths,
  request, route)` — policy not forwarded.

## Baseline Fingerprints

```
db.py SHA-256:
  071138e92ef2571b53f0c4f8a6254aacea641aa6c87b0eccd15ae38593d927ec

retrieval/evidence.py SHA-256:
  82a5d04bdc98b8f299edb2325cf8dae62678363290717bf7a409ddccfcc28b52

retrieval/models.py SHA-256:
  fa58a2da763f7a43a8baef22c59fbbb94eaee912478eaea149c7dfae34d1a498

retrieval/orchestrator.py SHA-256:
  566c3d678b6f92bec372b68bc3d0792c0ada0f3f9895a37ab339e7de5dee9ef9
```

## Testbed Baseline Snapshot

- Active scenario: `gaussian_splatting` (3 PDF papers via Reference Mode,
  `01_Workspaces/Gaussian Splatting Geometry Lab/`)
- Providers/models:
  - Primary LLM: Antigravity CLI (`gemini-3.5-flash`)
  - Embedding: `llama-cpp::qwen3-embedding-0.6b`
  - Search engine: `native-0.8.0` in-DB FTS5 + vector
- DB state: schema_version=9, 3 sources, 212 source_spans, 34 knowledge_units,
  1 synthesis_node, 17 graph_entities, 18 graph_relations, 1 community_report,
  34 claim_supports, 4 compiler_generations
- DB SHA-256 (before any Plan A changes):
  `5e6d18b057ef28fb90427f717aca355dcfb0811a372af1323da30a16e69092eb`
- DB backup: `.agents/backups/a-pre-implementation-state.sqlite`
  (gitignored), SHA-256 identical; `PRAGMA integrity_check` = ok
- DB schema fingerprint (SHA-256 over ordered `sqlite_master` DDL):
  `21e2330d009ad94993f70de6ba816094dd3c0bf02c6e794c2ec6f70223c6b969`
- `wiki lint` at baseline: 67/100 health, 11 release-blocking Compiler
  Integrity F6 errors (source 3 wrong-real-span claims; known pre-Plan-A corpus
  quality, NOT a system defect — the compiler is working correctly).
  These do NOT block Plan A.
- `wiki status`: L1 done (3/3), L2 done (3/3), L3 done (3/3), L4 pending (0/3)
- Failure Atlas fixture corpus SHA-256: `35301871bdd1e8e676d63c032e7c566d863a9760f94d1c00e5de8217e364603b`
- Failure Atlas qrels SHA-256: `e3b254054779595aa4157df82db1c885356e3763f35430be0b23bb187c35c6a0`

## Program 2 Compiler Audit Gate (serving baseline)

- `wiki lint` Compiler Integrity is live and correct: 11 release-blocking
  errors in the testbed are corpus-quality failures (source 3 F6 claims), not
  system defects. The audit module correctly identifies and reports them.
- No staged leftovers, no broad_fallback_plan_c, no dangling supports,
  no formula inconsistencies in the current compiler audit output.
- `list_serving_units` (authoritative ∧ verified ∧ not-retired) returns 2 units
  (source 2 only); source 1 = 0 units (graph LLM parse failure), source 3 = 0
  served (11 failed + 8 unchecked in authoritative generation, excluded from
  serving per §26.3).

## Rollback Requirements

- Rollback anchor commit: `ec93a22`
- DB backup for restore: `.agents/backups/a-pre-implementation-state.sqlite`
- Plan A does NOT require a schema migration for P3 (policy, bounded routes,
  omissions) — these are behavior changes only.
- Plan A MAY require minor schema additions for P2 (RTR-* ID in
  `retrieval_trace_json`) — stored in existing JSONB column, no new table needed.
- Plan A adds `StructuredLocator` dataclass and `locator` field to `EvidenceItem`
  in P4 — no DB migration, in-memory/transport only.
- Three QA failures for same blocker → activate `rollback_strategist`,
  restore `ec93a22` commit state, return to planning.

## Scope Note: F6/F8/F9

F6 (`synthesis.py:110` broad fallback), F8 (homonym merge), F9 (authored links)
remain assigned to Plan C follow-up work. Plan A does NOT own these oracles and
MUST NOT attempt to turn them green.

## P1 Spec Contract Deliverables (pre-code)

Before implementation code is written, the following spec sections must be added:
- `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`: §28 Policy Enforcement,
  §29 Structured Locators, §30 Retrieval Execution (RTR-*)
- `docs/specs/curator_schema/SCHEMA.md`: §22 Retrieval Contracts (Plan A)
- `docs/specs/search_engine/SEARCH_ENGINE_SCHEMA.md`: §11 Plan-A retrieval
  result boundary

And the following test file created:
- `backend/tests/test_plan_a_retrieval.py` — structural + oracle tests

## P2 — RTR-* Retrieval Execution (Implementation Notes)

P2 adds a retrieval execution ID (`RTR-*`) to the evidence pack and QTR trace.
No new DB table is needed — RTR-* is stored in the existing
`query_traces.retrieval_trace_json` column. The RTR-* ID is generated inside
`build_evidence` (or a new `RetrievalCoordinator`) and returned on the
`EvidencePack` alongside the route and evidence.

## Plan A P1 Mandatory Stop Status

User approval was given via "go ahead" on 2026-06-15 in response to the RELAY.md
state (Batch 3 Plan A execution). This satisfies the Universal Strict Workflow
§4 approval requirement for Plan A. Implementation may proceed through all phases.
