# RELAY

**Branch:** `codex/e4-denied-envelope`

## Goal
E4: make current agy no-output permission denials reach graph batch retry.

## Plan Reference
`.agents/plans/06_e4_denied_envelope.md`; evidence in `06_e4_roadmap_evidence.md`.

## Analysis & Reasoning
The August draft is stale: retry and durable resume already exist. agy 1.2.0 now returns exit 0 / SUCCESS / empty response / denied_actions on command denial; the adapter returns empty text and bypasses graph exception retry. Live exact graph contract succeeds in 13.5 seconds, 2 turns. No permission widening is needed.

## Progress Status
Arena proposals and cross-critique complete. Docs, TDD and provider boundary fix next. Current merged release is v0.82.4 (PR #204); target patch v0.82.5.

## Critical Context / Blockers
Do not reindex or mutate user data. Existing E4 draft was user-owned untracked content. Keep sandbox, graph cache, retry limit and prompt contract unchanged. Broad retry classification remains separate.

## Immediate Next Action
Write provider/graph envelope regressions before implementation, then live checks, review and release.
