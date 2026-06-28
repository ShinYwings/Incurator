# Briefing: XC-1 Broad-Except Narrowing (Error-Handling Root-Cause Pass)

Date: 2026-06-28 | Phase: System Stability Overhaul → Phase C (architectural S2)

## Problem

The backend contains **270 broad-`except` sites** (`except Exception`,
`except BaseException`, bare `except:`). A large fraction swallow errors silently
(`pass` / `continue` / `return <default>`), masking real failures. The diagnosis
ledger (XC-1) flagged this as an S2 error-handling smell:

> e.g. `ingest_raw.py:155 except Exception: pass` swallows source-path resolution
> errors → silent fallback to original `source`.

Concentration (per file, scan on 2026-06-28):

| File | broad-except | silent `→ pass` |
|---|---|---|
| `mcp_server.py` | 70 | (god-file — defer) |
| `cli.py` | 70 | (god-file — defer) |
| `plugin_api.py` | 13 | — |
| `ingest_raw.py` | 12 | 2 |
| `model_setup.py` | 11 | — |
| `llm.py` | 9 | 6 |
| `ingest_worker.py` | 9 | 4 |
| `parsers/pdf.py` | 8 | 4 |
| `pipeline/compile.py` | 7 | 0 |
| `config.py` | 6 | 5 |

Some broad-excepts are **intentionally defensive** and correct — they carry a
justifying comment, e.g. `ingest_raw.py:1409 "span extraction must never break
instant L1"` and `:1527 "transient per-page failure → fall back, never abort"`.
These must be preserved, not "fixed."

## Constraints carried from the diagnosis

- **XC-2 guardrail**: this is NOT a grep-and-replace. Every site's decision must
  come from reading the `try` body and knowing which exceptions it can actually
  raise. Blanket `except Exception → except SpecificError` without that reading
  is forbidden.
- **CLAUDE.md #7 (Root Cause Over Workarounds)**: where a swallow hides a bug,
  fix the bug or surface the error — do not keep masking it.
- **CLAUDE.md #3 (Surgical)**: touch only the except sites in scope; do not
  refactor surrounding logic.

## Definition of done (this slice)

Every broad-except in the **in-scope data-pipeline modules** is classified and
resolved into one of {KEEP, NARROW, SURFACE, DELETE} with a test or a justifying
comment; `ruff`/`mypy`/`pytest` green; no pipeline regression in testbed
`wiki add/sync`.
