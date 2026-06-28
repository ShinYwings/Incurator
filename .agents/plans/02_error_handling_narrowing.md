# v0.27.5 — Error-Handling Narrowing (XC-1, slice 1) — Master Implementation Plan

Date: 2026-06-28
Status: DRAFT — awaiting user approval (planning phase; no code yet)
Briefing: `.agents/plans/xc1_error_handling_arena/00_problem.md`
Domain analysis: `.agents/plans/A_exception_taxonomy.md`
Parent milestone: `.agents/plans/01_system_stability_overhaul.md` (Phase: S2 architectural)

## 1. Objective

Eliminate **bug-masking broad-`except`** in the backend **data-pipeline core** by
classifying every broad catch in scope into {KEEP, NARROW, SURFACE, DELETE} and
resolving it, so real failures are surfaced/logged instead of silently swallowed —
**without regressing the pipeline's intentional fault-tolerance**.

**Definition of done**: every broad-except in the six in-scope modules
(`config.py`, `parsers/pdf.py`, `llm.py`, `ingest_raw.py`, `ingest_worker.py`,
`pipeline/compile.py`, ~51 sites) is dispositioned and resolved with a test or a
justifying comment; the per-module inventory in `02_roadmap_evidence.md` is
complete; `ruff`/`mypy`/`pytest`/`vitest` green; testbed `wiki add/sync` parity
holds (no new aborts).

## 2. Explicit Non-Goals

- NOT touching the god-files `cli.py`, `mcp_server.py`, `plugin_api.py` (→ CM-1).
- NOT `model_setup.py` (→ second error-handling PR).
- NOT plugin `console.*`/timer hardening (→ XC-4).
- NOT prompt/identity logic in `llm.py` (→ prompt-v2); only its except handlers.
- NOT introducing a new logging framework or Result/Either error type.
- NOT a schema or public-contract change.

## 3. Strict Quality Conditions & Release Gates

- Every in-scope broad-except has a recorded disposition + rationale in the
  Evidence Ledger inventory (100% coverage of the slice; no site left unjudged).
- Each NARROW/SURFACE change has a behavioral test (outcome-asserting, not
  log-string-only) proving the error now propagates/handles correctly.
- Each KEEP carries a justifying comment AND logs (no remaining silent swallow in
  scope).
- `scripts/backend-check ruff|mypy|pytest` green; full `pytest` ≥ prior pass
  count; `git diff --check` clean.
- Testbed `VAULT_ROOT=testbed wiki add` on a multi-page source completes without a
  new abort introduced by a SURFACE change.

## 4. Locked Design Decisions (Arena Consensus)

- **Four-way disposition** per `A_exception_taxonomy.md`.
- **DAG-build bias: KEEP/NARROW first; SURFACE only with testbed proof** (R1).
- **Undecidable exception surface ⇒ KEEP+log, never NARROW** (R2).
- **Behavioral tests over log-string asserts** (R3).
- **Hard scope boundary** as in §2 (R4).
- **Patch 0.27.5** — internal error-handling only; no new user-facing capability
  and no schema/contract change, so per the 0.x SemVer criteria this is a Patch,
  not a Minor. The spec-line sync mandate does NOT apply: the `0.27` minor line is
  unchanged, so the four spec titles are NOT touched.
- **XC-2 guardrail**: no grep-and-replace; every change is read-justified.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: god-files, `model_setup.py`, plugin, prompt-v2 (see §2).
- **Stop Conditions**:
  - If a SURFACE change causes a testbed `wiki add/sync` regression that can't be
    resolved by re-classifying to KEEP/NARROW → STOP and report.
  - If narrowing a third-party-heavy body (pdfminer/sqlite/providers) can't be
    done safely (undecidable surface) → KEEP+log; do not force NARROW.
  - If the slice grows beyond the six modules → STOP (scope creep).

## 6. Evidence Ledger

Created as `02_roadmap_evidence.md` immediately before P1 coding:
- **Rollback anchor**: branch `fix/error-handling-pipeline` off `master` at the
  post-#63 merge (AGENTS.md allows only `release/`, `feature/`, `fix/`, `chore/`,
  `hotfix/` prefixes — `refactor/` is invalid); each module is an independent
  commit so any single module can be reverted.
- **Current reality**: 270 backend broad-excepts (scan 2026-06-28); 51 in scope;
  documented best-effort guards enumerated so they are preserved.
- **Dirty worktree**: none expected (IDLE before branch).
- **Per-module inventory table** (file:line · raisable set · disposition ·
  rationale) filled during P0 and kept as the audit trail.

## 7. Execution Phases (TDD + CI at each phase)

- **P0 — Inventory & baseline.** Read every in-scope try-body; fill the
  disposition inventory in `02_roadmap_evidence.md`; capture baseline `pytest`
  count and a testbed `wiki add` baseline. No code changes.
- **P1 — config.py + parsers/pdf.py.** Lowest pipeline risk. TDD per site;
  `ruff`/`mypy`/`pytest`.
- **P2 — llm.py (handlers only).** NARROW/SURFACE provider/JSON swallows; no
  prompt logic. Verify provider-failure tests.
- **P3 — ingest_raw.py + ingest_worker.py.** KEEP the documented best-effort
  guards. The `:155` path-resolution block is a **graceful fallback** (DB/path
  lookup → `return source` on failure), NOT a SURFACE: re-raising would crash the
  caller on a transient `sqlite3.OperationalError`/`OSError`. Disposition =
  **NARROW** (catch the expected resolution exceptions — `sqlite3.Error`,
  `OSError`, `ValueError` — log a warning, fall through to `return source`); fall
  back to KEEP+log if the raisable surface proves undecidable. Re-validate with a
  testbed `wiki add`.
- **P4 — pipeline/compile.py.** NARROW; assert checkpoint-resume + chunk-budget
  paths intact (re-run the v0.27.2 regression tests).
- **P5 — Testbed smoke + docs.** `wiki add/sync` parity; update
  `SYSTEM_BEHAVIOR.md` only if any SURFACE changed a documented best-effort
  behavior; version bump **0.27.5** (Patch — spec titles NOT touched) + CHANGELOG;
  open PR from `fix/error-handling-pipeline`.

## 8. Multi-Agent Role Sign-off (simulated)

- **peer_reviewer**: each except change is read-justified and outcome-tested.
- **schema_guardian**: no schema/prefix/frontmatter change; Patch bump leaves the
  four spec titles on the existing `v0.27` line (no spec-line sync).
- **source_pair_analyst**: DAG fault-tolerance preserved; SURFACE changes
  testbed-validated (R1).
- **qa_runner**: ruff/mypy/pytest/vitest + testbed `wiki add/sync`.
- **rollback_strategist**: per-module commits enable single-module revert.
