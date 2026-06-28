# Error-Handling Proposal: Classify-Then-Resolve, Module-Scoped

Date: 2026-06-28 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

### 1.1 The four-way decision (applied per site)

For each broad-except, read the `try` body and the handler, then assign exactly
one disposition:

- **KEEP** — the broad catch is the correct behavior (a true best-effort/optional
  step where *any* failure must degrade gracefully). Requirement: the handler
  MUST (a) carry a one-line justifying comment stating why catching broadly is
  correct, and (b) log at `debug`/`warning` with context (not silent). No
  control-flow change. Example: `ingest_raw.py:1409` instant-L1 guard.
- **NARROW** — the body raises a known, finite set of exceptions; replace
  `except Exception` with `except (X, Y)`. Unexpected exceptions now propagate.
  Example: a JSON read → `except (OSError, json.JSONDecodeError)`.
- **SURFACE** — the swallow hides a real failure AND the operation has no valid
  fallback. Add contextual logging AND either re-raise or convert to a
  typed/handled error the caller acts on. (Note: `ingest_raw.py:155` is NOT a
  SURFACE — it has a deliberate `return source` fallback, so it is NARROW+log.)
- **DELETE** — the guarded code cannot raise the caught type (provably), or the
  try/except is redundant with an outer handler; remove it.

### 1.2 Logging contract

Introduce a single helper convention (reuse the module's existing logger; do NOT
add a new logging framework). Every KEEP/SURFACE handler logs with:
`logger.warning("<operation> failed: %s", exc)` (or `exception(...)` where a
traceback aids debugging). No new global logger module — XC-4 (plugin
`console.*` gating) is a separate item.

### 1.3 Module scope (first Minor)

Data-pipeline core where silent swallows corrupt L1–L4 output:
`config.py`, `parsers/pdf.py`, `llm.py`, `ingest_raw.py`, `ingest_worker.py`,
`pipeline/compile.py`. ~51 sites. The god-files (`cli.py`, `mcp_server.py`,
`plugin_api.py`) are explicitly deferred to the CM-1 decomposition, because
their except sites are entangled with the structure that CM-1 will split — fixing
them twice is wasteful and risks merge churn.

### 1.4 Per-site workflow (TDD)

1. Read `try` body → enumerate raisable exceptions.
2. Decide disposition; record it in `A_exception_taxonomy.md` (the inventory).
3. For SURFACE/NARROW: write a failing test that drives the error path and
   asserts it is logged/raised (not swallowed); then change the handler.
4. For KEEP: add a characterization test asserting the graceful fallback still
   happens, plus the justifying comment.
5. For DELETE: prove unreachable (type/constant), remove, rely on existing tests.

## 2. Pros & Cons

**Pros**: correctness-first (un-masks real bugs); per-site isolated (each change
is small and reviewable); no public-contract/schema change; testable.

**Cons**: surfacing errors that were previously swallowed can make operations
that *silently degraded* now *fail loudly* — this is the intended behavior change
but must be called out in the CHANGELOG and validated against testbed so we don't
turn a tolerable degradation into a hard pipeline abort. Mitigation: the KEEP
category exists precisely for genuine best-effort steps; when unsure, prefer
NARROW (propagate only the unexpected) over SURFACE (force an error).
