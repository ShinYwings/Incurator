# RELAY — ACTIVE

## Goal

Ship v0.39.3 as the P6 durable-state integrity patch: preserve corrupt
session/secret bytes, block destructive ordinary saves, serialize atomic
session/secret/config writes, recursively redact runtime credentials, and prove
concurrent/interrupted writes plus synced-session merges.

## Plan Reference

- Branch: `release/v0.39.3`
- Master plan: `.agents/plans/02_v032_regression_audit.md` (P7 next; P6 evidence retained)
- Evidence ledger: `.agents/plans/02_v032_regression_evidence.md`
- Completed domain analysis is preserved in Git history.

## Analysis & Reasoning

- P6 addresses confirmed F14–F16 from the v0.32.0+ release-chain audit.
- The batch is backward-compatible integrity hardening with no schema or public
  contract change, so the correct version is patch `0.39.3`.
- Root-cause fixes must distinguish missing, valid, corrupt, and unreadable
  state rather than recovering through defaults that can later overwrite bytes.
- Production `second_brain` and any active testbed remain out of scope; use
  deterministic tests and isolated disposable fixtures.

## Progress Status

- PR #103 / v0.39.2 merged as `c319e6b`; local `master` was fast-forwarded.
- Created `release/v0.39.3` from clean merged relay-reset head `346fcdb`.
- Implemented typed fail-closed canonical session/profile reads, serialized
  atomic plugin saves, locked atomic secret/config mutation, and recursive
  runtime credential redaction.
- Added deterministic corruption, interruption, concurrency, synced-session,
  and recursive-redaction proofs; updated paired guides and static specs.
- Final release-head gates passed: backend 1,382 passed / 6 skipped /
  4 xfailed, Ruff and mypy clean, plugin build clean, Vitest 749 passed.
- Version/changelog closure is prepared for patch `0.39.3`; P6 is removed from
  the active roadmap and P7 is next.
- Release commit `272c7fa` was pushed and draft PR #104 targets `master`:
  `https://github.com/ShinYwings/Incurator/pull/104`.

## Critical Context / Blockers

- P6 required no schema or public contract change.
- Preserve corrupt/unreadable source bytes; do not test against live user state.
- Do not mutate production `second_brain` or an active testbed.

## Immediate Next Action

1. Wait for GitHub CI on the latest delivery head and address any failure.
2. After PR #104 merges, follow the documented IDLE relay-reset procedure.
