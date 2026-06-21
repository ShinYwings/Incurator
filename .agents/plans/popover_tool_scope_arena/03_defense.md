# Defense / Synthesis

Date: 2026-06-21 | Agent Persona: system_synthesizer (Closer)

All red-team points accepted. Resolutions folded into the Master Plan:

- **R1 (no-hang must be proven)** → P0 is a HARD GATE: empirically run each installed
  CLI (`agy --sandbox`, `claude` with the chosen non-bypass mode, `codex` scoped)
  with a deliberately out-of-bounds op and confirm it DENIES quickly, does NOT prompt
  or hang. If a CLI prompts in `-p`, that provider falls back to the tool-free path
  (R3) rather than skip-all. No ship without this evidence.
- **R3 (popover tool-free by construction)** → the popover does NOT rely on a sandbox
  alone: for CLI providers it uses a tool-free invocation (all tools disallowed /
  non-agentic), with the sandbox as a second layer. Belt and suspenders.
- **R2 (codex read scope)** → popover codex = tool-free (R3); sidechat codex =
  `workspace-write` scoped to the allowed roots, not blanket read-only.
- **R4 (cwd)** → CLI subprocesses run with `cwd` set to the vault root (an allowed
  root), never the repo/plugin dir; allowed roots passed via `--add-dir`.
- **R5 (paths)** → allowed roots are realpath-resolved before being passed; the CLI
  sandbox is the enforcing boundary, our allowlist is its input. Trust model
  documented in the spec/guide.
- **R6 (external MCP servers)** → explicitly OUT OF SCOPE and documented: external
  `mcpServers` are the user's own trust boundary. (Future: a setting to drop them for
  ephemeral surfaces.) This milestone sandboxes the CLI-native tools + Incurator MCP.
- **R7 (Zotero roots)** → allowed roots include `settings.zoteroBasePath` and its
  `storage/` subdir; P0 validates a legit Zotero PDF read still works under the
  sandbox. If insufficient, query the backend's resolved Zotero roots.

Consensus: the fix is a toolPolicy-aware `buildCliCommand` that (popover) goes
tool-free + sandboxed and (sidechat) scopes tools to realpath-resolved allowed roots
via each CLI's native sandbox/add-dir flags — never `--dangerously-skip-permissions`.
P0 empirical validation is the release gate. Proceed to Master Plan.

## Second review round (2026-06-21) — flags verified against installed CLIs

- **claude "flag hallucination / instant crash"** — REJECTED on evidence: claude
  2.1.175 HAS `--add-dir`, `--allowedTools`, `--disallowedTools`, `--permission-mode`,
  AND `--tools` (`--tools ""` disables all). No crash. BUT the underlying concern is
  ACCEPTED: claude has no deny-without-prompt directory sandbox, so claude is
  controlled by its TOOL SURFACE — popover `--tools ""`; sidechat disables all native
  tools and keeps only the DB-scoped MCP curator tools (the plugin edit-loop handles
  vault edits). No hang, no fs/shell escape.
- **codex `-c` TOML complexity** — ACCEPTED: codex HAS `--add-dir <DIR>` + `--cd <DIR>`
  (verified). Use `--sandbox workspace-write` + `--cd <vault>` + repeated `--add-dir`,
  matching agy — not the fragile `-c sandbox_workspace_write.roots` array.
- **Empty/null roots escalation** — ACCEPTED: `allowedRoots()` drops empty/undefined
  BEFORE resolution; never passes `--add-dir ""` (would default to cwd/`/`).
- P0 still validates deny-not-hang + legit-op-works on the installed CLI versions.
