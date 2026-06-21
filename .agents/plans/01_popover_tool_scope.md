# v0.23.0 Master Implementation Plan — Popover Tool Scope & CLI Sandbox

Date: 2026-06-21
Status: DRAFT — Arena concluded. Awaiting human review (relay STOP gate).
Branch: `feature/popover-tool-scope`
Arena record: `.agents/plans/popover_tool_scope_arena/`

## 0. P0 outcome — design revised to HYBRID (OS sandbox + flags)

P0 empirically falsified the flag-only approach: **`agy --sandbox` does NOT contain
agy** (it created files / read out-of-bounds in live tests) and agy has no `--tools`.
`claude --tools ""` works; codex `--sandbox` is the documented write-blocker. macOS
`sandbox-exec` was then validated to contain agy's nested-child writes (deny-by-default
+ allow-roots). **User decision: Hybrid, macOS + Linux (no Windows), AUTOMATIC (no
manual user setup).** This plan is updated accordingly.

## 1. Objective

Close the CLI-native-tool escape that lets the agent run scripts
(`find_mvg_text.py`), search the whole filesystem, and create files from the Quick
Query popover (and over-broadly from the sidechat). The MCP-injection + shared-prompt
half was fixed in v0.19.0; this milestone fixes the **CLI command-builder** half:

1. **Popover = zero side effects on every provider.** `toolPolicy: "none"` reaches
   the CLI path; CLI providers run tool-free (all tools disallowed / non-agentic) +
   sandboxed. A PDF-text popover query answers from injected context only.
2. **Sidechat tools scoped to allowed roots.** Replace
   `--dangerously-skip-permissions`/trust-workspace with access limited to the
   vault + Zotero folder + Zotero library via each CLI's native sandbox/`--add-dir`.

The fix has TWO layers:
- **Flag layer (primary, claude/codex)**: claude `--tools ""` (popover) /
  `--disallowedTools` (sidechat); codex `--sandbox read-only|workspace-write` +
  `--add-dir`. Drop `--dangerously-skip-permissions`/trust-workspace everywhere.
- **OS-sandbox layer (required, agy; defense-in-depth elsewhere)**: wrap the CLI
  subprocess in an OS sandbox generated from the allowed roots — macOS `sandbox-exec`
  (deny `file-write*`+`process-exec*` outside roots, allow runtime dirs), Linux `bwrap`
  (`--ro-bind / /` + `--bind <root>` per root). AUTOMATIC; no manual setup.

**Definition of done**: with any CLI provider, a popover query produces no side
effects (no file creation/exec); the sidechat's tools cannot write/exec outside the
allowed roots; agy is contained by the OS sandbox; no surface hangs.

## 2. Explicit Non-Goals

- NOT building an interactive permission-approval UI (sandbox denies, not prompts).
- NOT sandboxing user-configured external `mcpServers` (their own trust boundary;
  documented). This covers CLI-native tools + the Incurator MCP server.
- NOT touching the HTTP/MCP-injection path (already correct via `toolPolicy` v0.19.0).
- NOT Windows (user excluded). macOS + Linux only.
- NOT read-restriction as a hard requirement (security-critical harm is writes/exec;
  reads allowed to avoid breaking the CLI — read-scoping is a stretch goal).
- NOT making agy strictly tool-free (impossible — no `--tools`); agy is *contained*
  (no side effects) but may read within the sandbox during a popover query.
- NOT changing the chat/answer model or the prompt registry contents.

## 3. Strict Quality Conditions & Release Gates

- **P0 empirical gate (security)**: for each installed CLI (`agy`, `claude`,
  `codex`), evidence that the restricted mode (a) DENIES an out-of-bounds op quickly
  and (b) does NOT prompt/hang in `-p`/`exec`; and that legit in-vault tool use +
  Zotero PDF read still work. A provider that prompts falls back to the tool-free path.
- Popover: assembled CLI command for `toolPolicy: "none"` contains NO
  `--dangerously-skip-permissions` / `danger-full-access` /
  `--dangerously-bypass-approvals-and-sandbox`, and disables tools. Asserted by test.
- Sidechat: assembled CLI command scopes to realpath-resolved allowed roots
  (`--add-dir`/sandbox), no blanket skip. Asserted by test.
- `npx tsc --noEmit` + `npx vitest run` 100% green incl. new tests.
- Docs: SYSTEM_BEHAVIOR + PLUGIN_SCHEMA (CLI sandbox contract) + PLUGIN_GUIDE EN→KR.
- Minor bump `0.22.0 → 0.23.0`; 4 spec titles `v0.23`; spec_sync green.

## 4. Locked Design Decisions (Arena Consensus)

1. **`toolPolicy` threads into `buildCliCommand`** (default `"auto"`), passed from
   `streamChat`/`complete` opts through `streamChatViaCli`/`completeViaCli`.
2. **Popover (`none`) = tool-free + sandboxed** by construction (R3): CLI providers
   run with all tools disallowed / non-agentic AND a sandbox — never rely on one layer.
