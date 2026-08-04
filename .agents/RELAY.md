# RELAY — v0.42.0 in PR #111 (CI green), perf work queued

## Goal

Ship v0.42.0 (PR #111, CI green, awaiting user merge), then take up the newly
reported performance work on the Quick Query popover and Convert-to-LaTeX.

## Plan Reference

- No Arena plan for v0.42.0 — HOTFIX EXCEPTION plus a direct user instruction
  with explicit requirements. Evidence in `.agents/USER_REPORT.md`.
- Arena diagnosis (`.agents/plans/system_defect_audit_arena/`) is still PAUSED;
  only `00_problem.md` exists. Two runs died on provider limits.

## Analysis And Reasoning

v0.42.0 = the v0.41.1 hotfix plus the four follow-up items, promoted to Minor
because `setup.sh` provisioning a shell alias is a new user-facing capability.

Shipped in it:

1. **Deferred-view crash (the real cause of the reported breakage).** Obsidian
   1.7.2+ restores tabs as deferred views whose `leaf.view` reports the true
   view type while carrying none of the class's methods. Six sites cast on that
   string and called `getRuntimePath()`, throwing from `getLeafFile()` — which
   feeds both `updateActiveContext()` and the open-tab inventory, so ONE
   restored PDF tab killed the context pins, sidechat Send, and the popover
   together. Restarting made it *more* likely, which is why the early
   "reload Obsidian" advice was backwards.
2. **PDF.js canvas collision** — per-page render tasks now tracked, cancelled,
   and awaited before the next render claims the reused canvas.
3. **`setup.sh` provisions the `wiki` alias** — derived from `$ROOT_DIR`,
   idempotent (replaces the previous block, including the legacy undelimited
   form, so a wrong alias self-heals), zsh+bash, and warns when another `wiki`
   is earlier on PATH (scanned against the pre-venv PATH).
4. **Build-identity gating** — version checks read `build.backend_version`
   instead of installed package metadata, and a mismatch names the launcher
   that answered.

Two of my own earlier diagnoses were REFUTED and must not be re-run: the
stale-runtime bundle gate (user had already restarted; installed bundle hash
was byte-identical to a fresh build), and the claim that the plugin called the
anaconda `wiki` (it never did — `resolveBackendCommand` refuses the bare name
and `resolveWikiBinary` only checks `<repo>/.venv/bin/wiki`; the 0.4.3 was
terminal-only, from the broken shell alias). Item 4 above was therefore already
correct and is now pinned by regression tests rather than "fixed".

## Progress Status

- PR #111 pushed at `de0e199`, all CI green (backend, plugin, version
  consistency). Local gates: backend pytest 1414 passed / 6 skipped / 4
  xfailed, Ruff clean, mypy clean (127 files), plugin Vitest 859/859 across 78
  files, `tsc --noEmit` clean, production build clean, spec/version sync 10/10.
- Verified the alias script against a COPY of the user's real `~/.zshrc`: the
  broken `/home/shin` alias is removed, other tools' blocks survive, and a
  rerun is byte-identical. The user's own `~/.zshrc` was NOT modified.
- The stale anaconda `wiki` is already gone from this machine (user removed
  it), so the PATH-conflict warning correctly stays silent here; the mechanism
  is covered by a synthetic-conflict pytest.

## Critical Context / Blockers

- **PR #111 is not merged** — that is the user's call.
- New request (2026-08-04, not started): speed up popover answers and
  Convert-to-LaTeX. Triaged in USER_REPORT.md WITH first measurements: one
  backend round-trip is ~0.20 s (fresh Python process per call), and the
  popover's pre-request reference resolution issues up to ~8–10 SEQUENTIAL
  round-trips (~1.6–2.0 s) before the provider is called. Named
  contract-preserving candidate: collapse the four one-page adjacent-equation
  probes into a single ranged `--radius` call, evaluating results in the
  documented next-first order.
- **Do not optimize yet**: the provider's share of wall-clock is still
  unmeasured and needs in-plugin instrumentation. Repo rule is benchmark-first,
  accept only on measured speedup with no quality regression.

## Update (2026-08-04 10:55) — metadata removed, perf measured and closed

Both follow-ups landed on the SAME branch per user instruction:

1. **Package metadata is gone from version checking.** The user was right that
   the contract is manifest-only. `commands/plugin.py:71` seeds
   `build["backend_version"]` unconditionally before overlaying the manifest, so
   `build.backend_version` is always present and the fallback I had left was
   dead code that reintroduced the metadata dependency. The client now reads
   `build.backend_version` only; an absent value reports "did not report a build
   identity" rather than guessing, and an empty expectation in our own bundle
   claims no mismatch. Two pre-existing tests encoded the old metadata behavior
   and were updated to send real-shaped payloads; two new cases pin the field
   scenario (stale 0.4.3 metadata alongside correct build identity).

2. **Perf: measured, and the bottleneck is NOT Incurator.** `agy --print` costs
   8.2–12.2 s for a one-word answer and is flat across model and effort, while
   the CLI binary starts in 0.29 s, an Incurator backend round-trip is 0.20 s,
   and a warm local Ollama round-trip is 0.26–0.32 s. So it is the Antigravity
   service handshake. The PDF reference-fetch optimization was therefore
   REJECTED: it is ≤0.6 s of a ~13 s action, and `pdfReferenceContext.test.ts:80`
   proves the common case already issues one fetch, so batching would quadruple
   backend work on the common path to help only the rare one. Neither slow path
   makes a redundant provider call (CLI providers get no local tools;
   Convert-to-LaTeX resolves straight to `vision_model`). Shipped instead:
   elapsed-time feedback in the popover (PLUGIN_SCHEMA §1.4.3), because a frozen
   "Thinking…" for 8–12 s is indistinguishable from a hang — the exact ambiguity
   that made a real crash read as slowness earlier today. The remaining lever is
   provider choice (~30× gap), not code.

Gates after these changes: plugin Vitest 867/867 across 79 files, tsc clean,
production build clean, Ruff clean, spec/version sync 10/10. Backend pytest was
still running at write time.

## Immediate Next Action

Push the metadata + perf work to PR #111 and verify CI. Then, per the user's
sequencing, resume the Arena system-defect diagnosis
(`.agents/plans/system_defect_audit_arena/`) — two prior runs died on provider
usage limits, so restart it lean (targeted spec line ranges, tool-call budgets)
and expect to author the consolidated ROADMAP 1+2 plan from its output.
