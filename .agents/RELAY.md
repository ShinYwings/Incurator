# RELAY

**Branch:** `hotfix/setup-npm-audit`

## Next Action
**Current hotfix:** `./setup.sh` npm audit failure. Vitest 4.1.7 triggered npm
10.9 Arborist's optional-peer `edgesOut` crash; the branch pins 4.1.11,
declares the CodeMirror imports directly, and uses `--legacy-peer-deps` for the
plugin install/audit commands. Full setup with model/alias provisioning skipped
and plugin build, audit, backend install all completed. After the user changed
accounts, live `agy` validation succeeded: `gemini-3.8-flash` resolved to its
medium variant and answered in 3.0s; Incurator MCP returned v0.82.1 in 3.5s;
`read_file(*)` passed while retired/path-scoped rules were denied; `command(wiki)`
reached native run_command while an absolute path was correctly denied. The
earlier account's `RESOURCE_EXHAUSTED (code 429): Individual quota reached` was
provider evidence, not a local usage verdict, and the watcher stopped it in
5.8s.

E4 remains paused: the original untracked draft at
`.agents/drafts/e4_agy_shell_out.md` is preserved and untouched.

### Update (2026-09-11, Codex — hotfix shipped)

v0.82.0 merged as PR #201 / 4083923e; current branch `master`.
Backend 1964 and plugin 1284 local tests passed; final Linux CI, type checks,
lint and build passed. Codex independent review findings are fixed. User waived
Claude validation after the prescribed skill invocation failed authentication.
Plans/Arena remain in merge history and are removed from the active workspace.
No production vault/DB/snapshot edits; original untracked E4 draft preserved.
The agy provider-refusal/denied-shell live validation is now closed in ROADMAP
I4 after the account switch; the earlier quota message remains provider evidence,
not proof of local account depletion. E4 remains paused: the user requested this
hotfix only. No active implementation remains here.