3. **Sidechat (`auto`) = scoped tools** via each CLI's NATIVE mechanism (flags
   EMPIRICALLY VERIFIED on installed versions), NEVER skip-all:
   - agy: `--sandbox` + `--cd <vault>` + `--add-dir <root>` per allowed root (drop
     `--dangerously-skip-permissions` + `*_TRUST_WORKSPACE`).
   - claude: controlled by its TOOL SURFACE, not a directory sandbox (R2 — claude has
     no deny-without-prompt dir sandbox). Disable ALL native tools
     (`--disallowedTools "Bash Read Write Edit WebFetch"`); keep only the DB-scoped MCP
     curator tools; the plugin's `ai-agent-edit` loop handles vault edits. Popover
     claude = `--tools ""`. (claude 2.1.175 HAS these flags — the "flag hallucination"
     claim was false; the valid substance is "no dir sandbox → use the tool surface".)
   - codex: `--sandbox workspace-write` + `--cd <vault>` + `--add-dir <root>` per allowed
     root (verified flags — NOT the fragile `-c sandbox_workspace_write.roots` TOML).
4. **Allowed roots** = realpath-resolved `vaultRoot` + `zoteroBasePath` (+ its
   `storage/`); CLI subprocess `cwd` = vault root, never repo/plugin dir (R4/R5).
   `allowedRoots()` MUST drop empty/undefined paths BEFORE resolution and NEVER pass
   `--add-dir ""` (an empty arg escalates scope to cwd/`/` — R4).
5. **No-hang via deny-by-sandbox** (R1); empirically validated in P0.
6. **External MCP servers out of scope** (R6), documented.
7. **OS-sandbox layer (P0 round 2, REQUIRED for agy; defense-in-depth for all)**:
   `buildCliCommand` prepends an OS-sandbox wrapper generated from `allowedRoots()`:
   - macOS: `sandbox-exec -f <generated .sb>` — deny `file-write*` + `process-exec*`
     outside roots; allow vault/Zotero roots + the CLI's runtime write dirs
     (`$TMPDIR`/`/private/var/folders`, home config/cache). Validated to contain
     nested-child writes.
   - Linux: `bwrap --ro-bind / /` + `--bind <root> <root>` per allowed root (+ dev/proc).
     If `bwrap` is missing → detect, show a one-line install hint, and refuse the
     agentic CLI for tool-sensitive surfaces until installed.
   - AUTOMATIC (no manual user setup). Windows: out of scope → CLI agentic tools run
     as today (documented limitation) OR force tool-free where possible.
   - agy is contained by this layer (its own flags are ineffective); claude/codex
     keep flag control as primary + OS sandbox as defense-in-depth.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: interactive approval UI; external MCP sandboxing; HTTP path.
- **Stop Conditions**:
  - **STOP after this plan** for human review (relay gate).
  - **STOP after P0** if any CLI cannot be made to deny-without-hang AND tool-free
    fallback is also infeasible for it → reassess that provider's design.
  - **STOP** if scoping breaks legit Zotero PDF reads and backend root resolution is
    required → decide whether to pull in the backend Zotero-root query.

## 6. Evidence Ledger

See `.agents/plans/01_popover_tool_scope_roadmap_evidence.md`. Key pre-facts:
popover already tool-free on HTTP (v0.19.0); `buildCliCommand` (`llmClient.ts:1826`)
ignores `toolPolicy`; agy uses `--dangerously-skip-permissions` + trust-workspace;
claude has `--add-dir`/`--allowedTools`/`--disallowedTools`/`--permission-mode`;
codex has `-s read-only|workspace-write` + `-c sandbox_*`; allowed roots derive from
`LLMClient.vaultRoot` + `settings.zoteroBasePath`.

## 7. Execution Phases (plugin-only TDD; STOP after this plan for approval)

- **P0 — Empirical sandbox validation (HARD GATE)**: per-CLI, prove deny-not-hang
  for an out-of-bounds op + legit in-vault/Zotero op works; record exact flags +
  versions. Decide tool-free fallback per provider that prompts.
- **P1 — Contract & docs (docs-first)**: SYSTEM_BEHAVIOR CLI-sandbox section +
  PLUGIN_SCHEMA (toolPolicy→CLI flag matrix, allowed-roots trust model) +
  PLUGIN_GUIDE EN→KR; bump 4 spec titles to `v0.23`.
- **P2 — `allowedRoots()` + thread `toolPolicy` into the CLI path** (no behavior
  change yet beyond plumbing). (vitest+tsc)
- **P2b — OS-sandbox wrapper** (`sandboxWrapper.ts`): pure functions
  `buildMacosSeatbeltProfile(roots)` + `buildSandboxPrefix(platform, roots, bwrapPresent)`
  returning the `sandbox-exec -f <tmp .sb>` (macOS) / `bwrap …` (Linux) command prefix;
  bwrap-availability detection + missing-bwrap guidance. Unit-tested (profile/bind
  generation, empty-roots guard, platform switch).
- **P3 — Per-provider flag matrix + sandbox in `buildCliCommand`** (popover
  tool-free+sandbox; sidechat scoped; drop `--dangerously-skip-permissions`/
  trust-workspace; safe `cwd`; PREPEND the OS-sandbox prefix — required for agy).
  Tests assert command strings per (provider × toolPolicy × platform). (vitest+tsc)
- **P4 — Validation**: re-run P0 ops through the plugin path; popover zero-side-effect
  + sidechat scoped + agy OS-contained, all no-hang.
- **P5 — Release**: bump `0.23.0`, CHANGELOG, spec titles, full CI, delete plan,
  release commit + PR.

> Versioning: Minor `0.22.0 → 0.23.0` (security behavior change to CLI tool scope).
