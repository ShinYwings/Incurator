# Active Relay State

**STATUS: IDLE.**

No active implementation branch is in progress.

Last completed release:
- v0.28.3 merged to `master` on 2026-06-29 via PR #73:
  https://github.com/ShinYwings/Incurator/pull/73

Current repository state:
- Branch: `master`
- Working tree: clean at `origin/master` before this relay cleanup
- `.agents/USER_REPORT.md`: empty
- Roadmap queue: no urgent hotfixes; continue the System Stability Overhaul
  before lower-priority roadmap items.

Immediate next action:
- Select the next roadmap item. Likely next stability work: remaining S2
  broad-except cleanup in MCP/plugin API surfaces, CM-1/PL-1 god-file
  decomposition, or remaining G17 S3 cleanup.

### Update (2026-06-30, Codex)

Handled side-task for `/Users/shin/shinywings/second_brain`: updated outdated
COLMAP-free GS workspace configuration to current dynamic curation/KRS rules.
Touched only vault/workspace configuration files, not Incurator code.
Validation performed with local repo `.venv/bin/wiki`: `wiki migrate --dry-run`
reported schema v1 current and no stale Collection files; `curate.yml` parsed
and compiled with no validation errors; workspace rule sync check passed; EXH /
`curator_curate_workspace` / `wiki curate` legacy markers were removed from the
target configuration files.

### Update (2026-07-01, Codex)

Active branch: `fix/workspace-template-hygiene`.

Handled workspace/vault template hygiene bugfix for generated workspace rules:
removed Incurator repo-local workflow references from managed `AGENTS.md` /
`CLAUDE.md` templates, corrected `curate.yml` vault-root guidance, made workspace
provisioning install only the selected/detected top-level agent rule file, and
normalized Codex MCP detection to the workspace-agent slug `codex`.

Validation completed: `scripts/backend-check ruff`, `scripts/backend-check
mypy`, `scripts/backend-check pytest` (1142 passed, 6 skipped, 5 xfailed),
`npx vitest run -c ./plugin/vitest.config.ts` (646 passed), direct temp-vault
`wiki init` + `wiki workspace init --agent codex` smoke, `VAULT_ROOT=testbed`
workspace-init smoke, and `--agent antigravity` alias smoke. Temporary MCP
`VAULT_ROOT` written during smoke validation was restored to
`/Users/shin/shinywings/second_brain`.

### Update (2026-07-01, Claude — device-portable vault_root)

Extended the same `fix/workspace-template-hygiene` branch (still 0.28.4) to fix
the absolute-path portability issue the user raised for multi-device use:

- **Finding — `vault init` is already portable.** No synced file hardcodes the
  vault's absolute path; the vault is discovered by location (`find_wiki_root`),
  and the only absolute marker (`last_root`) lives in the device-local global
  cache. The MCP `.claude/settings.json` / printed snippet keep absolute
  `VAULT_ROOT`/`WORKSPACE_PATH` *deliberately* — `.claude/` is `.stignore`'d
  (device-local, regenerated per device), so absolute is correct there.
- **Fix — the one synced absolute leak was `curate.yml.vault_root`.**
  `provisioner.portable_vault_root()` now writes it relative to the workspace dir
  (`../..` in-vault; `../<vault>` for outside-vault workspaces) via
  `os.path.relpath`, absolute fallback only for cross-drive. Healing preserves any
  value (relative/absolute) that already resolves to the active vault and only
  rewrites genuinely-stale ones. `mcp_server._resolve_paths` resolves a relative
  `vault_root` against the workspace dir, not the process CWD. `VAULT_ROOT` env
  remains authoritative.
- Docs: USER_GUIDE(+KR), MCP_USER_GUIDE(+KR), SYSTEM_BEHAVIOR §16.0, CHANGELOG,
  curate-template.yml comment. Tests: +7 in `test_workspace_hygiene.py`.

Validation: `scripts/backend-check ruff` (clean), `mypy` (clean),
`scripts/backend-check pytest` (1149 passed, 6 skipped, 5 xfailed), and a real
temp-vault `wiki init --no-interactive` + in-vault/outside-vault `wiki workspace
init` smoke confirming `../..` and `../myvault` are written and resolve back to
the vault with no absolute-path leak.
