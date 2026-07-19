# RELAY - v0.36.2 Fail-Closed Correctness Hardening

## Goal

Fix verified false-success and scope-bypass bugs in cross-device sync and
workspace curation policy resolution. System behavior correctness, code/docs
parity, and reproducible failure handling take priority over refactoring volume.

## Plan Reference

- Completed v0.36.2 plan artifacts are deleted from the active workspace during
  release closure. Planning is preserved from commit `3a6c3c2`; final validation
  evidence is preserved in commit `ada48f1`.

## Analysis & Reasoning

- PR #89 merged as `06e69058def994d4091a77790b2eeaf162da5393`.
- Branch `release/v0.36.2` was created directly from updated `master`.
- Six failure classes are reproduced: corrupt sync state resets identity; conflict
  import/archive can report false success; tombstone delete failure propagates a
  false deletion; malformed YAML defaults unrestricted; wrong-shaped source
  scope compiles unrestricted; invalid semantic KRS is persisted by MCP/plugin
  plan surfaces.
- Missing state and missing workspace policy remain legitimate initialization
  defaults; only an existing invalid artifact fails closed.
- Per-file imports stay transactional/idempotent. A later failure may follow an
  earlier committed peer, but the overall pass must fail visibly and retry safely.
- Composite-PK tombstone encoding is a separate schema-contract issue and is
  queued rather than guessed in this patch.

## Progress Status

- [x] PR #89 merged and local master updated.
- [x] Created `release/v0.36.2` at merge commit `06e6905`.
- [x] Reproduced all four queued P0 failures on current code.
- [x] Found and reproduced the additional wrong-shaped source-scope bypass.
- [x] Found and reproduced invalid MCP/plugin curation-plan persistence: MCP
  returns success and plugin exits zero after writing invalid normalized policy.
- [x] Confirmed all current scenario/testbed `curate.yml` files satisfy the
  proposed stricter source-pattern shape.
- [x] Read current code, specs, paired guides, tests, and historical sync plans.
- [x] Relevant pre-change baseline: 95 passed in 425.76s.
- [x] Authored Arena proposal, red-team critique, defense, domain analyses,
  Evidence Ledger, and Master Plan.
- [x] User approved the v0.36.2 Master Plan on 2026-07-20.
- [x] P1 docs/spec contracts updated (English first, then Korean pairs).
- [x] P2 regression tests added; pre-fix run produced the expected 26 failures
  with 125 passes, all on the reproduced false-success paths.
- [x] P3 sync fail-closed implementation complete; focused backend tests pass
  (56) and the plugin client suite passes (33).
- [x] P4 shared validated curation-policy boundary complete; source-scope shapes,
  semantic validation, I/O probes, and load/hash disappearance fail closed before
  query work or plan persistence.
- [x] Combined focused state/scope suites pass (86); query orchestrator passes
  (14); new public-query/MCP/plugin plan tests pass.
- [x] P5 backend CI passes: 1259 passed, 6 skipped, 5 xfailed; Ruff and Mypy pass.
- [x] P5 plugin CI passes: 66 files / 689 tests; TypeScript and production build pass.
- [x] P5 gaussian_splatting passes status/reindex/incremental-sync/lint (100/100),
  Reference Mode preservation, and repeated quiescent autosync checks.
- [x] v0.36.2 version/spec/docs consistency passes (16 tests).
- [ ] P6 release commit, push, and PR creation in progress.

## Critical Context / Blockers

- External validation blocker only: Antigravity CLI returned no output during
  answer JSON repair after KRS loading/retrieval succeeded. Full logical sync and
  final answer synthesis were therefore not claimed; lower-level gates passed.
- The newly observed full-traceback query UX is queued in ROADMAP for a separate
  plan rather than mixed into this patch.
- No workflow blocker; the implementation plan is approved.
- No production vault/DB/config was changed; only temporary fixtures and the
  repository `testbed/` were used.
- Active validation scenario is `tests/scenarios/gaussian_splatting`; existing
  `testbed/` is present.

## Immediate Next Action

Create `chore(release): v0.36.2`, push `release/v0.36.2`, and open the release PR.
