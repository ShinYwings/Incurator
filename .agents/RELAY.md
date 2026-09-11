# RELAY

**Branch:** `codex/e4-denied-envelope`

## Goal
E4: normalize current agy denied/no-answer envelopes so graph batch retry runs.

## Plan Reference
`.agents/plans/06_e4_denied_envelope.md`; evidence in `06_e4_roadmap_evidence.md`.
PR: https://github.com/ShinYwings/Incurator/pull/205 (OPEN, target v0.82.5).

## Analysis & Reasoning
agy 1.2.0 can return exit 0 / SUCCESS / blank response / denied_actions on command refusal. The backend returned empty text and bypassed graph exception retry. Fix raises existing AntigravityCliError before parsing. Graph cache, retry cap, permissions and extraction schema remain unchanged. Earlier direct live graph probe succeeded in 13.5 s; forced command reproduced denial in 8.38 s.

## Progress Status
Implementation, regressions, English/Korean docs and v0.82.5 manifests/changelog committed and pushed. Local checks: 1980 backend passed, 6 skipped, 4 xfailed; 1286 plugin passed, 3 skipped; Ruff, mypy, TypeScript and production build passed. Independent peer review found no actionable defect.

## Critical Context / Blockers
Required `/code-review:code-review 205` was invoked through installed Claude CLI but failed before review: OAuth session expired and could not be refreshed. No login retry performed. Independent review is not recorded as a substitute; PR remains unmerged pending required review or explicit user waiver. Current merged release remains v0.82.4.

User explicitly requested removing tests that trigger agy login. Removed the new live graph test, existing backend live structured-output test, and global INCURATOR_LIVE_AGY spawn-guard bypass. Root cause: pytest isolates HOME, so real agy cannot see existing login. DO NOT run agy from pytest or retry login. Further validation uses captured-response replay. No agy processes remained after timeout. No post-change real provider validation claimed.

Original untracked `.agents/drafts/e4_agy_shell_out.md` is preserved. No user-vault reindex, migration, or production-data mutation. Plans stay active until merge. E7 is recorded shipped by prior PR #204.

## Immediate Next Action
Finish the required review once available (do not automatically authenticate), verify latest PR CI, then merge and prune the finished branch, retire implemented plans, and update roadmap/relay. Do not restart E4 research or repeat live agy calls.

### Update (2026-09-11, Codex)

Synchronized `AGENTS.md` with the latest `CLAUDE.md` shared body. Removed the
stale Antigravity/Gemini exclusion and shortened rule set from `AGENTS.md`,
copied the current detailed workflow, architecture, and development guidance,
and added a byte-for-byte shared-body invariant to both files. Workspace
hygiene tests passed (18/18); the synchronization commit is on `master` and
that commit was merged into and pushed with this E4 branch. The untracked E4
briefing draft remains untouched.
