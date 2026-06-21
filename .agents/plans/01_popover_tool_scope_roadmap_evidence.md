# Evidence Ledger — v0.23.0 Popover Tool Scope & CLI Sandbox

Date: 2026-06-21 | Branch: `feature/popover-tool-scope`

## Rollback Anchor
- HEAD: `51ae4f8` (current popover-tool-scope branch tip; contains merged v0.22.0).
- Plugin-only change set → rollback = revert the feature merge.

## Current Repository Reality (verified by reading code)

| Claim | Evidence |
|---|---|
| Popover injects ZERO MCP tools (HTTP) — v0.19.0 | `quickQueryPopover.ts:468` `{toolPolicy:"none"}`; `llmClient.ts:678` `shouldInjectMcpTools`; `:38` returns false for "none" |
| Prompts unified (no duplication) — v0.19.0 | `quickQueryContext.ts:9,145,160` consumes shared `promptRegistry.ts` |
| `toolPolicy` does NOT reach the CLI path (the gap) | `streamChatViaCli`/`buildCliCommand` `llmClient.ts:1826` take no toolPolicy |
| agy runs unrestricted | `llmClient.ts:1833` `--dangerously-skip-permissions` + `:1837-1838` `*_TRUST_WORKSPACE=true` |
| claude runs with default tools, no scoping | `llmClient.ts:1845-1855` (no `--add-dir`/`--disallowedTools`) |
| codex read-only (no writes, but reads filesystem) | `llmClient.ts:1879-1881` `--sandbox read-only` |
| Incurator MCP server exposes NO fs/exec tool | `mcp_server.py` tools are DAG/DB queries only → exploit is CLI-native, not Incurator MCP |
| CLI scoping flags (VERIFIED on installed versions) | `agy 1.0.10`: `--sandbox`, `--add-dir`, `--cd`. `claude 2.1.175`: `--add-dir`, `--allowedTools`, `--disallowedTools`, `--permission-mode`, `--tools` (`--tools ""` disables all). `codex 0.135`: `-s read-only\|workspace-write`, `--add-dir <DIR>`, `-C/--cd <DIR>`. |
| claude has NO deny-without-prompt dir sandbox | `--add-dir` only ADDS allowed dirs; `--permission-mode` is prompt-or-bypass → claude controlled via tool surface (`--tools ""` / `--disallowedTools`), keeping only DB-scoped MCP curator tools |
| Allowed-roots sources | `LLMClient.vaultRoot` (`llmClient.ts:539`); `settings.zoteroBasePath` (+ `storage/`) |

## Second review round corrections (2026-06-21, verified)
- claude flags are NOT hallucinated (2.1.175 has them); claude controlled via tool
  surface since it lacks a deny-sandbox. codex uses `--add-dir`+`--cd` (not `-c` TOML).
  `allowedRoots()` filters empty/undefined before resolve; never `--add-dir ""`.

## P0 Empirical Validation RESULTS (2026-06-21) — assumption overturned

Live tests (isolated /tmp "vault", out-of-bounds secret + write target):

- **agy `--sandbox` — FAILS to sandbox.**
  - Out-of-bounds READ: read `/tmp/pts_outside_secret.txt` via `view_file`, returned the secret.
  - Shell exec + WRITE: ran `echo … > /tmp/pts_sidefx_created.txt` and the file WAS created.
  - agy ignores spawn cwd ("Shell cwd was reset to <repo>"). agy has NO `--tools`/
    `--disallowedTools`/`--permission-mode` — only `--add-dir`, `--sandbox` (ineffective
    for file/shell tools), `--dangerously-skip-permissions`. → **agy cannot be
    sandboxed via its flags.** (This is the user's DEFAULT provider.)
- **claude `--tools ""` — WORKS.** It announced a Bash call but the tool did NOT
  execute; no file created. Tool-free confirmed. `--disallowedTools "Bash …"` similarly
  removes specific native tools for the sidechat.
- **codex `--sandbox read-only`** — live test inconclusive (hit usage limit), but it is
  codex's documented write-blocker and created no file. Re-validate in P4.

**Conclusion (STOP gate):** the per-CLI-flag approach secures claude (and likely
codex) but NOT agy — agy executes shell/file ops regardless of `--sandbox`. Decision
required before P1.

## P0 round 2 — OS-level sandbox VALIDATED (user chose Hybrid; macOS + Linux, no Windows)

macOS `sandbox-exec` deterministic seatbelt tests (plain child processes):
- Write to a DENIED subpath → `Operation not permitted`, no file → **CONTAINED**.
- **Nested** child (`sh -c "sh -c 'write'"`) → still blocked → **CONTAINED** (agy spawns
  nested shells, so this is the load-bearing case).
- Deny-by-default profile (`(deny file-write*)` + `(allow file-write* (subpath <root>))`)
  → in-root write OK, out-of-root write blocked → **CONTAINED**.
- Clean deny ("Operation not permitted"), no hang.

→ **Hybrid is viable.** The OS seatbelt contains agy's writes/exec regardless of agy's
broken `--sandbox`. Design:
- **macOS**: wrap the CLI in `sandbox-exec -f <generated .sb>`; profile = deny
  `file-write*` + `process-exec*` outside the allowed roots, BUT allow the CLI's
  necessary runtime write dirs (`$TMPDIR`/`/private/var/folders`, home config/cache).
  Reads allowed (the security-critical harm is writes/exec/creation; read-restriction
  risks breaking the CLI and is a stretch goal).
- **Linux**: wrap in `bwrap` (bubblewrap): `--ro-bind / /` + `--bind <root> <root>` per
  allowed root (+ `--dev /dev --proc /proc --tmpfs /tmp`-style). If `bwrap` is absent →
  detect and show a one-line install hint (`apt/dnf install bubblewrap`); until then,
  refuse the agentic CLI for tool-sensitive surfaces.
- **Automatic** (user requirement): the plugin generates the profile/binds from
  `allowedRoots()` and prepends the wrapper in `buildCliCommand`. No manual user setup
  (macOS built-in; Linux one-time `bwrap` install if missing).
- **Residual caveat**: agy has no tool-free mode, so even sandboxed it may READ within
  the sandbox during a popover query (no side effects, but not strictly "zero tool
  calls"). Strict zero-tool popover → use Ollama/claude/codex. Documented.
- claude (`--tools ""`/`--disallowedTools`) + codex (`--sandbox`) keep their flag
  control as the primary mechanism; the OS sandbox is defense-in-depth on top.

## P0 Empirical Validation (original gate description)
For each installed CLI (agy 1.0.10, claude 2.1.x, codex 0.135.x):
1. Out-of-bounds op (e.g. read `/etc/hosts` or write outside vault) under the chosen
   restricted flags → MUST deny quickly, MUST NOT prompt/hang in `-p`/`exec`.
2. Legit op inside the vault + a Zotero PDF read → MUST still succeed.
3. Record exact flags + CLI versions. A provider that prompts → tool-free fallback.

## Decisions captured from user (2026-06-21)
- Scope (a): both popover tool-disable AND sidechat path-sandboxing.
- agy `--dangerously-skip-permissions` was a hang workaround; replace with
  `--sandbox` + `--add-dir` (deny-not-prompt). No interactive-approval UI this round.
