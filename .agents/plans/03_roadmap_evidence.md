# Evidence Ledger — v0.27.6 Robustness Slice 2

Date: 2026-06-28 | Branch: `fix/robustness-slice2` (off `master` post-#64)

## Rollback anchor
- Base: `master` at `ac4c0d7` (post PR #64) + plan-docs commit.
- Per-phase commits → single-phase revert.

## Baselines
- Plugin `vitest`: **621 passed / 61 files**.
- Backend `pytest`: (branch-base background run — recorded on completion).

## P1 — model_setup.py (DONE, 11 sites)
| line | disposition | note |
|---|---|---|
| `_ollama_reachable` | NARROW httpx.HTTPError + log | → False |
| `ensure_ollama_serving` Popen | NARROW (OSError, SubprocessError) | → ModelStep(False) |
| `ensure_ollama_model` pull | NARROW (OSError, SubprocessError) | → ModelStep(False) |
| `unload_ollama_model` | NARROW httpx.HTTPError | → ModelStep(False) |
| `llama_cpp_installed` import | KEEP+log+comment | opaque native import surface |
| `install_llama_cpp` run | NARROW (OSError, SubprocessError) | → ModelStep(False) |
| `download_gguf` | NARROW (httpx.HTTPError, OSError) | → (None, msg) |
| embedding-smoke | KEEP+comment | smoke must catch anything → report |
| reranker-smoke | KEEP+comment | smoke must catch anything → report |
| embedding-config save | NARROW OSError | → report.add(False) |
| reranker-config save | NARROW OSError | → report.add(False) |
Tests: `backend/tests/test_error_handling_model_setup.py` (4) — http/OSError
degrade+log; unexpected error propagates (NARROW).

## P2 — plugin timers (39) — DONE: audit found NO gaps (all managed/benign)
Full accounting (all 39 — no silent caps):
- **Intervals (all MANAGED, cleared on teardown):**
  - `settings.ts:341` authPollTimer — cleared in `hide()`/`display()` (G17-1).
  - `chatSidebar.ts:241` statusPollInterval — cleared in `onClose`.
  - `chatSidebar.ts:4058` thinkingTimer — cleared in `stopThinkingTimer()`,
    which `onClose` calls (so closing mid-stream is safe).
  - `incuratorDashboardModal.ts:1022/1239` modelLoadTimer/jobsTimer — cleared in
    `onClose` (and on tab switch / self-clear).
  - `main.ts:679/1856/1942` — all wrapped in `this.registerInterval(...)`
    (auto-cleared on unload).
- **Stored timeouts (all MANAGED):**
  - `externalPdfView.ts:1710/1768` zoomDebounceTimer — cleared in `clearTimers()`
    (called by `onClose`) and re-cleared before re-arm.
  - `main.ts:1056` scrollPositionSaveTimer — one-shot, self-nulls, AND cleared in
    `onunload` (851-852).
  - `agent/syncScheduler.ts:24` timer — cleared in `stop()` / before re-arm.
  - `agent/mcpClient.ts:163`, `agent/llmClient.ts:621` — request timeouts cleared
    via `clearTimeout` on response (standard timeout-race pattern).
- **Fire-once UI deferrals (BENIGN one-shots, 0–250ms; not repeating → no leak):**
  `chatSidebar.ts:259/303/582/583/2432/2805/4493/4813`,
  `externalPdfView.ts:905/916/927/938/1716/1775/1806`,
  `zoteroWizardModal.ts:144`, `mcpClient.ts:95/208`,
  `main.ts:159/176/617/841/1033/1964`. Deferred render/focus/scroll; a detached
  element access is a harmless no-op. Per R3 (gap-only) these are left untouched.

**No code change in P2** — the audit confirms hygiene; fixes were only to be made
for real gaps and none exist.

## P3 — console.* (42) — DONE
- New `plugin/src/utils/logger.ts` (+ `logger.test.ts`, 4 tests): `debug`/`info`
  gated by `localStorage["incurator-debug"]==="1"` (captured at load; graceful
  if localStorage absent); `warn`/`error` always emit; `[Incurator]` prefix.
- Converted all 42 `console.*` across 12 files via a one-shot transform:
  `console.log/debug`→`logger.debug` (gated), `console.info`→`logger.info`,
  `console.warn`→`logger.warn`, `console.error`→`logger.error`. Stripped legacy
  `[Incurator]`/`[AI Agent]` prefixes (logger re-adds `[Incurator]`); kept
  `[MCP:…]` sub-namespaces.
- Verified: 0 raw `console.*` in plugin source except `logger.ts`; no
  double-prefixing; `tsc` clean; vitest 625 passed (updated one stale
  source-guard: `llmClient.test.ts` now expects `logger.warn`).

## Final summary (slice 2)
- model_setup: 11 sites (7 NARROW, 3 KEEP+comment, 1 KEEP+log) + 4 tests.
- timers: 39 audited, all managed/benign, **0 fixes** (hygiene already solid).
- console: 42 routed through the gated logger + 4 logger tests.
- Patch 0.27.6; no schema/setting/contract change.
