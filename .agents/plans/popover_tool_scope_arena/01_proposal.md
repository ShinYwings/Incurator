# Proposal: toolPolicy-aware CLI command builder + allowed-roots sandbox

Date: 2026-06-21 | Agent Persona: lead_architect (Plugin/Security)

## 1. Core Logic & Implementation

### 1.1 Allowed roots (single source) — MUST filter empty before resolve (R4)
Add a helper on `LLMClient`:
```ts
private allowedRoots(): string[] {
  const candidates = [
    this.vaultRoot,
    this.settings.zoteroBasePath,
    this.settings.zoteroBasePath ? join(this.settings.zoteroBasePath, "storage") : "",
  ];
  return candidates
    .map((p) => (p || "").trim())
    .filter((p) => p.length > 0)        // SECURITY: drop empty/undefined FIRST
    .map((p) => realpathSafe(expandHome(p)))  // resolve symlinks/.. (R5)
    .filter((p) => p.length > 0);
}
```
- **Never pass `--add-dir ""`** — an empty arg makes a CLI default to cwd or `/`,
  silently escalating scope (R4). The filter is mandatory and runs BEFORE resolution.
- When Zotero is unconfigured, allowed roots = just the vault. The CLI `cwd` is
  always set to the vault root (an allowed root), never the repo/plugin dir (R4).

### 1.2 Thread `toolPolicy` into the CLI path
`buildCliCommand(provider, prompt, …)` gains a `toolPolicy: ToolPolicy` param
(default `"auto"`). `streamChatViaCli` / `completeViaCli` already receive the
surface context — pass `toolPolicy` through from `streamChat`'s `opts`. The popover
already calls `streamChat(..., { toolPolicy: "none" })`; we just stop dropping it at
the CLI boundary.

### 1.3 Per-provider flag matrix (EMPIRICALLY VERIFIED flags, replace skip-all)

Flags confirmed against installed CLIs (agy 1.0.10, claude 2.1.175, codex 0.135):

| Provider | Popover (`none`) — zero side effects | Sidechat (`auto`) — scoped |
|---|---|---|
| **agy** | `--sandbox`, `--cd <vault>`, NO trust-workspace env, NO `--add-dir` | `--sandbox` + `--cd <vault>` + `--add-dir <each allowed root>` (NO `--dangerously-skip-permissions`) |
| **claude** | `--tools ""` (disable ALL tools — verified "Use \"\" to disable all") | `--disallowedTools "Bash Read Write Edit WebFetch"` (keep ONLY the DB-scoped MCP curator tools) + `--cd`/cwd=vault |
| **codex** | `--sandbox read-only` + `--cd <vault>` | `--sandbox workspace-write` + `--cd <vault>` + `--add-dir <each allowed root>` |

**claude is controlled by its TOOL SURFACE, not a directory sandbox (R2):** claude
2.1.175 has `--add-dir`/`--allowedTools`/`--disallowedTools`/`--permission-mode`/`--tools`
(the "no such flags" claim is false for this version), BUT `--add-dir` only ADDS
allowed dirs and permission modes are prompt-or-bypass — there is no deny-without-prompt
directory sandbox. So:
- Popover claude → `--tools ""` (tool-free; answers from injected context only).
- Sidechat claude → disable ALL native tools (Bash/Read/Write/Edit/WebFetch). The
  plugin's own `ai-agent-edit` loop (not claude's Write tool) handles vault edits, so
  claude needs no native fs tools. Only the injected **MCP curator tools** remain —
  these are DB/DAG-scoped by construction (not arbitrary fs), so no escape, no shell,
  and no hang (MCP tools auto-run without a permission prompt).

**codex uses `--add-dir <DIR>` + `--cd <DIR>` (verified)** — cleaner than the fragile
`-c sandbox_workspace_write.roots=[…]` TOML array; matches the agy structure.

- Unifying principle: **deny/scope via each CLI's native mechanism** — `--sandbox`
  (agy/codex) + scoped `--add-dir`/`--cd`, or tool-surface removal (claude) — NEVER
  `--dangerously-skip-permissions` / `danger-full-access` /
  `--dangerously-bypass-approvals-and-sandbox`.

### 1.4 No-hang guarantee
Each restricted mode ENFORCES (denies) rather than prompting, so `-p`/`exec` never
blocks on an unanswered permission question. P0 validates this empirically per CLI.

## 2. Pros & Cons

**Pros**
- Fixes the actual exploit (CLI native tools) at the single command-builder choke
  point; no new deps; reuses each CLI's native sandbox/scoping.
- Replaces the dangerous blanket skip with scoped access → vault/Zotero stay usable,
  filesystem escape and arbitrary shell are blocked.
- Resolves the user's hang problem without an interactive bridge.

**Cons / risks**
- Per-CLI flag semantics differ and some are version-sensitive (P0 must verify the
  exact flags exist and that denial ≠ hang on the installed CLI versions).
- A non-prompting claude permission mode that also doesn't bypass needs empirical
  confirmation (`--permission-mode` options vary).
- Zotero library/storage path resolution may need the backend's Zotero root
  discovery (settings may only hold the base path).
