# Critique on the toolPolicy-aware CLI sandbox proposal

Date: 2026-06-21 | Agent Persona: red_teamer (Security Adversary)

## 1. Vulnerabilities & Flaws

### R1 — "Sandbox denies, doesn't hang" is an ASSUMPTION, not verified
The whole no-hang claim rests on each CLI's restricted mode denying cleanly. If
`agy --sandbox` (or claude's non-bypass permission mode) actually PROMPTS for a
blocked op in `-p` mode, the sidechat hangs again — the exact bug we're removing.
This MUST be empirically proven per installed CLI version before shipping, not
assumed from `--help` text.

### R2 — codex `read-only` still allows whole-filesystem READ/SEARCH
The popover's codex mode is `--sandbox read-only`, but read-only still lets the
agent grep the entire filesystem (the user explicitly complained about filesystem
search, not just writes). Read scope must ALSO be bounded to the allowed roots, or
the popover should inject ZERO tools for codex too (force the no-tool path).

### R3 — Popover via CLI: why allow ANY tools at all?
The popover is ephemeral and answers from injected context. Giving it even a
read-only sandbox is unnecessary attack surface. The strongest design is: the
popover NEVER uses the agentic CLI tool loop — route it through a tool-free
completion (the HTTP `complete()` path, or a CLI invocation with all tools
disallowed). Defense in depth: even if a flag regresses, the popover can't act.

### R4 — `--add-dir` may GRANT more than intended / cwd leak
If `buildCliCommand` runs the CLI with `cwd` = repo or vault root, the agent may
treat cwd as implicitly allowed even without `--add-dir`. Also `--add-dir` is
additive: passing the vault is fine, but if the process cwd is the plugin/repo dir,
the agent can still read it. Must set a safe `cwd` (a neutral/allowed dir) AND not
inherit a permissive working directory.

### R5 — Symlink / path-normalization escape
Allowed-roots checks that compare string prefixes can be defeated by symlinks,
`..`, or `~` expansion. If we rely on `--add-dir <vault>` and the vault contains a
symlink to `/`, the sandbox may follow it. Path roots must be realpath-resolved;
document that the sandbox's own enforcement (not our string check) is the real
boundary.

### R6 — MCP servers configured by the user (`mcpServers`) re-introduce tools
Even with CLI sandboxing, the sidechat injects the user's external MCP servers'
tools (a filesystem/bash MCP server would re-open the hole). toolPolicy gates
Incurator-vs-none, but `auto` still injects ALL MCP servers. Out of scope for this
milestone? At minimum, document that external MCP servers are the user's own trust
boundary and are not sandboxed by this change.

### R7 — Zotero library path unknown to the plugin
`settings.zoteroBasePath` may be just the base; the actual storage/linked-attachment
roots are discovered by the BACKEND. If the plugin only adds the base path, legit
Zotero PDF access could break (denied). Need the resolved Zotero roots, possibly via
a backend query, or accept the base path covers storage.

## 2. Suggested Alternatives

- **R1/R3 (popover)** — Make the popover tool-free by construction: for CLI
  providers, the popover uses a NON-agentic invocation (no tool loop) or
  `--disallowedTools <all>`; never rely solely on a sandbox mode. Belt and
  suspenders: tool-free path + sandbox.
- **R2 (codex read scope)** — bound codex reads too: `-c sandbox_permissions` /
  workspace scoping rather than blanket `read-only`; or no-tools for the popover.
- **R4 (cwd)** — explicitly set the CLI subprocess `cwd` to an allowed root (the
  vault) and pass `--add-dir` for each additional allowed root; never run from the
  repo/plugin dir.
- **R5 (paths)** — realpath-resolve allowed roots; rely on the CLI sandbox as the
  enforcing boundary, our list as the allowlist input. Document the trust model.
- **R6 (external MCP)** — document explicitly: external `mcpServers` are user-owned
  and outside this sandbox; consider a future setting to disable them for ephemeral
  surfaces.
- **R7 (Zotero roots)** — resolve Zotero roots from the backend (`wiki plugin zotero
  …` already resolves roots) or include `settings.zoteroBasePath` + its `storage/`
  subdir; validate legit Zotero PDF read still works in P0.
