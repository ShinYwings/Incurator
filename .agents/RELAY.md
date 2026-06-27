# Active Relay State

**STATUS: Phase B v0.27.3 shipped to PR — awaiting merge.**

**Current branch**: `fix/phase-b-plugin-rest-cleanup`

**Last refreshed**: 2026-06-27 by Claude Code.

---

## Goal

System Stability Overhaul Phase B: G17 plugin-runtime cleanup + G18/G19
docs-code parity. Complete and validated; shipped as **v0.27.3** in PR #62.

- PR: https://github.com/ShinYwings/Incurator/pull/62
- Master plan: `.agents/plans/01_system_stability_overhaul.md`
- Evidence ledger: `.agents/plans/01_roadmap_evidence.md`

## Progress Status

- All G17 (G17-1/2/3/4/5/6/8/9/11) and G18/G19 items implemented, tested,
  documented, and version-bumped to 0.27.3 (all three manifests + CHANGELOG).
- Validation green: backend pytest (1090 passed / 6 skipped / 5 xfailed),
  ruff, mypy, vitest (611 tests), `tsc --noEmit`, `git diff --check`.
- Committed and pushed; PR #62 open against `master`.
- Post-push `/code-review` (high) found 4 plugin bugs; all fixed on this branch
  (commit `0470728`) with tests: Ollama custom-model wipe in
  `migrateUnavailableModelDefaults`, fragile `---` frontmatter-fence detection
  and empty-frontmatter double-fence in `stampZoteroProfile`, and a new-profile
  name trim mismatch. Full plugin suite green (615 tests), `tsc` clean.

## Immediate Next Action

- Human: review and merge PR #62.
- After merge, start the next Phase B batch on a **fresh branch** (do not reuse
  this one): G17 S3 cleanup (citekey resolution, legacy `imageFolder`
  migration), then the larger S2 architectural items — XC-1 broad-except
  narrowing and CM-1/PL-1/DB-2 god-file decomposition. These warrant their own
  plan + version bump.
