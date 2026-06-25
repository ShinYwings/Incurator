# v0.25.1 Master Implementation Plan

Date: 2026-06-25
Status: APPROVED — implementation in progress after user "go".
Briefing: `.agents/plans/user_report_stability_hotfix_arena/00_problem.md`
Arena:
- `.agents/plans/user_report_stability_hotfix_arena/A_backend_cli_pipeline.md`
- `.agents/plans/user_report_stability_hotfix_arena/B_plugin_pdf_popover.md`
- `.agents/plans/user_report_stability_hotfix_arena/02_critique_plan_review.md`
- `.agents/plans/user_report_stability_hotfix_arena/03_defense_revision.md`

## 1. Objective

Fix the urgent user-reported stability bugs from `.agents/USER_REPORT.md` before
resuming the broader System Stability Overhaul diagnosis. Definition of done:
each report is either fixed with tests/docs or explicitly moved to a deferred
stability follow-up with the reason recorded.

## 2. Explicit Non-Goals

- Not a broad refactor of `cli.py`, `chatSidebar.ts`, or `externalPdfView.ts`.
- Not a new PDF annotation system.
- Not a rewrite of the RAG/DAG pipeline.
- Not an automatic full-DAG build on every Add Source click.
- Not a non-LLM text-copy replacement for Convert-to-LaTeX; the feature remains
  LLM-backed but must use the dedicated extraction route and a strict output-only
  contract.

## 3. Strict Quality Conditions & Release Gates

- Backend changes pass focused pytest plus `scripts/backend-check ruff`.
- Plugin changes pass focused vitest plus the full plugin vitest suite if focused
  tests are green.
- Docs updated in English first and synced to Korean for changed behavior.
- `wiki source rm` must never delete a source file unless an explicit destructive
  flag is supplied and confirmed.
- Generated L1/CTX content must not include `file://` or `.cache/vision_render`
  temp paths.
- VLM sanitizer must run post-generation and pre-persistence, and must preserve
  valid non-temp Markdown links/images.
- L2 generated fields must pass a programmatic English-language guard. Prompt
  wording alone is not an acceptable gate.

## 4. Locked Design Decisions

- Source-data safety is P0.
- Preserve the existing source-state contract unless the user asks otherwise:
  `Queued` and `Building...` remain distinct from inert `Added`; after successful
  registration, a chip must not revert to actionable `Add source`.
- Make `jobs rerun` idempotent for queued jobs and precise for running jobs.
- Make `source retry` use per-layer error state, not only aggregate
  `sources.status='error'`.
- Sanitize VLM outputs at the ingest boundary: after
  `normalize_vision_latex(...)` returns model text and before that text is assigned
  to `pdf_pages[*].text`, cached as durable extracted content, written to CTX, or
  turned into source spans. The sanitizer only removes Markdown image/link
  destinations that parse as `file:` URLs or normalize under
  `vision.vision_render_dir()` / `.cache/vision_render`; `http(s)://`,
  vault-relative links, and normal external paths remain untouched.
- Enforce English generated L2 output with a deterministic validation step over
  generated fields (`canonical_name`, `statement`, projected Atom title/body),
  allowing raw evidence/source spans to remain in the source language. Non-English
  generated output triggers a capped retry/repair path; repeated failure marks the
  source layer error instead of silently persisting Korean Atoms.
- Audit all internal `remove_source(` callers before changing defaults. Any
  legitimate file-deletion caller must pass an explicit destructive argument.
- Reuse sidechat LaTeX copy infrastructure in popover.
- Keep Convert-to-LaTeX LLM-backed. The fix is to route both image and text
  selections through the dedicated backend `plugin pdf transcribe` extractor
  (`latex_extract_model → vision_model → main-if-vision`) with an output-only
  prompt/normalizer, not through general chat behavior that can add explanations.
- Match sidechat's PDF priority model for `(19.11)` and similar references:
  local visible/window PDF context and local document index first; backend
  read-only PDF context/search only when local context is insufficient and a
  tracked/resolvable identity exists; never passive auto-ingest.
- L4 is an automatic build-stage target in the current architecture, not a manual
  Add Source step. `wiki add` creates L1 and queues/refines L2/L3; `wiki build
  --wait`, `wiki jobs run`, or an active worker should run global L3 and attempt
  shared L4 synthesis. Zero SYN nodes can be valid when there are no eligible
  community reports, but perpetual `l4_status='pending'` after a completed build
  is a status/reporting bug.
