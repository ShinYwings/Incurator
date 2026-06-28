# v0.27.6 — Robustness Slice 2 (XC-1 model_setup + XC-4 plugin timers/logging) — Master Implementation Plan

Date: 2026-06-28
Status: DRAFT — awaiting user approval (planning phase; no code yet)
Briefing: `.agents/plans/robustness_slice2_arena/00_problem.md`
Domain analysis: `.agents/plans/B_plugin_logging_and_timers.md`
Parent milestone: `.agents/plans/01_system_stability_overhaul.md`

## 1. Objective

Complete the error-handling/robustness theme: (A) narrow bug-masking broad-`except`
in `model_setup.py` (XC-1, 11 sites); (B) harden plugin timing/observability
(XC-4) by (B1) auditing all 39 `setTimeout`/`setInterval` for teardown leaks and
ordering races and (B2) routing all 42 `console.*` through a new namespaced,
level-gated logger so user consoles stay quiet by default while errors stay
visible.

**Definition of done**: every `model_setup.py` broad-except dispositioned with a
test or justifying comment; every one of the 39 timers accounted for (managed /
converted / guarded / race-fixed) in the evidence ledger; all 42 `console.*`
(excluding `*.test.ts`) routed through `logger`; `pytest`/`ruff`/`mypy`/`vitest`/
`tsc` green; no plugin behavior regression.

## 2. Explicit Non-Goals
- NO new plugin setting / `PluginSettings` field (verbose logging gated via
  `localStorage["incurator-debug"]`, a dev affordance) — keeps this a Patch.
- NO god-file decomposition (CM-1/DB-2/PL-1) and NO god-file excepts
  (`cli.py`/`mcp_server.py`/`plugin_api.py` — those ride CM-1).
- NO gating of `console.warn`/`console.error` (must stay visible — R1).
- NO churn of already-managed timers (gap-only — R3).
- NO backend logic change beyond `model_setup.py` except handlers.

## 3. Strict Quality Conditions & Release Gates
- `model_setup.py`: every broad-except has a recorded disposition + rationale;
  NARROW enumerations are complete (slice-1 lesson) or fall back to KEEP+log.
- Timers: all 39 enumerated in the ledger; converted/guarded ones have a test or
  a teardown assertion where practical.
- console: 0 remaining `console.*` in plugin source (excluding `*.test.ts`);
  `logger` unit-tested (gated debug suppressed, warn/error always emit).
- `scripts/backend-check ruff|mypy|pytest` green (full pytest ≥ prior pass
  count + new tests); `npx vitest run` + `npx tsc --noEmit` green; `git diff --check` clean.

## 4. Locked Design Decisions (Arena Consensus)
- Four-way except disposition (slice-1 taxonomy) for `model_setup.py`.
- Logger contract per `B_plugin_logging_and_timers.md` (debug/info gated;
  warn/error always; `[Incurator]` prefix; localStorage flag captured at load).
- Timer disposition table per the domain analysis; **gap-only** edits with full
  accounting of all 39.
- **Patch 0.27.6** — internal error-handling + plugin robustness + a dev-only
  logger; no new user capability, setting, or contract → spec titles untouched.

## 5. Scope Exclusions & Stop Conditions
- **Exclusions**: god-files, plugin settings, warn/error gating (§2).
- **Stop Conditions**:
  - If the timer audit uncovers a **non-trivial race** (not a simple cleanup
    gap), STOP, capture it as a `USER_REPORT.md` finding, and plan it separately.
  - If the combined diff is too large to review well, **split P3 (console
    gating) into a follow-up PR** (v0.27.7) and ship P1+P2 first.
  - If a `model_setup` NARROW can't be completed safely, KEEP+log.

## 6. Evidence Ledger
Created as `03_roadmap_evidence.md` before P1 coding: rollback anchor (branch off
`master` post-#64; per-phase commits), baseline pytest + vitest counts, the
model_setup disposition table, the full 39-timer accounting table, and the
console conversion checklist.

## 7. Execution Phases (TDD + CI each phase)
- **P0 — Inventory & baseline.** Read all model_setup except bodies + enumerate
  all 39 timers + 42 console sites into the ledger. Capture baseline counts.
- **P1 — model_setup.py (backend).** Classify+resolve 11 excepts; tests;
  `ruff`/`mypy`/`pytest`.
- **P2 — plugin timer lifecycle audit.** Convert/guard the gap timers; tests for
  teardown clearing where practical; `vitest`/`tsc`.
- **P3 — console → logger.** Add `src/utils/logger.ts` (+ unit test); convert the
  42 sites; `vitest`/`tsc`. (May split to v0.27.7 per §5.)
- **P4 — Docs + release.** PLUGIN_GUIDE(/_KR) "Debug logging" note + PLUGIN_SCHEMA
  one-liner; version 0.27.6; CHANGELOG; PR.

## 8. Multi-Agent Role Sign-off (simulated)
- **peer_reviewer**: excepts read-justified + complete; timers gap-only; console
  conversion mechanical (no control-flow change).
- **schema_guardian**: no schema/setting/contract change; spec titles unchanged.
- **qa_runner**: ruff/mypy/pytest/vitest/tsc + manual plugin smoke if feasible.
- **rollback_strategist**: per-phase commits → single-phase revert.
