# Evidence Ledger — v0.27.5 Error-Handling Narrowing (XC-1 slice 1)

Date: 2026-06-28 | Branch: `fix/error-handling-pipeline` (off `master` post-#63)

## Rollback anchor
- Branch base: `master` at `2986e54` (post PR #63 merge) + the plan-docs commit.
- Each module is its own commit → single-module revert is safe.

## Current repository reality (scan 2026-06-28)
- 270 backend broad-`except` sites total. In scope this slice: 6 data-pipeline
  modules (~51 sites). God-files (`cli.py`, `mcp_server.py`, `plugin_api.py`),
  `model_setup.py`, plugin, and `llm.py` prompt logic are OUT (see plan §2).
- Baseline `scripts/backend-check pytest`: captured at branch base (see Validation).

## Dirty worktree
- None at branch creation (repo was IDLE; plan docs committed first).

## Per-module disposition inventory (audit trail)

### config.py — DONE (commit pending)
| line (orig) | handler before | raisable | disposition | note |
|---|---|---|---|---|
| 328 | `except Exception: pass` | OSError, yaml.YAMLError | NARROW+log | global config read |
| 352 | `except Exception: pass` | OSError, ValueError | NARROW+log(debug) | get_last_root |
| 363 | `except Exception: pass` | OSError | NARROW+log(warn) | set_last_root (best-effort cache) |
| 414 | `except Exception: pass` (after YAMLError) | OSError | NARROW+log | global config merge |
| 436 | `except Exception as e:` (logs) | many (dict+file rewrite) | KEEP+log+comment | migration must not hard-fail CLI |
| 514 | `except Exception: pass` | OSError, yaml.YAMLError | NARROW+log(debug) | find_wiki_root scan |

Tests: `backend/tests/test_error_handling_config.py` (3) — malformed-settings
fallback preserved; unexpected error propagates (NARROW); bad-read logs+None.

### parsers/pdf.py — pending (P1)
### llm.py — pending (P2)
### ingest_raw.py / ingest_worker.py — pending (P3)
### pipeline/compile.py — pending (P4)

## Validation log
- config.py: ruff ✓, mypy ✓, `test_error_handling_config.py` 3 passed.
- Baseline full pytest count: (recorded from branch-base background run).
