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

### parsers/pdf.py — DONE
All 8 sites are best-effort wrappers over PyMuPDF/pymupdf4llm (opaque,
version-dependent surface → R2 KEEP+log+comment, no NARROW):
| line | disposition | note |
|---|---|---|
| 38 `_extract_pdf_toc` | KEEP+log(debug) | optional outline |
| 73 per-image xref | KEEP+log(debug) | skip one bad image, continue |
| 76 `_extract_pdf_images` outer | KEEP+log(debug) | partial images |
| 139 `parse` main | unchanged | already SURFACE-correct (`raise ParserError … from e`) |
| 188 title metadata | KEEP+log(debug) | falls through to first-line/filename |
| 209 author/date metadata | KEEP+log(debug) | optional enrichment |
| 232 `get_page_count` | KEEP+log(debug) | callers treat 0 as unknown |
| 267 `parse_page_window` | KEEP+log(**warning**) | load-bearing for L2 completeness |
Tests: `backend/tests/test_error_handling_pdf.py` (4) — fallback preserved + logged.
### llm.py — DONE (handlers only; no prompt/identity logic touched)
| line | disposition | note |
|---|---|---|
| 70 `detect_ram_gb` | NARROW (OSError, ValueError, SubprocessError)+log | default 32GB |
| 113 `get_ollama_model_capabilities` | NARROW (httpx.HTTPError, ValueError)+log | [] |
| 228 `OllamaClient.unload` | NARROW httpx.HTTPError+log | best-effort VRAM free |
| 1062 Codex auth read | NARROW (OSError, ValueError)+log | falls through to CodexCliError |
| 1322 failover ping | KEEP+comment | provider ping may raise anything → "down" |
| 1346 `ensure_ready` failover | KEEP+log+comment | the failover mechanism; surfaces LLMError |
| 1449 `unload` loop | KEEP+log+comment | best-effort cross-provider cleanup |
| 1456 `close` loop | KEEP+log+comment | best-effort teardown |
| 1477 `list_models_on_host` | NARROW (httpx.HTTPError, ValueError)+log | [] |
Tests: `backend/tests/test_error_handling_llm.py` (4) — empty+log on transport
error; unexpected error propagates (NARROW).
### ingest_raw.py — DONE (12 sites)
- 155 `_resolve_reference_source` → **KEEP+log(warning)** (review-corrected: NOT
  SURFACE; multi-subsystem best-effort resolver, fall back to `return source`).
- 265 reference-candidate scan → NARROW (OSError, yaml.YAMLError)+log → continue.
- 1144 `_safe_vault_subdir` → NARROW (OSError, ValueError, RuntimeError)+log → None.
- 1184 `_save_pdf_images` → NARROW OSError+log(warn) → partial saved.
- 490, 1368, 1612, 1627, 2068, 2255 → KEEP+comment (already surface via print /
  DB l1 status / ERROR AddOutcome).
- 1409, 1527 → KEEP, already documented+printed (untouched).
- Removed an unused `sqlite3` import added during drafting (KEEP chosen over NARROW).
Tests: `backend/tests/test_error_handling_ingest.py` (2) — transient-DB-lock
fallback (reviewer scenario) + `_safe_vault_subdir` None+log.

### ingest_worker.py — DONE (9 sites)
- 198, 212 runtime snapshots → KEEP+log(debug)+comment (best-effort dashboard).
- 233 token accounting → KEEP+log(debug)+comment.
- 271 finally client.close → KEEP+log(debug)+comment.
- 171 global-L3, 253 job boundary → KEEP+comment (already surface: re-raise /
  retry+mark-failed; central to v0.27.2 resilience).
- 220, 359, 452 → already log with non-fatal rationale (untouched).
Regression: existing `test_prompt_trace`, `test_compile_pipeline`,
`test_knowledge_unit_extraction` still green (32).
### pipeline/compile.py — DONE (7 sites)
- 145 `_resolve_span_text` → KEEP (already raises SpanTextUnavailable; commented).
- 187 `hydrate_spans` → KEEP+log(debug)+comment (omit unavailable source, now logged).
- 224 L2 parse boundary → KEEP+comment (surfaces l2 error + CompileResult error).
- 307 staged-compile rollback, 527 transactional rollback → KEEP+comment (discard
  staged generation + surface/re-raise; never publish a partial generation).
- 582 per-report prose, 593 L4 synthesis → KEEP+log(warning)+comment (collect to
  errors list which gates synthesis; now also logged).
Tests: `backend/tests/test_error_handling_compile.py` (1) — hydrate_spans omits
unavailable source + logs. Regression: `test_compile_pipeline` 10 passed.

## Final disposition summary (slice 1)
6 modules, 51 sites: NARROW 12 · KEEP+log/comment 35 · already-compliant
(untouched) 4. SURFACE forced: 0 (every candidate had a valid fallback or already
surfaced — consistent with the R1 "KEEP/NARROW-first" bias). New tests: 14.

## Validation log
- config.py: ruff ✓, mypy ✓, `test_error_handling_config.py` 3 passed.
- Baseline full pytest count (branch base): **1090 passed, 6 skipped, 5 xfailed**
  (400s). Gate: post-change full pytest must keep ≥ 1090 passed (+ new tests).
