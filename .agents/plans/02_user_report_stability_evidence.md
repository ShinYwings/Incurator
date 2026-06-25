# Evidence Ledger: User Report Stability Hotfixes

Date: 2026-06-25
Status: implementation complete; release cleanup pending.

## 0. Rollback Anchor

- Branch at triage: `feature/system-stability-overhaul`.
- Pre-implementation dirty files:
  - `.agents/USER_REPORT.md` modified by user.
  - `.agents/image.png`, `.agents/image-1.png`, `.agents/image-2.png` untracked.
- No application code edited during triage.

## 1. Report Mapping

| Report | Area | Initial Classification |
|---|---|---|
| 1 | Backend VLM ingest | Device-local temp path leak in generated L1 |
| 2 | Plugin source badge | Registered source still appears untracked/actionable |
| 3 | Backend generated wikilinks / lint | CTX wikilinks malformed immediately after add |
| 4 | Backend L2 prompts/projections | Generated Atom/KNU language contract drift |
| 5 | Plugin quick-query render/copy | Popover missing sidechat LaTeX source stamping |
| 6 | Plugin external PDF text copy | Text selection path overuses LLM transcription |
| 7 | Plugin PDF reference resolver | Bare equation reference and out-of-window lookup |
| 8 | Backend jobs CLI/DB | Queued rerun gives misleading terminal-only error |
| 9 | Plugin markdown rendering | Generated link not interactive |
| 10 | Backend source retry | Layer errors not selected by retry command |
| 11 | Backend source rm | Dangerous default source-file deletion |
| 12 | Backend/plugin pipeline state | L1 running/queued/pin/L4 status mismatch |
| 13 | Plugin PDF viewer performance | Scroll/render jank needs measurement |
| 14 | Plugin quick-query lifecycle | Opening a new quick query replaces the previous popover |

## 2. Review-Driven Plan Revisions

- Arena files moved under `.agents/plans/user_report_stability_hotfix_arena/`.
- VLM sanitizer placement locked to post-generation/pre-persistence.
- L2 English output now requires a programmatic guard and capped retry.
- `source rm` implementation must audit internal `remove_source(` callers before
  changing defaults.
- L4 contract clarified:
  - `wiki add` is not supposed to wait for L4.
  - `wiki build --wait`, `wiki jobs run`, or an active worker should run global
    L3 and attempt shared L4 synthesis automatically.
  - Zero SYN nodes can be valid if no community reports exist, but source
    `l4_status` must not remain indefinitely `pending` after a completed build.
- Convert-to-LaTeX remains LLM-backed through the dedicated backend extractor.
  The fix target is prompt/normalizer/provider routing, not bypassing the LLM.
- PDF reference lookup follows sidechat priority: local PDF context first,
  backend read-only context/search fallback when local context is insufficient,
  no passive auto-ingest.

## 3. Additional Repository Evidence

- `backend/src/curator/pipeline/compile.py::compile_global_l3` calls
  `synthesis.generate_synthesis(...)`, so current architecture attempts L4 as
  part of global L3.
- `backend/src/curator/ingest_llm.py::run_l3_from_existing_atoms` calls
  `compile_global_l3(...)`, then sets L4 status for L2-done sources back to
  `pending`. `pipeline/synthesis.py::generate_synthesis` writes SYN nodes but
  does not set source `l4_status`.
- `plugin/src/context/providerContextPolicy.ts::shouldUseBackendPdfContext`
  skips backend PDF context when local viewer context exists.
- `plugin/src/context/providerContextPolicy.ts::shouldRunCuratorDomainQuery`
  blocks concept-grounded `curator_query` for PDF-focused turns until an L3-ready
  source is present.
- `backend/tests/test_plugin_pdf_transcribe.py::test_transcribe_text_routes_to_dedicated_extract_model`
  confirms text-selection Convert-to-LaTeX already routes through the backend
  dedicated extract model path.

## 4. Pre-Implementation Checks To Run

