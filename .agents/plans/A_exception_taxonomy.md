# Domain Analysis: Exception Taxonomy & Per-Module Inventory (XC-1)

Date: 2026-06-28 | Component: backend error-handling

## Design constraints from the codebase

- Modules use the stdlib `logging` module with a module-level `logger`. No custom
  error framework exists; do not introduce one.
- The DAG build (`ingest_*`, `pipeline/*`) is intentionally fault-tolerant in
  places (instant-L1 guard, per-page fallback). v0.27.2 added checkpoint-resume
  and fail-fast-after-terminal-error semantics — error-handling changes MUST NOT
  regress those.
- Search/DB are DB-native; no external binaries. Not in this slice's scope.

## docs/specs invariants

- `SYSTEM_BEHAVIOR.md` describes pipeline resilience (a single bad item should
  not abort a whole source where the design says "best effort"). Any SURFACE
  decision that changes that must be reflected in `SYSTEM_BEHAVIOR.md`.
- No schema change in this slice → `SCHEMA.md` untouched (only the version line
  on the Minor bump).

## The four-way disposition (decision contract)

| Disposition | When | Action | Test |
|---|---|---|---|
| **KEEP** | broad catch is correct (genuine best-effort/optional step) | add justifying comment + `logger.warning/debug` | characterization: fallback still happens |
| **NARROW** | raisable set is knowable from stdlib/our code | `except (X, Y)`; unexpected propagate | behavioral: unexpected type now propagates |
| **SURFACE** | swallow hides a whole-operation bug | log w/ context + re-raise or typed error | behavioral: error path raises/handled |
| **DELETE** | caught type provably unreachable / redundant | remove try/except | rely on existing tests |

**Bias inside the DAG build** (`ingest_raw`, `ingest_worker`, `pipeline/compile`):
KEEP/NARROW first; SURFACE only with testbed `wiki add` proof it does not abort a
multi-page run (red-team R1/R2).

## Per-module inventory (to be filled at fix-time, P0 deliverable)

Each row: `file:line` · current handler · raisable set (from reading body) ·
disposition · rationale. Created as the working ledger before edits; the final
state is summarized in the Evidence Ledger `02_roadmap_evidence.md`.

### In scope (first slice, ~51 sites)
- `config.py` (6; 5 silent) — config/yaml/file reads → expect mostly NARROW
  (`OSError`, `yaml.YAMLError`, `KeyError`).
- `parsers/pdf.py` (8; 4 silent) — pdfminer surface undecidable in places →
  KEEP+log where the lib surface is opaque (R2); NARROW file I/O.
- `llm.py` (9; 6 silent) — swallow-narrowing ONLY; no prompt/identity logic change
  (R4). Expect NARROW on JSON/HTTP, SURFACE where a provider error is hidden.
- `ingest_raw.py` (12; 2 silent) — KEEP the 2 documented L1/per-page guards.
  `:155` is a **graceful fallback** (DB/path lookup → `return source` on failure),
  NOT a SURFACE — re-raising would crash the caller on transient
  `sqlite3.OperationalError`/`OSError`. Disposition = **NARROW** (`sqlite3.Error`,
  `OSError`, `ValueError` → log warning, fall through to `return source`); KEEP+log
  if the surface is undecidable.
- `ingest_worker.py` (9; 4 silent) — job-loop resilience; bias KEEP/NARROW.
- `pipeline/compile.py` (7; 0 silent) — NARROW; verify checkpoint-resume intact.

### Out of scope (deferred, with reason)
- `cli.py` (70), `mcp_server.py` (70), `plugin_api.py` (13) → **CM-1** god-file
  decomposition (fix once, post-split).
- `model_setup.py` (11) → second error-handling PR (setup/UX, lower risk).
- plugin `console.*`/timers → **XC-4**.
- `llm.py` prompt/identity logic → **prompt-v2**.

## Alternatives considered & rejected

- *Global blanket replace* (`except Exception`→specific everywhere): rejected by
  XC-2 guardrail; misses real types, crashes where broad-catch coped.
- *Custom Result/Either error type*: over-engineering for this slice (CLAUDE.md
  #3); stdlib exceptions + logging suffice.
