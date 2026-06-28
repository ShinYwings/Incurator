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

## P2 — plugin timers (39) — pending
Full accounting table (file:line · disposition managed/convert/guard/race-fix)
filled during P2.

## P3 — console.* (42) — pending
`src/utils/logger.ts` + conversion checklist filled during P3.
