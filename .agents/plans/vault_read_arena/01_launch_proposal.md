# CLI Launch Proposal: One Native Codex Sandbox
Date: 2026-09-21 | Agent Persona: CLI Runtime Engineer

## 1. Core Logic & Implementation

The reported failure is a process-start failure, not a missing vault path or a
request that needs the user to grant read access. The active implementation wraps
every Codex invocation in the plugin's write-denying macOS Seatbelt profile, then
asks Codex to apply its own `read-only` or `workspace-write` Seatbelt profile when
executing tools. Parent reproduced the exact `sandbox_apply: Operation not
permitted` failure with nested `sandbox-exec` and the outer write denial. Removing
the outer wrapper or its write denial permits that minimal read command.

Use Codex's native sandbox as the sole command-execution sandbox for Codex-backed
CLI launches. Keep the plugin wrapper for providers that require it. Do not modify
the user's global Codex configuration, grant full access, enable automatic retry
without a sandbox, or ask a user permission question to execute a vault read.

The native launch must retain the existing per-surface policy:

- Sidechat uses `--sandbox workspace-write` and grants only realpath-resolved
  `sandboxWriteRoots()` through Codex's `--add-dir`, plus the existing scoped chat
  image directory when necessary. The actual cwd is the plugin's CLI cache, so
  Codex's implicit writable cwd remains an operational directory.
- Ephemeral surfaces keep `--sandbox read-only` with no vault write grants. Their
  public tool/edit contract remains unchanged.
- Pin `approval_policy="never"` per invocation. A headless read does not need a
  permission dialog; a prohibited write must fail instead of requesting an
  escalation.
- Pin `sandbox_workspace_write.writable_roots=[]` per invocation before adding
  the plugin-owned explicit roots. Otherwise removing the outer wrapper exposes
  arbitrary additional roots inherited from user configuration.
- Pin `sandbox_workspace_write.exclude_slash_tmp=true`. Preserve the existing
  explicit `TMPDIR`/`TEMP`/`TMP` under the repository CLI cache; do not grant host
  `/tmp` as a new side effect of removing the wrapper. Confirm the generated
  native state actually uses these intended roots before shipping.

Codex's installed `0.155.1` help explicitly describes `--add-dir` as adding
directories that are **writable**. The shared `allowedRoots()` currently contains
vault, Zotero, and Zotero storage and is described as a visibility list. That
description is false for Codex: the outer wrapper is the only thing currently
preventing Zotero writes. Therefore bypassing the wrapper while retaining the
shared `addDirs` would create a concrete data-corruption permission regression.
The Codex branch must construct its own write-root arguments and omit Zotero.
Native default reads already include these external reference files, so omitting
them from writable roots does not prevent reference reading.

Keep the change in the existing command-construction path. A new global
configuration option, compatibility adapter, retry path, or filesystem tool
implementation is unnecessary for this incident. Comments must distinguish the
Codex WRITE roots from other providers' visibility/read-root arguments.

### Measured evidence and remaining qualification

- Installed executable is `/Users/shin/.nvm/versions/node/v22.14.0/bin/codex`,
  reporting `codex-cli 0.155.1`.
- `codex exec --help` supports `--sandbox read-only|workspace-write|danger-full-access`,
  `-c`, `--profile`, and `--add-dir` as writable directories.
- The user config currently declares `approval_policy="never"` and
  `sandbox_mode="danger-full-access"`; explicit invocation overrides are needed
  so this plugin remains independent of that global choice. No global
  `sandbox_workspace_write` table was observed. The generated
  `obsidian.config.toml` is currently empty and the plugin overwrites it from its
  enabled MCP server list.
- A disposable probe under `.cache/vault-read-probe-hf_160k1` could read both a
  fake vault note and an external reference through `codex sandbox`. It denied
  both attempted writes even with `codex --sandbox workspace-write ... sandbox`.
  Therefore this subcommand does not faithfully apply the `exec` flags and must
  not be presented as proof of native sidechat write behavior. No live LLM or
  production data was used in that probe.
- Final qualification must use a bounded `codex exec` with the actual generated
  plugin argv: read a disposable vault note; read a disposable Zotero-like
  reference; write an allowed disposable vault file; attempt and observe refusal
  for a sibling external write. Include an inherited unrelated writable root in
  a disposable config to prove the per-invocation empty-root override works.
- Repeat the read using `read-only`; a write to the fake vault must then fail.
  Check that the execution records contain no nested Seatbelt initialization
  failure and no user approval request.

The published fix should describe the confirmed Codex launch bug. Claude's
existing text-only `Read` denial and AGY's prompt/tool policy are separate
provider-parity findings and cannot be claimed fixed by this proposal.

## 2. Pros & Cons

Pros: removes the measured incompatible nesting; keeps Codex's native read-only
versus workspace-write distinction; retains direct vault and reference reads;
preserves Zotero write protection for external Zotero roots; needs no user global
configuration edits; keeps AGY/Claude containment unchanged; avoids adding a
second custom Codex permissions implementation.

Cons and boundaries: the native sandbox confines tool execution rather than the
entire Codex parent process. User-configured MCP servers already have a documented
separate trust boundary. Newer named permission profiles may have configuration
precedence that cannot be proved from legacy flag syntax alone; the exact
`exec` probe is a release gate. Removing the outer wrapper must not silently add
inherited writable roots or host `/tmp`. A Zotero directory nested inside an
allowed vault already overlaps the existing outer write grant; this proposal
does not invent a read-only carve-out that the native workspace-write contract
cannot express. If that actual topology is discovered, surface it explicitly
before claiming all Zotero paths are write-protected.
