# Sidechat Local Git History (drop `gh` dependency) Plan

## Context
Triaged from USER_REPORT on 2026-06-11. The user questions why GitHub CLI (`gh`)
is a required dependency at all, since the vault is already managed by local
`.git`, and version-control operations (commit/push) are done by a separate
Obsidian plugin that does not need `gh`.

## Observed Request (verbatim intent to preserve)
- "Why do I need to install `gh`? It's already managed by `.git`." The intended
  use was: in the sidechat, reference the **history of files inside the vault**
  via local git — e.g. "How did I write this before?", "I think there was a
  record of this, but I can't see it now", "I want to recover what I wrote a few
  hours ago."
- Commit/push (version control) is handled directly by another plugin that does
  not require `gh`.

## Requirements
1. **Audit the `gh` dependency**: find where `gh` is required/invoked and
   determine whether any feature genuinely needs the GitHub API vs. plain local
   `git`. The history-reference use case needs only local `git log`/`git show`.
2. **Remove the hard `gh` requirement** for local-history features; fall back to
   (or exclusively use) local `git`.
3. **Sidechat file-history reference feature**: let the agent answer
   history/recovery questions about vault files using local git history
   (`git log -- <file>`, `git show <rev>:<file>`), surfacing prior versions for
   recovery.

## Files Likely Involved
- Wherever `gh` is checked/required (setup scripts, plugin preflight, docs)
- Sidechat tool/command layer (new local-git history tool)

## Notes
- Distinguish "needs GitHub API" (PRs/issues) from "needs local git history" —
  only remove `gh` where the latter suffices.
- New agent tool likely needs both `.test.ts` and/or `pytest` coverage.
