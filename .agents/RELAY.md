# Cross-Agent Relay State

## Goal
Batch 3 / Plan F — Unified Agent Context Service on
`feature/agent-context-service`.

## Plan Reference
- Active plan: `.agents/plans/F_agent_context_service.md`
- Current phase: **P6 — Obsidian Agent Grounding And Sources & Trace** (in flight).
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

## Validation
- `scripts/backend-check pytest backend/tests/test_plan_f_context_service_contract.py`
  -> `24 passed`.
- `npx tsc --noEmit` from `plugin/` -> passed.
- `npx vitest run` from `plugin/` -> `50` files / `426` tests passed (was 49/417).

## Critical Context / Blockers
- Items `01`-`03` and `06` from the Batch 1~3 audit (`.agents/drafts/batch_1_to_3_audit/`)
  are real follow-up risks tracked in `.agents/ROADMAP.md`.
- P6 browser/Obsidian *visual* QA (pack/refetch/action control styling) cannot be done
  headlessly; still pending a human/visual pass.
- Active testbed scenario is unconfirmed; Plan F defers destructive
  `wiki testbed init --force` until P9 or explicit selection.
- Explore-mode ContextService migration is deferred to the explicit follow-up
  requirement unless the user directs otherwise.

## Immediate Next Action
Continue P6, then advance to remaining phases:
1. P6: visual QA of pack/refetch/action controls (needs a human/Obsidian pass).
2. **P7 — Feedback And Promotion Lineage**: append-only `context_feedback`, all locked
   feedback types, lineage attachment, quarantine from ranking/truth. Begin TDD.
3. P8 — Plan-A route admission; P9 — cross-client E2E, testbed, migration, release
   (version bump + changelog at the P9 release gate per Universal Strict Workflow).
