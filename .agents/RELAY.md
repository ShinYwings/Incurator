# Cross-Agent Relay State

## Status: RELEASE READY

**Branch:** `feature/plan-b-math-distillation`
**Release commit:** `aec5fcb` — `chore(release): v0.8.0`
**Version:** 0.8.0 (pyproject.toml, package.json, manifest.json — all agree)

Plan B (Math Extraction Distillation) and Plan B2 (Compiler Staging Separation)
are fully implemented, reviewed (P8 sequential review PASSED), CI-validated
(P9), version-bumped, and committed (P10).

## CI Results (P9)

- `pytest -q` → 825 passed, 8 xfailed
- `ruff check src/` → clean
- `mypy src/` → 72 pre-existing, 0 introduced
- Plugin `vitest run` → 44 files, 361 tests passed

## Immediate Next Action

**SHIPPED — PR #29 is open and ready to merge.**
<https://github.com/ShinYwings/Incurator/pull/29>

- Branch `feature/plan-b-math-distillation` pushed; local HEAD == remote HEAD ==
  `aec5fcb`. PR #29 (62 files, +7783/-677) is `MERGEABLE` / `CLEAN`; a detailed
  Why/What/How description is set.
- Remote GitHub Actions: **Backend Tests pass, Plugin Tests pass, Version
  Consistency pass.** Re-verified locally on the release HEAD: pytest 825 passed
  / 8 xfailed, ruff clean, mypy 72 (0 introduced), plugin vitest 361 passed.
- **P8 sequential role review (re-run by Claude): PASS** across all 7 personas —
  one trivial doc fix (`list_eligible`→`list_serving` in a docstring, in HEAD);
  pre-existing qmd comments + 6 `ruff tests/` import errors are out of Plan B's
  scope. No new non-trivial finding.

### Update (2026-06-14, Claude) — follow-up review round on `recompile_source`

A reviewer raised 6 findings on the re-publish path. Verified each against code:

- **Findings 1/2 (`_load_unit`/`_load_spans` reuse `conn`):** done — threaded
  `conn` so the reads join the publish transaction (no second connection /
  per-read schema-script overhead inside the open gate). WAL-safe either way;
  this is consistency, not a deadlock fix.
- **Findings 3/4/5 (stale `formula` supports):** REAL latent imprecision.
  `_clear_claim_supports(preserve_formula=True)` kept formula supports
  unconditionally. Tightened: preserve only while the claim still has a formula
  AND the support's span is still declared; else clear it (can't dangle/linger).
  3 TDD oracles (1 preserve, 2 clear) + verified the P5 recovery flow is
  unaffected (`recover_formula` enforces span ∈ declared at creation).
- **Finding 6 (gate audits old state):** the literal "corrupted state commits
  blindly" claim is NOT reachable (validation provably can only *shrink*
  `publish_blocking` — it writes supports only for existing declared spans and
  never emits `linked_evidence`/`omitted_incidental`), so the pre-validation
  gate was already a conservative superset. BUT implemented the structural
  rewrite anyway because it is genuinely better: the gate now runs INSIDE the
  recompile transaction AFTER re-validation (conn-threaded `refresh_support_
  freshness` + `run_compiler_audit` + `_run_publish_gate`), so it audits the
  exact to-be-committed rows AND lets a re-validation HEAL a transiently-dangling
  support instead of being permanently blocked. Existing ghost-unit dangling
  test still blocks (ghost isn't re-validated).

CI after fixes: pytest **828 passed / 8 xfailed** (+3 new), ruff src clean,
mypy 72 (0 introduced), plugin vitest **361 passed**. D2 db.py drift fingerprint
re-armed (`a4e1785d…`→`1afc2c9e…`; transaction plumbing, no ranking path).
Specs updated (SCHEMA §20.5, SYSTEM_BEHAVIOR §26.3) + CHANGELOG. Pushed to PR #29.

The human user's only remaining responsibility is to **review and merge PR #29**.
After merge, truncate this RELAY to an IDLE stub (git log is the history).