- `scripts/backend-check pytest backend/tests/test_v021_background_jobs.py -q`
- `scripts/backend-check pytest backend/tests/test_plugin_cli.py -q`
- `scripts/backend-check pytest backend/tests/test_vision_resolvers.py -q`
- `scripts/backend-check pytest backend/tests/test_plugin_pdf_transcribe.py -q`
- `scripts/backend-check pytest backend/tests/test_synthesis.py -q`
- `npx vitest run -c ./plugin/vitest.config.ts plugin/src/ui/quickQueryPopover.test.ts`
- `npx vitest run -c ./plugin/vitest.config.ts plugin/src/context/quickQueryContext.test.ts`
- `npx vitest run -c ./plugin/vitest.config.ts plugin/src/context/sourceStatus.test.ts`
- `npx vitest run -c ./plugin/vitest.config.ts plugin/src/context/providerContextPolicy.test.ts`

## 5. Post-Implementation Evidence

### P1 Backend Safety/Recovery

- Added regression tests:
  - `backend/tests/test_plugin_cli.py::test_jobs_rerun_is_successful_when_job_is_already_queued`
  - `backend/tests/test_plugin_cli.py::test_source_rm_keeps_source_file_by_default`
  - `backend/tests/test_plugin_cli.py::test_source_retry_accepts_layer_error_without_aggregate_error`
  - `backend/tests/test_vision_resolvers.py::test_sanitize_transient_vision_artifacts_preserves_valid_image_links`
- Implemented:
  - `wiki jobs rerun <id>` treats already queued jobs as successful no-ops and
    still rejects running jobs.
  - `wiki source rm <id>` keeps the source file by default; `--delete-file` is
    now required for destructive file deletion.
  - `wiki source retry [id]` selects aggregate errors plus layer-scoped
    `l1_status`/`l2_status`/`l3_status`/`l4_status`/`layer_error` failures.
  - VLM PDF transcription output is sanitized after generation/normalization
    and before cache or source-text persistence. The sanitizer strips only
    Markdown link/image destinations pointing at `.cache/vision_render` temp
    paths and preserves external URLs/vault-relative assets.
- Internal caller audit:
  - `rg -n "remove_source\\(" backend/src backend/tests -S` found only
    `backend/src/curator/cli.py` plus the function definition. No automated
    cleanup caller relied on the previous destructive default.
- Verification:
  - `scripts/backend-check pytest backend/tests/test_plugin_cli.py::test_jobs_cancel_and_rerun_commands_mutate_queue backend/tests/test_plugin_cli.py::test_jobs_rerun_is_successful_when_job_is_already_queued backend/tests/test_plugin_cli.py::test_source_rm_keeps_source_file_by_default backend/tests/test_plugin_cli.py::test_source_retry_accepts_layer_error_without_aggregate_error backend/tests/test_vision_resolvers.py` -> 16 passed.
  - `scripts/backend-check ruff backend/src/curator/cli.py backend/src/curator/db.py backend/src/curator/vision.py backend/src/curator/ingest_raw.py backend/tests/test_plugin_cli.py backend/tests/test_vision_resolvers.py` -> passed.

### P2 L2 English Contract And CTX Wikilinks

- Added regression tests:
  - `backend/tests/test_compile_pipeline.py::test_compile_source_l2_repairs_non_english_generated_units`
  - `backend/tests/test_compile_pipeline.py::test_compile_source_l2_rejects_persistently_non_english_generated_units`
  - `backend/tests/test_v021_instant_l1.py::InstantL1Tests::test_structural_l1_plaintexts_parser_generated_heading_wikilinks`
  - Built-in prompt eval fixture: `knowledge_units: non-English generated fields are rejected`
- Implemented:
  - Added `generated_english` prompt validator for generated L2 fields
    (`canonical_name`, `statement`), leaving raw source spans unmodified.
  - Attached the validator to `curator.knowledge_unit_extract`, added explicit
    English prompt rules, and bumped the contract from `@v2` to `@v3`.
  - Non-English first output triggers the prompt runner's existing repair retry;
    repeated non-English output fails L2 and publishes no new ATM projection.
  - Generated CTX projections plaintext parser-generated same-document heading
    wikilinks like `[[MultipleViewGeometry#...]]` in titles, previews,
    atom-candidate scaffolding, and projected source-section text.
- Verification:
  - `scripts/backend-check pytest backend/tests/test_prompt_eval_fixtures.py backend/tests/test_compile_pipeline.py backend/tests/test_v021_instant_l1.py` -> 17 passed.
  - Combined P1+P2 focused pytest -> 33 passed.
  - Combined P1+P2 focused ruff -> passed.

### P3 Plugin Source Badge, Popover Copy, And Generated Links

