# v0.35.0 Model Catalogue Refresh Evidence Ledger

Date: 2026-07-19

## Rollback Anchor

- Working branch: `release/v0.35.0`
- Current branch head before model-refresh planning: `c9f5726`
- Current master before hotfix merge: `bcc4ac2`
- Required predecessor: PR #86 (`hotfix/v0.34.1-knowledge-sync-loop`), head
  `1a71771`; GitHub CI passed and the PR is mergeable/ready for review.

## Current Worktree Reality

- Pre-existing user-owned modification: `plugin/package-lock.json` changes the
  lockfile version from 0.33.0 to 0.34.0.
- Planning and later implementation must preserve that change and reconcile it
  deliberately during the v0.35.0 version bump.
- No model implementation file is modified at planning start.

## Runtime Evidence

- `codex-cli 0.139.0`; cache fetched `2026-07-19T07:50:55Z`.
- Visible Codex entries: Sol, Terra, Luna, GPT-5.5. Effective context: 272K.
- Sol/Terra support through `ultra`; Luna through `max`; GPT-5.5 through
  `xhigh`.
- `claude` version `2.1.175`; help accepts efforts
  `low|medium|high|xhigh|max` and current aliases/full IDs such as
  `claude-fable-5`.
- Anthropic official docs confirm effort support for Fable 5, Opus 4.8, and
  Sonnet 4.6; Haiku 4.5 has no effort dimension.

## Code/Document Divergence Baseline

- Backend default and guide examples still select GPT-5.5.
- Codex TypeScript/spec/guide effort unions stop at `xhigh`.
- Plugin schema requires nonexistent `supportsThinking`.
- Model transition behavior differs among settings, sidebar, dashboard, and
  load migration.
- Claude plugin command always emits `--effort`.
- Plugin context clipping uses characters although catalogue context is shown
  as tokens.

## Pre-Implementation Gates

- Merge PR #86, update `master`, and rebase/update `release/v0.35.0` from the
  merged master without overwriting the user-owned lockfile edit.
- Capture a fresh test baseline after that branch update.
- Stop if the installed CLI catalogue changes again before implementation; the
  locked tables must be revalidated rather than guessed.
