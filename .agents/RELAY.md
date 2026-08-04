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

## Immediate Next Action

Await the PR #111 merge. Then instrument the popover and Convert-to-LaTeX paths
to split plugin/backend/provider time, and only then propose the optimization.