- Added/updated regression tests:
  - `plugin/src/context/sourceStatus.test.ts` now treats `queued` and `running`
    as registered/inert states alongside `l1_ready..l4_ready`.
  - `plugin/src/ui/quickQueryPopover.test.ts` verifies the popover stamps
    rendered math with source LaTeX after Markdown rendering and before copy
    handling.
  - `plugin/src/context/answerLinkNavigation.test.ts` verifies explicit vault
    block locators such as `Auto Calibration#^8f735d` and
    `Auto Calibration > ^8f735d`.
  - `plugin/src/ui/chatSidebarSource.test.ts` verifies the chat sidebar reads
    `data-href` before `href` and opens generated vault block links through
    `workspace.openLinkText(...)`.
- Implemented:
  - Registered source badges are inert for `queued`, `running`, and ready
    states. `Queued`/`Building...` keep their labels but no longer expose an
    actionable Add Source path after registration.
  - Quick-query popover answer rendering now calls `stampMathSourceData(...)`
    before installing the LaTeX-preserving copy handler.
  - Chat-sidebar generated block links with explicit local block anchors open
    through Obsidian vault navigation while ordinary links and external URLs
    retain their normal behavior.
- Verification:
  - `cd plugin && npx vitest run -c ./vitest.config.ts src/context/sourceStatus.test.ts src/ui/quickQueryPopover.test.ts src/context/answerLinkNavigation.test.ts src/ui/chatSidebarSource.test.ts` -> 54 passed.
  - `cd plugin && npx vitest run -c ./vitest.config.ts` -> 58 test files / 570
    tests passed.

### P4 PDF Reference Lookup And Convert-To-LaTeX

- Added regression tests:
  - `plugin/src/context/crossReferenceResolver.test.ts` detects bare
    parenthesized dotted equation references such as `(19.11)`.
  - The same resolver test verifies `(19.11)` resolves through available local
    PDF search hits as `Equation 19.11`.
  - `backend/tests/test_plugin_pdf_transcribe.py` verifies text and image
    interactive transcription strip explanatory prose and return only the
    selected LaTeX-bearing transcription.
- Implemented:
  - Added a conservative bare-equation extractor for `(N.N...)` references,
    leaving explicit `Eq. (...)`/`Equation ...` matches preferred through the
    existing overlap handling.
  - Added an interactive-only PDF transcription prompt that requests exactly one
    `<transcription>...</transcription>` block.
  - Added `normalize_interactive_latex_transcription(...)` for the backend
    plugin transcribe path. It extracts the tag when present and strips common
    intro/outro prose/fences before the plugin copies or injects the text. The
    full-page VLM ingest path keeps the existing prompt/normalizer.
- Verification:
  - `cd plugin && npx vitest run -c ./vitest.config.ts src/context/crossReferenceResolver.test.ts` -> 15 passed.
  - `scripts/backend-check pytest backend/tests/test_plugin_pdf_transcribe.py` -> 6 passed.
  - `scripts/backend-check ruff backend/src/curator/cli.py backend/src/curator/vision.py backend/tests/test_plugin_pdf_transcribe.py` -> passed.

### P5 L4 Build/Status Clarity

- Added regression tests:
  - `backend/tests/test_compile_pipeline.py::test_compile_global_l3_marks_l4_done_when_synthesis_is_generated`
  - `backend/tests/test_compile_pipeline.py::test_compile_global_l3_marks_l4_skipped_when_no_reports_exist`
  - `backend/tests/test_compile_pipeline.py::test_l3_regeneration_preserves_l4_terminal_status`
  - `plugin/src/ui/incuratorDashboardModal.test.ts` verifies `skipped` layer
    statuses render explicitly as `Skipped`.
- Implemented:
  - `compile_global_l3(...)` now records terminal source-level L4 status for all
    L2-done sources after global L3: `done` when SYN nodes exist, `skipped` when
    no eligible community reports/syntheses exist, and `error` on L3/L4 failure.
  - `run_l3_from_existing_atoms(...)` no longer resets L4 to `pending` after
    `compile_global_l3(...)` has already determined the terminal state.
  - `generate_synthesis(...)` clears stale synthesis nodes/projections when the
    current report corpus has no served reports.
  - Dashboard Sources tab renders `Skipped` instead of hiding the status as `—`.
