# Critique on Robustness Slice 2 + Resolution

Date: 2026-06-28 | Agent Persona: red_teamer

## 1. Vulnerabilities & Flaws

1. **console.log → logger.debug silently HIDES logs users/devs relied on.**
   Some `console.log` calls may be load-bearing for field debugging (e.g. sync
   diagnostics). Gating them off-by-default could make a future bug report
   harder to triage.

2. **localStorage may be unavailable / throw.** In some Obsidian contexts
   `localStorage` access can throw; the `DEBUG` initializer must not crash plugin
   load. (Proposal already wraps in try/catch — verify.)

3. **DEBUG captured once at module load.** Toggling `incurator-debug` at runtime
   won't take effect until reload. Acceptable, but document it.

4. **Timer audit scope creep / churn.** "Audit 39 timers" can balloon. Converting
   already-managed timers risks regressions for zero benefit.

5. **Converting console.error → logger.error changes the emitted string** (adds
   `[Incurator]` prefix). Any test asserting exact console output, or any log
   scraper, could break.

6. **model_setup NARROW incompleteness** — the exact failure-mode class that bit
   slice 1 twice (AttributeError/IndexError/RuntimeError on closed clients).

## 2. Suggested Alternatives (accepted into the Master Plan)

- **R1**: `console.warn`/`console.error` → `logger.warn`/`logger.error`
  (always-visible). `console.log`/`console.debug` → `logger.debug` (gated). Do
  NOT gate anything that reports an error/failure. When a `console.log` is
  clearly a load-bearing diagnostic, promote it to `logger.info` (also gated) but
  flag it in the ledger so we can reconsider.
- **R2**: keep the `localStorage` access wrapped in try/catch (done); module-load
  capture is fine — document the reload requirement in a code comment.
- **R3**: timer audit is **gap-only**: touch a timer ONLY to (a) add missing
  teardown cleanup, (b) guard a callback that runs post-teardown, or (c) fix a
  real ordering race. Already-managed timers are left untouched and listed as
  "managed — no change" in the ledger (no silent caps: every one of the 39 is
  accounted for).
- **R4**: grep tests for `console.` assertions before converting; none should
  break (the `*.test.ts` console calls are excluded from conversion).
- **R5**: model_setup excepts — enumerate the FULL raisable set per body
  (subprocess.SubprocessError, OSError, httpx.HTTPError, plus `.get()`/index
  AttributeError/IndexError on any parsed data); when uncertain, KEEP+log.

## 3. Consensus

Adopt R1–R5. The gated logger does not gate error/warn. Timer audit is gap-only
with full accounting of all 39. model_setup narrowing enumerates completely or
KEEPs. Patch 0.27.6. console-gating phase may split to a follow-up PR if the
combined review is too large (master plan §5 stop-condition).
