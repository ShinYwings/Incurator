# Proposal: Robustness Slice 2

Date: 2026-06-28 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

### Part A — model_setup.py error-handling (XC-1, 11 sites)

Reuse the slice-1 four-way disposition (KEEP / NARROW / SURFACE / DELETE). These
sites wrap `subprocess.Popen`/`run` (ollama serve/pull), `httpx` reachability,
and model provisioning, and already return structured `ModelStep(ok=False, msg)`
results. Expected dispositions:
- Reachability/probe (`_ollama_reachable`): NARROW `httpx.HTTPError` (+ maybe
  `OSError`) → return False.
- subprocess launch/run: NARROW `(OSError, subprocess.SubprocessError)` → return
  `ModelStep(ok=False, …str(exc))` (already surfaces in the message).
- Anything spanning a heterogeneous surface: KEEP+log+comment.
Each gets a justifying comment + log; NARROW gets a propagation test where
practical.

### Part B1 — plugin timer lifecycle audit (XC-4, 39 sites)

For each `setTimeout`/`setInterval`:
- **Interval** → must use Obsidian `this.registerInterval(window.setInterval(…))`
  (auto-cleared on unload) OR be cleared in `onunload`/`onClose`. Convert
  unmanaged intervals.
- **Timeout** → store the handle and `clearTimeout` it in the owner's teardown
  (`onunload`/modal `onClose`/view `onClose`); guard the callback against
  running after teardown (detached-DOM / disposed-state check) where it touches
  DOM or plugin state.
- **Ordering races** → audit callbacks that assume a prior async step finished;
  re-check the diff-viewer pattern (v0.14.1 history).
Record each timer's disposition (managed / converted / race-fixed) in the
evidence ledger. Fix only real gaps — do not churn already-managed timers.

### Part B2 — console.* gating (XC-4, 42 sites)

New `plugin/src/utils/logger.ts`:
```ts
const DEBUG = (() => { try { return localStorage.getItem("incurator-debug") === "1"; } catch { return false; } })();
export const logger = {
  debug: (...a: unknown[]) => { if (DEBUG) console.debug("[Incurator]", ...a); },
  info:  (...a: unknown[]) => { if (DEBUG) console.info("[Incurator]", ...a); },
  warn:  (...a: unknown[]) => console.warn("[Incurator]", ...a),
  error: (...a: unknown[]) => console.error("[Incurator]", ...a),
};
```
Conversion: `console.log`→`logger.debug` (gated), `console.warn`→`logger.warn`,
`console.error`→`logger.error`. Errors/warnings stay always-visible; verbose
logs are off unless a developer sets `localStorage["incurator-debug"]="1"`. No
plugin setting, no contract change. (Leave `*.test.ts` console calls alone.)

## 2. Pros & Cons

**Pros**: completes the XC robustness theme; timer audit fixes real leak/race
classes; quieter user console without losing error visibility; all
Patch-level (no contract/setting change).

**Cons**: large surface (92 sites). Mitigation: phase boundaries are
independently shippable; console-gating (B2) can split to a follow-up PR if the
combined diff is too big. Timer audit is investigative — if it uncovers a
non-trivial race, that race gets its own captured finding rather than an ad-hoc
inline fix.
