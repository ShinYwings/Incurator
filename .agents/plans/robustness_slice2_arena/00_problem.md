# Briefing: Robustness Slice 2 — model_setup error-handling (XC-1) + plugin timers/logging (XC-4)

Date: 2026-06-28 | Phase: System Stability Overhaul → Phase C (robustness)

## Problem

Two diagnosis items remain in the error-handling/robustness theme, both deferred
from XC-1 slice 1:

- **XC-1 (model_setup.py)**: 11 broad-`except` sites in the model setup path
  (`ollama serve`/`pull`, reachability probes, backend model provisioning).
  Excluded from slice 1 as "setup/UX, lower risk"; now in scope.
- **XC-4 (plugin)**: timing/observability hardening.
  - **Timers**: 39 `setTimeout`/`setInterval` across the plugin (10 in
    `chatSidebar.ts`, 10 in `main.ts`, 9 in `externalPdfView.ts`, …). 25
    cleanup calls (`registerInterval`/`clearInterval`/`clearTimeout`) already
    exist, so the job is to find the GAPS — timers not cleared on
    unload/teardown (leaks, detached-DOM callbacks) and ordering races
    (diff-viewer had a documented race in v0.14.1).
  - **console.\***: 42 `console.*` calls (14 `main.ts`, 9 `externalPdfView.ts`,
    …). No gated logger exists — verbose logs always spam the user's dev
    console. Route through a namespaced, level-gated logger so user consoles
    stay quiet by default while errors remain visible.

## Constraints

- **XC-2 guardrail** (from slice 1): no grep-and-replace for excepts; each
  decision comes from reading the `try` body.
- **No new user-facing setting / contract change** — gate verbose logging via a
  `localStorage` dev flag, not a plugin setting, so this stays a **Patch** and
  changes no public contract.
- **CLAUDE.md surgical**: timer fixes touch only the timer lifecycle; console
  conversion is mechanical and must not change control flow.
- **Reviewability**: this is a large surface; phases are independently
  shippable (see master plan §5 — console-gating may split to a follow-up PR if
  the combined diff is too large to review well).

## Definition of done

`model_setup.py` excepts classified+resolved (test/comment each); every plugin
timer is cleared on teardown or justified; `console.*` routed through the gated
logger; `pytest`/`ruff`/`mypy`/`vitest`/`tsc` green; no plugin behavior
regression.
