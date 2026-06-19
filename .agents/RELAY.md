# Cross-Agent Relay State

## Goal
Batch 3 / Plan F — Unified Agent Context Service on
`feature/agent-context-service`.

## Plan Reference
- Active plan: `.agents/plans/F_agent_context_service.md`
- Current phase: **P8 — Plan-A Route Admission** (in flight). P6 + P7 are done
  except headless-impossible visual QA.
- Plan G (PDF unification) was branched off this branch and merged back via PR #33
  (`f53306c`); v0.12.0 shipped. That merge restored the Plan G RELAY snapshot, so
  this file has been rewritten to the accurate Plan F live state.

## Analysis & Reasoning (Phase boundary)
- **P0–P5 complete.** ContextService owns root `QTR-*`, deterministic `SNAP-*`,
  ordered `CTXA-*` child actions, `PACK-*`, typed `snapshot_conflict`. Budget-bounded
  pack selection, explicit omissions, `next[]` expansion handles, locator resolution,
  and trace/response selected-pack parity all landed. Public adapters
  (`curator_fetch_context`, `curator_query`/`wiki query`, plugin JSON) delegate to the
  service and expose normalized pack/snapshot/budget/prompt-trace parity against the
  stored root `QTR-*`. `context_manifest`/`context_expand`/`context_verify` exist and
  reuse the root QTR + stored SNAP.
- **P6 in flight.** Provider grounding (hidden `wiki plugin context fetch` →
  `IncuratorClient.fetchContext()` → sidechat `formatCuratorContextPack`, no default
  backend-synthesized answer), exact-pack Sources & Trace rendering, clickable locators,
  and `context:expand`/`context:verify` controls are done. Snapshot-conflict refetch UX
  is implemented at source-contract level.

## Progress Status
- Baseline after Plan G merge re-verified green (see Validation).
- This session (Claude, 2026-06-19): hardened the P6 Sources & Trace locator slice.
  Extracted the pure open-target decision out of the Obsidian-coupled trace module into
  `plugin/src/ui/incuratorQueryTraceLocator.ts` (mirrors Plan G's `PdfCaptureService` /
  `externalPdfRegistry` testability extractions) and replaced weak source-grep coverage
  with real behavioral tests in `incuratorQueryTraceLocator.test.ts`: registered/vault
  PDF (`#page=N`), unregistered external Reference Mode PDF (plugin viewer at page),
  PDF-by-extension, non-PDF external (system handler, stub-loses-to-external_uri),
  URL-scheme `.pdf` (system handler), and vault note block/heading anchors.
  `incuratorQueryTraceV031.test.ts` now asserts the trace module *delegates* + wires the
  Obsidian/Electron side-effects, instead of grepping the moved pure logic.

## Progress Status (P7 — Feedback, slice 1)
- Implemented the append-only `context_feedback` ContextService operation:
  `FBK-*` event recorded as a `feedback` child action on the root `QTR-*`, linked
  to pack/snapshot, with locked feedback-type validation, target/reviewed-evidence
  capture, and a hard quarantine (`ranking_or_truth_mutated: false`; lineage fields
  present but unresolved). No schema migration — reuses the `query_traces`
  `retrieval_trace.context_service.actions` append store.
- Added public adapters for parity: `plugin_api.feedback_context` and the hidden
  `wiki plugin context feedback` CLI command.
- Docs: PLUGIN_SCHEMA command list + §15 feedback usage; EN then KR PLUGIN_GUIDE.
  SYSTEM_BEHAVIOR §31.6 and SCHEMA §23.2 FBK-* already specced this at P1.
- Slice 2 done: `new_insight` feedback now records a provisional `pending` insight
  candidate (reuses `insight_lifecycle`, deterministic, no LLM) and reports it in
  `resulting_lineage.insight_candidate_id`. Quarantine preserved: candidate is never
  applied to source/generated/ranking/truth until a human promotes it. `correction`
  patching and `02_Wiki/` promotion stay behind the existing explicit tools
  (`curator_propose_correction`, `curator_promote_insight`/`promote_answer`).
  SYSTEM_BEHAVIOR §31.6 documents this.
- Slice 3 (plugin-side) done: per-item feedback affordance in Sources & Trace —
  👍 relevant / 👎 irrelevant + a Report… menu (incorrect/stale/insufficient/
  duplicate) — dispatches one `context:feedback` event; `chatSidebar`
  `handleContextTraceFeedback` calls `IncuratorClient.feedbackContext()` ->
  `wiki plugin context feedback`. Acknowledgement-only; never mutates the displayed
  pack/ranking/truth. PLUGIN_SCHEMA §15.1 + EN/KR PLUGIN_GUIDE updated.
- **P7 is functionally complete** (backend + CLI + plugin + docs). Remaining: review/
  promotion-lifecycle UI for `new_insight` candidates is out of scope here (handled by
  existing insight-candidate review surfaces).

## Validation
- `scripts/backend-check pytest backend/tests/test_plan_f_context_service_contract.py`
  -> `29 passed` (24 prior + 5 new feedback tests).
- `scripts/backend-check pytest backend/tests/test_plugin_cli.py test_spec_sync.py`
  -> `20 passed` (feedback CLI happy-path + invalid-type rejection).
- `scripts/backend-check ruff/mypy` on context_service/plugin_api/cli -> clean.
- Refreshed `.venv-dev` editable install (stale 0.11.0 metadata -> 0.12.0) so
  `test_spec_sync` passes; env-only, no code change.
- `npx tsc --noEmit` + `npx vitest run` from `plugin/` -> `50` files / `426` passed
  (from the prior P6 locator slice; plugin untouched this slice).

## Critical Context / Blockers
- Items `01`-`03` and `06` from the Batch 1~3 audit (`.agents/drafts/batch_1_to_3_audit/`)
  are real follow-up risks tracked in `.agents/ROADMAP.md`.
- P6 browser/Obsidian *visual* QA (pack/refetch/action control styling) cannot be done
  headlessly; still pending a human/visual pass.
- Active testbed scenario is unconfirmed; Plan F defers destructive
  `wiki testbed init --force` until P9 or explicit selection.
- Explore-mode ContextService migration is deferred to the explicit follow-up
  requirement unless the user directs otherwise.

## P8 — Route Admission (done)
- Added a ContextService admission gate (`_admit_route`, SYSTEM_BEHAVIOR §31.8):
  only Plan-A pack-integrated routes are served — `local`, `source-section`,
  `global`. `explore` (deferred) and any unknown route degrade to `local` BEFORE
  retrieval runs, so no second/divergent retrieval path is created.
- Rollback seam: an admitted experimental route (`global`) is independently
  disableable via `INCURATOR_DISABLED_ROUTES` env (comma-sep) or a programmatic
  `disabled_routes=` constructor arg; degrades to `local`. Safe baselines never
  disabled. Decision recorded as `route_admission` on the response + root trace.
- Tests: `_admit_route` unit cases, env parsing, forced-explore degrade (asserts
  one RTR / one QTR — no second retrieval/root), global rollback degrade, admitted
  pass-through. Contract suite green (running full sweep to confirm).

## Immediate Next Action
1. P9 — cross-client E2E, testbed, migration rehearsal, then release (version bump
   + changelog + PR at the P9 release gate per Universal Strict Workflow).
2. P6/P7/P8 visual QA in Obsidian (feedback buttons, pack/refetch controls) —
   needs a human pass; cannot run headless.