- Architectural answer for report 12:
  - L4 generation is automated in the current design. `wiki add` intentionally
    stops at structural L1; `wiki build --wait`, `wiki jobs run`, or the
    background worker's global L3 pass attempts shared L4 synthesis automatically.
  - No SYN nodes is valid when no eligible community reports exist, but the source
    `l4_status` must then be terminal `skipped`, not indefinitely `pending`.
- Verification:
  - `scripts/backend-check pytest backend/tests/test_compile_pipeline.py backend/tests/test_synthesis.py` -> 13 passed.
  - `scripts/backend-check ruff backend/src/curator/pipeline/compile.py backend/src/curator/pipeline/synthesis.py backend/src/curator/ingest_llm.py backend/tests/test_compile_pipeline.py backend/tests/test_synthesis.py` -> passed.
  - `cd plugin && npx vitest run -c ./vitest.config.ts src/ui/incuratorDashboardModal.test.ts` -> 17 passed.

### P6 PDF Scroll Performance

- Audit finding:
  - `ExternalPdfView` scroll handling called `updateCurrentPage()` directly on
    every raw scroll event. That method scans all rendered/placeholder page
    elements and calls `getBoundingClientRect()` for each page, then triggers lazy
    rendering. On long PDFs this is a credible jank source because it can run
    many times per frame during a scroll burst.
- Added regression tests:
  - `plugin/src/ui/externalPdfViewSource.test.ts` verifies scroll work is
    coalesced through `requestAnimationFrame`.
  - The same test verifies pending scroll frames are cancelled on close.
- Implemented:
  - Added `scheduleScrollWork(...)` so raw scroll events schedule at most one
    page-number/lazy-render pass per animation frame.
  - Added cleanup for pending scroll frames in `clearTimers()`.
- Verification:
  - `cd plugin && npx vitest run -c ./vitest.config.ts src/ui/externalPdfViewSource.test.ts` -> 5 passed.

### P7 Multiple Quick-Query Popovers

- Added regression tests:
  - `plugin/src/ui/quickQueryPopover.test.ts` verifies
    `openForCurrentSelection(...)` no longer removes existing popovers before
    opening another selection.
  - The same test verifies each quick-query open creates an independent
    `QuickQueryPopover` session registered in the parent manager.
- Implemented:
  - The selection manager now keeps one floating trigger button, but each quick
    query opens a separate child popover session.
  - Existing popovers retain their answer, position, minimized state, and
    follow-up trace when another quick query is opened.
  - Closing/unloading the manager still cleans up all child popovers.
- Verification:
  - `cd plugin && npx vitest run -c ./vitest.config.ts src/ui/quickQueryPopover.test.ts` -> 20 passed.
  - `cd plugin && npx vitest run -c ./vitest.config.ts` -> 58 test files / 576
    tests passed.

### P8 Version And Testbed Smoke

- Version bump:
  - `backend/pyproject.toml`, `plugin/package.json`, and
    `plugin/manifest.json` now agree on `0.25.1`.
  - `CHANGELOG.md` has a `0.25.1` fixed-entry for the user-report stability
    batch.
- Testbed smoke:
  - Existing `testbed/` matched `complex_math_backprop` but still used the old
    `.curator/config.yml` layout, so `VAULT_ROOT=testbed wiki status` initially
    fell back to the production last-root. The testbed was regenerated through
    `wiki testbed init complex_math_backprop --force`, not by manual production
    config edits.
  - `VAULT_ROOT=testbed .venv-dev/bin/wiki migrate` -> schema up to date v1.
  - `VAULT_ROOT=testbed .venv-dev/bin/wiki status` -> resolves
    `/Users/shin/shinywings/Incurator/testbed` and reports a clean empty
    generated state with 3 raw source files.
- Final validation:
  - `scripts/backend-check pytest` -> 1027 passed, 6 skipped, 5 xfailed after
    the backend P1-P6 changes; subsequent code changes were plugin-only plus the
    version bump.
  - `scripts/backend-check pytest backend/tests/test_spec_sync.py` -> 10 passed
    after the `0.25.1` version bump.
  - `scripts/backend-check ruff` -> passed.
  - `scripts/backend-check mypy` -> passed.
  - `cd plugin && npx vitest run -c ./vitest.config.ts` -> 58 test files / 576
    tests passed.
  - `git diff --check` -> passed.