- Treat PDF scroll jank as a measured performance bug.
- Quick-query popovers are per-selection ephemeral sessions. Opening another
  quick query must preserve existing popovers instead of replacing them; each
  popover keeps independent answer/follow-up/minimize/drag state.

## 5. Scope Exclusions & Stop Conditions

- Whole-codebase Phase A diagnosis remains paused, not cancelled.
- Stop if fixing source retry requires a DB schema migration.
- Stop if PDF scroll jank cannot be reproduced or measured locally.
- Stop if whole-PDF equation lookup requires a new backend command contract beyond
  existing `plugin pdf context/search`; otherwise use the existing sidechat-style
  priority model.

## 6. Evidence Ledger

- Branch: `feature/system-stability-overhaul`.
- Pre-triage dirty files: `.agents/USER_REPORT.md` modified by user and
  `.agents/image.png`, `.agents/image-1.png`, `.agents/image-2.png` untracked.
- `wiki source rm` docs say registration/L1 removal, while code defaults to
  `delete_file=True`.
- `wiki source retry` code selects only `sources.status='error'`.
- `db.rerun_job` only updates terminal jobs; queued jobs return false.
- Quick-query render path does not call `stampMathSourceData`; sidechat does.
- Bare parenthesized equation references like `(19.11)` are not extracted.
- Sidechat PDF context policy already skips backend PDF context when local viewer
  text/window/crop is available, and runs `curator_query` for PDF-focused turns
  only after L3 is complete.
- Current build architecture: `compile_global_l3()` calls
  `synthesis.generate_synthesis(...)`, so L4 is attempted as part of global L3.
  However, `run_l3_from_existing_atoms()` currently sets source `l4_status` back
  to `pending` after `compile_global_l3()`, and synthesis generation itself does
  not mark source `l4_status='done'`/`skipped`. This is a likely source of report
  12's "L4 stays pending" symptom.

## 7. Execution Phases

- **P0 — Triage & Baseline**
  - Move inbox items into this plan and ROADMAP; empty `USER_REPORT.md`.
  - Run focused existing tests for touched areas where cheap.

- **P1 — Backend Source Safety and Recovery**
  - Tests first for `source rm`, `source retry`, `jobs rerun`, VLM sanitizer, and
    `remove_source(` caller audit expectations.
  - Implement minimal backend fixes.
  - Update user/workflow docs and Korean counterparts.

- **P2 — L2 English Contract and Wikilink Generation**
  - Tests first for English generated L2 output, language-guard retry/failure,
    and malformed wikilink reproduction.
  - Fix prompt/generator/lint root causes and add the programmatic English guard.
  - Raw source evidence remains unmodified even when Korean.

- **P3 — Plugin Source Badge, Popover Copy, and Link Interactivity**
  - Tests first for source-status key consistency, quick-query LaTeX stamping,
    and rendered curator wikilink interactivity.
  - Implement minimal plugin fixes and update plugin docs/spec.

- **P4 — PDF Reference Lookup and Convert-to-LaTeX**
  - Tests first for bare `(19.11)` reference extraction and use of available PDF
    search hits/context using sidechat's priority model.
  - Keep text-selection Convert-to-LaTeX on the dedicated backend extractor, but
    make its prompt/normalizer output only faithful LaTeX+text without extra prose.

- **P5 — L4 Build/Status Clarity**
  - Tests first for global L3/L4 build status: when synthesis nodes are produced,
    source `l4_status` becomes `done`; when no eligible community reports exist,
    status becomes `skipped` or another documented non-pending terminal state with
    a clear message.
  - Fix runtime/status/dashboard wording so the user can tell whether L4 is
    pending work, skipped due to no reports, or failed.

- **P6 — PDF Scroll Performance**
  - Profile active-context capture, PDF text extraction, source-status polling,
    and render handlers.
  - Patch only the measured jank source.

- **P7 — Multiple Quick-Query Popovers**
  - Tests first for current-selection quick query opening without removing
    existing popovers and for per-selection popover session registration.
  - Implement within the existing popover class; do not introduce persistence or
    sidebar history coupling.

- **P8 — Testbed, Version, Changelog, Cleanup**
  - Run feasible testbed smoke.
  - Bump versions to `0.25.1`; update `CHANGELOG.md`.
  - Clean roadmap/user report and delete plan artifacts only after shipping.
