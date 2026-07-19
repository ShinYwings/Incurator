# RELAY - v0.36.2 Fail-Closed Correctness Hardening

## Goal

Fix verified false-success and scope-bypass bugs in cross-device sync and
workspace curation policy resolution. System behavior correctness, code/docs
parity, and reproducible failure handling take priority over refactoring volume.

## Plan Reference

- Master: `.agents/plans/02_fail_closed_correctness.md`
- Evidence: `.agents/plans/02_roadmap_evidence.md`
- Domain analysis: `.agents/plans/A_sync_fail_closed.md`,
  `.agents/plans/B_curation_policy_fail_closed.md`
- Arena: `.agents/plans/fail_closed_correctness_arena/`

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
- [ ] Await user approval before docs/TDD/application changes.

## Critical Context / Blockers

- No technical blocker.
- Workflow blocker by design: substantial control-flow changes require plan
  approval before coding.
- No production vault/DB/config was changed; failure injection used temporary
  directories only.
- Active validation scenario is `tests/scenarios/gaussian_splatting`; existing
  `testbed/` is present.

## Immediate Next Action

After user approval, execute P1 docs-first, then P2 failing tests, followed by
P3/P4 implementation and full/testbed validation. Do not change application
logic before approval.
