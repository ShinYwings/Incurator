# Containment Proposal: Enforce The Popover's Tool Surface, Not Just Describe It
Date: 2026-08-31 | Agent Persona: containment_engineer

## 0. Framing, stated up front

The briefing's fix-shape is a wording fix: `boundaryConstraints`'s `"local-only"`
case currently lies ("You have NO filesystem access and NO MCP tools"), and the
user has decided the honest replacement should say the popover may use the
guarded `fetch_url`. A prompt is advice to a model, not a constraint on it —
nothing stops the *next* prompt-injected PDF from telling the model to ignore
that sentence and call something else. My assignment is to answer a narrower,
harder question: after the wording is fixed, what is *actually true* about
what the popover's CLI-routed agent can call, independent of what it is told?

The short answer, argued in full below: **the set of MCP servers a given `agy`
invocation loads cannot be scoped per-call without re-introducing the exact
race the briefing forbids** (§1.1–§1.3). That is not a gap in this design pass
— it is a property of the CLI this repo does not control. What *can* be
enforced without that race is a layer down: not *which tools exist*, but *what
those tools are physically able to do once invoked* (§1.4). I recommend
narrowing that layer, enumerate exactly what residual risk remains once it is
narrowed, and separately design the fix for the "auto-denied tool kills the
whole turn" defect, which is real regardless of how the scoping question
resolves (§1.5).

---

## 1. Core Logic & Implementation

### 1.1 Design Q1 — `syncAgyMcpConfig` writes ONE global file; can the popover get a narrower server set without racing the sidebar?

**Trace, verified against the current tree** (`plugin/src/agent/llm/LLMClient.ts:3020-3150`):

`syncAgyMcpConfig()` takes no arguments. Every call — sidebar and popover alike,
since `buildCliCommand`'s `case "antigravity"` (`LLMClient.ts:2657-2681`) calls
it unconditionally at line 2658, before either surface's `ephemeral` branch
does anything else — writes the *same* computed `mcpServers` map (every
enabled `this.settings.mcpServers` entry, plus the auto-injected
`incurator_fetch`) to four locations:

1. `~/.gemini/settings.json` (`admin.mcp.enabled` + `mcpServers`, reconciled)
2. `~/.gemini/config/mcp_config.json` (the registry `agy mcp list` actually reads — `LLMClient.ts:3117-3120`)
3. `~/.gemini/antigravity/mcp_config.json` (mirror of the same)
4. `~/.gemini/incurator/managed_mcp_servers.json` (the prune manifest)

There is no parameter anywhere in this call chain that could carry "this
invocation is the popover, only register `incurator_fetch`." The function has
exactly one output shape, unconditionally, for both surfaces.

**Why writing a narrower registry immediately before spawning the popover's
`agy` is unsafe** — the TOCTOU race the briefing names:

`agy` reads its MCP registry at **its own process startup**, not from the
plugin. The plugin's write (`writeFileSync`, synchronous) and the plugin's
spawn (`child_process.spawn`, async) are two separate steps; between them,
and for some further interval while the spawned `agy` process is still
starting up and has not yet read the file itself, the file is sitting on disk
in whatever state the *last writer* left it. If two `syncAgyMcpConfig` calls
interleave — sidebar call B writes the full set while popover call A's
already-spawned `agy` has not yet reached its own config read — **A's `agy`
process reads B's config, not the one A just wrote**, and ends up with
whichever server set happened to be on disk when it got there. This can go
either direction: the popover could pick up the sidebar's `incurator` server
(the containment failure), or the sidebar could pick up a hypothetically
popover-narrowed set and silently lose `incurator` mid-session (a *worse*
regression — the sidebar's own advertised tools would vanish with no error).

This is not a hypothetical narrow window. The popover is explicitly built to
be usable *while* the sidebar is open (`foregroundRequestControllers` is a
`Set`, not a single controller — `LLMClient.ts:998` — the codebase already
assumes concurrent in-flight requests). A user reading a paper with the
sidebar open in one pane and pulling up Quick Query on a selection is the
product's own intended usage, not an edge case.

**Could the write be held long enough to guarantee the spawned process has
already read it, closing the window?** No signal exists to detect that
moment. `agy`'s own stdout/stderr carries no "config loaded" event this
codebase currently parses (`isAntigravityStatusLine`, `messageUtils.ts:268-294`,
recognizes generic progress/status text, not a config-load milestone), and
even if one did, gating on it would mean holding an exclusive lock across
"write → spawn → wait for first observable output" for *every* antigravity
invocation, sidebar included — serializing concurrent antigravity calls
plugin-wide for however long that takes. That is a real, user-visible latency
regression traded for a race window that would still not be provably closed
(the observed signal is a proxy for "config loaded," not a guarantee of it).
I am not recommending this.

**Alternatives considered and ruled out, with evidence:**

- **A per-invocation `HOME`/config-dir override**, so the popover's spawn
  writes and reads its own private `~/.gemini` copy. Ruled out by this repo's
  *own* prior measurement, not speculation: `agyPermissionLive.test.ts:52-55`
  states plainly — *"agy has no settings-path override, and pointing HOME at a
  temp dir breaks its authentication (the run dies in under a second and every
  rule looks denied, which is a false negative, not a measurement)."* This was
  already tried and measured against the real CLI while building the
  permission-live-test harness. I did not need to re-invoke `agy` to confirm
  this; the comment records a real, already-paid-for measurement against the
  live binary, and I am treating it as established fact per the briefing's own
  instruction to trust measured facts.

- **`agy mcp enable <name>` / `agy mcp disable <name>`, toggled around the
  popover's call.** These subcommands are real — confirmed by static string
  inspection of the installed binary (`strings -a ~/.local/bin/agy`, read-only,
  never executed; see §1.2 for method and why this is not "invoking agy"):
  `"Added \`mcp\` subcommands (\`add\`, \`remove\`, \`list\`, \`enable\`,
  \`disable\`) for managing MCP servers in your user-level \`mcp_config.json\`
  without hand-editing it"`. But this toggles the *same shared file*
  `syncAgyMcpConfig` writes — it is a different write path to identical shared
  state, not a scoping mechanism. Disabling `incurator` before a popover spawn
  and re-enabling it after inherits the exact same TOCTOU window described
  above, with an added failure mode: if the popover call crashes or the plugin
  is killed between disable and re-enable, the sidebar silently loses its
  vault tools until the next `syncAgyMcpConfig` call happens to restore them
  (the reconcile logic can restore *content*, but nothing currently re-runs it
  proactively on a crash). This is strictly worse than the current bug, not a
  fix for it.

- **An env var set only in the `incurator` MCP server's own config entry**
  (e.g. `INCURATOR_MCP_READONLY=1`, read by `wiki mcp` itself to refuse
  mutating tool calls when a popover spawned it). This looked promising
  because it would move enforcement into code Incurator owns (`wiki mcp`,
  `backend/src/curator/mcp/server.py`) rather than relying on `agy`. It fails
  for a structural reason, not a race: **the plugin does not spawn the
  `incurator` MCP server process — `agy` does**, reading `command`/`args`/`env`
  for that server out of the *same* shared registry file at its own startup.
  There is no channel from "the plugin is about to spawn a popover-flavored
  `agy`" into "the env `agy` hands to the `incurator` child it spawns" other
  than that one shared file. The idea does not escape §1.1's race — it
  relocates the race onto a different field (`env` instead of server
  membership) of the identical shared JSON, with the identical TOCTOU window
  and the identical failure direction (a sidebar call could pick up a
  READONLY env meant for the popover and silently lose its ability to
  mutate the vault, with no error surfaced anywhere).

**Conclusion for Q1: not achievable.** Every scoping mechanism this repo can
verify routes through the one shared file `syncAgyMcpConfig` writes, or
through `agy`'s own persistent state that lives beside it. None of them offer
a per-invocation, race-free write. I am not proposing any change to
`syncAgyMcpConfig`'s one-global-write behavior.

### 1.2 Design Q2 — is there ANY verified way to restrict which MCP servers one `agy` invocation loads?

**Method, stated for reproducibility and to be explicit about what "verified"
means here.** Per this repo's own standing rule (memory:
`do-not-invoke-agy-cli.md`) and this task's explicit instruction, I did not run
`agy` — not `agy --help`, not `agy mcp list`, nothing that starts the binary.
Everything below comes from **static inspection of files already on disk**:

```
strings -a /Users/shin/.local/bin/agy > <scratch file>   # read-only, no execution
grep -i mcp <scratch file> | sort -u
```

`strings -a` reads the binary's bytes and prints embedded ASCII/UTF-8 text; it
does not execute a single instruction in the file. The binary is a Go program
built from `google3/third_party/jetski/...` sources (the debug symbol strings
say so directly — this also confirms "jetski" is `agy`'s own internal
codename, load-bearing for §1.5 below) and was **not** fully stripped, so
`strings` recovers real flag names, error-format strings, changelog text, and
a bundled `docs/mcp_servers.md`-style help snippet, not just symbol noise.

**What that search found, and what it rules in/out:**

- `usage: mcp list` and the changelog line *"Added `mcp` subcommands (`add`,
  `remove`, `list`, `enable`, `disable`) for managing MCP servers in your
  user-level `mcp_config.json`"* — confirms the CLI subcommand surface
  discussed in §1.1, and confirms explicitly ("user-level") that these
  subcommands operate on the one shared, standing config file, not a
  per-invocation scope.
- `AllowedMcpServers` / `allowed_mcp_servers` / `allow_mcp_servers` appear as
  protobuf fields — but on `TeamConfig` and
  `UpdateTeamConfigExternalRequest` (`codeium_common_go_proto`,
  `seat_management_go_proto`). This is an **enterprise/team-admin policy
  control**, pushed from a backend management service to seats on a team
  plan, not a CLI flag an individual invocation can set. I found no evidence
  it is reachable from a personal account, and even if it were, it is a
  standing account-level policy (same shape of problem as §1.1, one level up
  the stack), not a per-call scope.
- `McpSetting.mcp_config_json` / `McpSetting.override_mcp_config_json`
  (`google/internal/cloud/code/v1internal` proto) — likewise reads as a
  cloud-side setting object, not a local CLI argument.
- I searched specifically for a CLI flag shape (`--mcp-config`,
  `--allowed-mcp-servers`, `--mcp-server`, `--only-mcp`, any `--*mcp*` token)
  and found **none**. This search method is not merely "absence of evidence":
  the same `strings` pass *does* recover other real flags this codebase
  already relies on verbatim (`"--sandbox",`, `"--print-timeout"` is visible
  as `--print-timeout`-shaped usage text, `"--app_data_dir="`,
  `"--format=%at %H"`), so the technique demonstrably surfaces flag literals
  when they exist. Their absence for MCP scoping is real signal, not a blind
  spot in the method — though it is not a proof; a flag could theoretically be
  assembled from string fragments at runtime in a way `strings` cannot see.

**What would settle this definitively, that I am not doing:** running
`agy --help` and `agy mcp --help` against the real binary, or checking
Antigravity's own published CLI reference docs online. Both are explicitly
out of bounds for me (the standing rule against invoking `agy`, and I was not
asked to browse the web for this). If the system_synthesizer or the user wants
higher confidence than static string inspection provides, either of those two
checks would close the gap — I am naming them rather than guessing further.

**Conclusion for Q2: no verified per-invocation MCP-scoping mechanism exists.**
Treat it as unavailable. If a future `agy` release adds one, the string
`--mcp-config` (or similar) appearing in `strings -a` output on an upgraded
binary is the trigger to revisit this section.

### 1.3 Design Q3 — given `mcp(*)` is a class-wide wildcard, can permissions scope the popover at all?

No, and this is already conclusively established rather than merely likely.
`AGY_MCP_PERMISSION = "mcp(*)"` (`LLMClient.ts:119`) carries its own measured
history in the surrounding comment block (`LLMClient.ts:94-118`): scoped forms
`mcp(incurator_fetch)` and `mcp(fetch_url)` were measured against a real agy
1.1.22 run and both were auto-denied; only the bare wildcard let the call
through. I independently confirmed the wildcard is what's live on this
machine by reading (not invoking) the actual settings file:

```
$ cat ~/.gemini/antigravity-cli/settings.json
{
  "enableTelemetry": false,
  "permissions": { "allow": ["read_file(*)", "command(wiki)", "mcp(*)"] },
  "trustedWorkspaces": ["/Users/shin/shinywings/Incurator"]
}
```

This matches `AGY_REQUIRED_PERMISSIONS` (`LLMClient.ts:120-124`) exactly. The
permission system has exactly one lever for MCP calls — on for every server,
or off for every server — and `command(wiki)` demonstrates the CLI's parser
*can* honor a scoped rule when it chooses to (it is not a blanket limitation
of the rule syntax); `mcp` specifically was measured to not support scoping.
There is no permission-layer answer here, and none of the file-registry
mechanisms in §1.1–§1.2 give permissions anything narrower to scope *to*
even if the wildcard problem were somehow solved.

### 1.4 Design Q4 — recommendation, given per-invocation scoping is unavailable

**I recommend accepting the shared server set** — the popover's `agy`
invocation will see both `incurator` and `incurator_fetch`, identically to the
sidebar's — **and closing the consequence at the one layer that genuinely can
be scoped per-invocation without any shared-file race: the OS sandbox's write
permissions.** This is not a restatement of "rely on the prompt." It is a
concrete, mechanical control that exists in this codebase today and currently
does **not** distinguish the popover from the sidebar, which I found while
verifying this design and consider the most load-bearing finding in this
document.

#### 1.4.1 What the popover can actually reach: the full tool enumeration

`backend/src/curator/mcp/server.py` registers **50 tools** on the `incurator`
server (48 via `@mcp.tool()` decorators, plus `curator_update_artist_persona`
and `curator_update_curator_persona`, registered manually at
`server.py:3367-3368`). `incurator_fetch` registers exactly one:
`fetch_url` (`LLMClient.ts:154`, GET-only, SSRF-guarded). Classified by
whether the underlying operation mutates vault content, the DAG, or
persistent config (source: docstrings and, for every tool marked *(body
checked)*, direct reading of the function body — not docstring alone):

**Read-only (28 tools) — no vault, DAG, or config mutation:**

| Tool | Line |
|---|---|
| `curator_search_zotero_items` | 815 |
| `curator_get_zotero_item_metadata` | 838 |
| `curator_get_zotero_annotations` | 859 |
| `curator_resolve_zotero_pdf` | 883 |
| `curator_get_provider_config` | 940 |
| `check_ingest_status` | 1011 |
| `fetch_document_section` | 1056 |
| `check_source_status` | 1263 |
| `curator_list_external_resources` | 1346 |
| `curator_search_sources` | 1697 |
| `curator_get_pdf_toc` | 1745 |
| `curator_get_pdf_context` *(body checked — docstring explicitly contrasts with `curator_ingest_source`: "Unlike curator_ingest_source (which creates L1-L4 DAG nodes), this tool" does not)* | 1758 |
| `curator_get_provenance` | 1798 |
| `search_curator` (raw DAG hit retrieval, no LLM synthesis, per its own docstring's contrast with `curator_query`) | 1882 |
| `curator_check_workspace` | 2111 |
| `curator_get_node` | 2535 |
| `curator_traverse_evidence` | 2553 |
| `curator_find_contradictions` (list only) | 2612 |
| `curator_layer_index` | 2837 |
| `curator_get_version` | 2870 |
| `get_available_models` | 2880 |
| `curator_status` | 2890 |
| `curator_lint` *(body checked — computes and returns a report object; no file write in the function body)* | 3051 |
| `curator_update_node` *(body checked — this tool is a permanently disabled no-op since v0.3.1: it unconditionally returns `{"ok": False, "updated": False, "error": "Direct Curator node overwrites were removed in v0.3.1..."}`. It is inert, not merely low-risk.)* | 3073 |
| `curator_validate_curate_spec` *(body checked — loads, validates, and compiles `curate.yml`; never writes it)* | 3188 |
| `curator_fetch_context` | 3245 |
| `curator_get_prompt_trace` | 3292 |
| `curator_list_insight_candidates` | 3301 |

**Read-semantics, but writes an internal trace/candidate record (2 tools) —
not a vault file or DAG content write, still a DB write and, for both, an LLM
call that costs the user's configured provider quota:**

| Tool | Line | What it writes |
|---|---|---|
| `curator_query` (primary sidebar Q&A entry point) | 1997 | a prompt-trace record (`PTR-…`, retrievable via `curator_get_prompt_trace`) |
| `curator_explore` (explore-mode query) | 3267 | a prompt-trace record **and** provisional `insight_candidate_ids` rows |

**Mutating (20 tools) — writes vault files, the DAG, or persistent config:**

| Tool | Line | What it mutates |
|---|---|---|
| `curator_set_provider_config` | 971 | LLM provider config |
| `curator_rebind_source` | 1359 | source→page binding |
| `curator_import_source` | 1409 | registers + writes a new source |
| `curator_register_source` | 1450 | registers a new source |
| `curator_build_source` | 1554 | writes L2/L3 DAG nodes |
| `curator_ingest_source` | 1663 | writes L1–L4 DAG nodes |
| `promote_answer` | 2048 | writes into `02_Wiki/` |
| `curator_workspace_init` | 2235 | writes workspace files incl. `curate.yml` |
| `curator_dismiss_contradiction` | 2719 | mutates contradiction review state |
| `curator_resolve_contradiction` | 2754 | patches L2 Atoms when resolving |
| `curator_add_all` | 2964 | writes L1 Contexts |
| `curator_build_all` | 3011 | writes L2/L3 |
| `curator_sync` | 3031 | repairs/writes DAG integrity |
| `curator_reindex` | 3101 | rebuilds DB-native search rows/embeddings |
| `curator_add_knowledge` | 3131 | writes into `02_Wiki/` |
| `curator_plan_workspace` | 3219 | writes a recorded curation plan |
| `curator_promote_insight` | 3311 | writes a durable `02_Wiki/` note |
| `curator_propose_correction` | 3322 | writes a correction proposal record |
| `curator_update_artist_persona` | 333 | writes workspace persona |
| `curator_update_curator_persona` | 419 | writes vault-level persona |

28 (read) + 2 (read-with-trace) + 20 (mutating) = 50, the full registered
`incurator` tool count. I am not rounding this list for brevity; every
mutating tool the server registers is named above.

**`fetch_url`** (`incurator_fetch` server): performs an outbound GET, subject
to the loopback/private/link-local refusal and DNS-pinning already shipped.
Binary responses are saved to a machine-local temp path and returned as a
path string, never inlined — this is a *read* of the network, not a vault
write, and is exactly the tool the product decision approved.

#### 1.4.2 The finding: the OS sandbox does not narrow write access for the ephemeral surface either

`wrapWithOsSandbox` (`LLMClient.ts:2916-2938`) computes the sandbox's WRITE
root set as:

```ts
const roots = [...this.sandboxWriteRoots(), this.getCliCwd()];
```

`sandboxWriteRoots()` (`LLMClient.ts:2889-2891`) is:

```ts
private sandboxWriteRoots(): string[] {
  return this.resolveRoots([this.vaultRoot]);
}
```

Neither function takes the `ephemeral` boolean that `buildCliCommand` already
computes at line 2645 and uses to gate `--add-dir` visibility (line 2653) and
`toolArgs` (claude, line 2687) and `--sandbox read-only|workspace-write`
(codex, line 2745). **The popover's OS-level write permission is identical to
the sidebar's: the whole vault, writable.** This is a real gap between the
product's stated contract for the popover — "no filesystem roots"
(`00_problem.md`'s constraints section, and `POPOVER_PROFILE.allowEdits =
false`, `promptRegistry.ts:49-54`) — and what the OS sandbox profile actually
grants. `--add-dir` (the visibility set) is scoped for ephemeral calls today;
the write-deny profile, the thing that would actually stop a write, is not.

This is exactly the layer that *can* be scoped per-invocation without any
shared-file race, because the write-root list is a **pure function of local,
already-known, per-call state** (the `ephemeral` boolean), assembled into a
command-line argument (`sandbox-exec -p <profile-string>` on macOS, a `bwrap`
argv on Linux) at spawn time. There is no file on disk that a second
invocation could race against — each spawn constructs and passes its own
profile string inline, exactly as the file's own header comment already notes
for the multi-vault case: *"passed INLINE on the command line (no temp file →
no multi-vault / concurrent-call collision)"* (`sandboxWrapper.ts:8-9`). Two
concurrent `agy` spawns with different `ephemeral` values simply get two
different, independently-correct `-p` argument strings; neither can clobber
the other because neither writes anything shared.

#### 1.4.3 Proposed change

```ts
// LLMClient.ts — sandboxWriteRoots gains the ephemeral gate
/**
 * Roots the sandboxed CLI may WRITE to. For a non-ephemeral surface (sidebar):
 * the vault only. For an EPHEMERAL surface (popover): NOTHING — the popover's
 * product contract (POPOVER_PROFILE.allowEdits = false, "no filesystem
 * roots") currently holds only for --add-dir visibility; the OS write-deny
 * profile grants the same vault access as the sidebar regardless. This closes
 * that gap at the one layer that can be scoped per-invocation without racing
 * `syncAgyMcpConfig`'s shared registry file (see plan 77's containment
 * proposal §1.1/§1.4.2) — a value computed locally from the already-known
 * `ephemeral` boolean, baked into an inline sandbox-exec/bwrap argument at
 * spawn time, never written to a shared file.
 */
private sandboxWriteRoots(ephemeral: boolean): string[] {
  if (ephemeral) return [];
  return this.resolveRoots([this.vaultRoot]);
}

private wrapWithOsSandbox(
  base: { command: string; args: string[]; env?: Record<string, string>; stdin?: string },
  provider: LLMProvider,
  ephemeral: boolean,
): { command: string; args: string[]; env?: Record<string, string>; stdin?: string } {
  ...
  const roots = [...this.sandboxWriteRoots(ephemeral), this.getCliCwd()];
  ...
}
```

Call site (`buildCliCommand`, line 2761): `return this.wrapWithOsSandbox(base,
p, ephemeral);` — `ephemeral` is already in scope at that point (computed at
line 2645), so this is a one-parameter thread-through, not new plumbing.
`getCliCwd()` (`<incuratorRepoPath>/.cache/cli`) stays writable regardless of
`ephemeral` — it holds the CLI's own operational files (temp chat-image dirs
for image-bearing turns, per `LLMClient.ts:3182-3196`), not vault content, and
the popover can legitimately send image turns. `buildSandboxPlan`'s existing
"empty roots → refuse" guard (`sandboxWrapper.ts:144-148`) is not triggered by
this change: `roots` still contains `getCliCwd()` even when
`sandboxWriteRoots(true)` returns `[]`, so the plan is never `unavailable`
purely from this narrowing.

No change is needed to `sandboxWrapper.ts` itself. `buildMacosSeatbeltProfile`
and `buildBwrapArgs` already take an arbitrary `allowedRoots: string[]` and
already have unit tests asserting the vault root's write rule (e.g.
`sandboxWrapper.test.ts:9-23`) — passing a root list that excludes the vault
is exactly what they are built to do; this is invoking existing, already-pure,
already-tested logic with a narrower input, not writing new sandbox logic.

#### 1.4.4 What this closes, mechanically

If a prompt-injected instruction inside untrusted PDF/paper content (the exact
threat class `fetch_url`'s SSRF guard was built against) gets the popover's
model to call any of the 20 mutating tools in §1.4.1 — `mcp(*)` still approves
the *call* at the `agy` permission layer, and the `incurator` server still
*attempts* the underlying file write — the write itself now fails at the OS
kernel level (Seatbelt `(deny file-write*)` / bwrap read-only bind), because
the vault is no longer in the sandboxed process tree's write-allow list for an
ephemeral invocation. This is not a silent failure the way the agy-level
permission auto-deny is (§1.5): a filesystem write denial from inside the
`incurator` MCP server surfaces as an ordinary Python exception, which
`server.py`'s tool functions generally catch and return as a typed
`{"ok": False, "error": ...}` MCP tool result — the kind of failure the model
can see and answer around, per the "typed failures, never thrown turns"
principle §13.7 already establishes for local tools. It is a contained,
visible failure instead of vault corruption.

#### 1.4.5 What this does NOT close — stated plainly, per the task's instruction

- **The two read-with-DB-trace tools (`curator_query`, `curator_explore`) are
  untouched.** Neither writes a *file* under the vault or `getCliCwd()`; both
  write to `state.sqlite`, which — per `config.py`'s `get_vault_cache_dir` —
  lives at `<incuratorRepoPath>/.cache/vaults/<hash>/state.sqlite`, a sibling
  of `getCliCwd()`'s `.cache/cli`, **not currently in the OS sandbox's write
  set at all, for either surface.** I flag this as an open question rather
  than folding a fix into this proposal: either (a) DB writes from an
  agy-spawned `incurator` server are *already* failing under the OS sandbox
  today for the sidebar too, in which case this proposal changes nothing
  about that pre-existing behavior, or (b) something I have not traced makes
  `.cache/vaults` reachable that I am not aware of, in which case narrowing
  ephemeral writes to exclude the vault does not touch this path and
  `curator_explore`'s insight-candidate write would still succeed from the
  popover. This is outside my assigned scope (the popover's fetch/MCP tool
  surface specifically); I am naming it because I found it while verifying
  §1.4.3 and it directly bears on how complete "mutation is blocked" actually
  is. It deserves its own, separately-scoped investigation before anyone
  treats this proposal as having fully closed mutation risk.
- **This does nothing about cost.** `curator_query`/`curator_explore` both
  invoke the configured LLM provider. A prompt-injected popover call to either
  still spends the user's quota even though it writes no vault content.
- **This is defense-in-depth, not primary enforcement.** The primary control
  remains: `mcp(*)` approves the call at the agy layer regardless, so the
  *attempt* always happens and always reaches the `incurator` server's Python
  code. This proposal makes the attempt's write fail; it does not stop the
  attempt, the network round-trip to spawn the server, or the model spending
  a turn on it.
- **The prompt wording is a separate, necessary complement, not something
  this proposal implements.** `boundaryConstraints`'s `"local-only"` case
  (`promptRegistry.ts:70-86`) still needs to say the popover has `fetch_url`
  and *only* `fetch_url` — not because that statement enforces anything (it
  does not; see §0), but because an honest instruction plus a hardened
  fallback is strictly better than either alone, and the wording fix is
  explicitly the user's already-taken product decision, not an engineering
  question for this document. I note it here only so the master plan does not
  read this proposal as having covered it.

### 1.5 Design Q5 — where the auto-deny message becomes a fake answer, and the fix

**Convergent finding.** `03_proposal_degradation.md` (resilience_engineer)
independently traced this same mechanism in detail (its §2, "Where the
jetski auto-deny text becomes the user's result") and recommends "Option A —
classify-and-reject at the recovery boundary" as the mandatory backstop, but
explicitly leaves the classifier's design to *"whoever owns that piece"*
(its §6 Cons: *"implementing it is not scoped here in detail... a red-team
question for whoever owns that piece"*). That is squarely this proposal's
territory — I design the predicate and its integration point below, building
on rather than re-deriving their trace. Line numbers below are from my own
direct read of the current file and may differ by a line or two from theirs;
both point at the same code.

**The mechanism** (`LLMClient.ts`, inside the antigravity `child.on("close",
...)` handler):

```
2157   let recoveredAntigravityAnswer = "";
2158   if (outputFile && existsSync(outputFile)) { ... }
2165   } else {
2167     fullOutput = this.cleanCliOutput(provider, fullOutput);
2168     if (provider === "antigravity" && fullOutput.trim().length === 0) {
2169       recoveredAntigravityAnswer = extractAntigravityAnswerFromStderr(fullStderr);
2170       if (recoveredAntigravityAnswer) {
2171         fullOutput = recoveredAntigravityAnswer;
2172       }
2173     }
2174   }
...
2180   } else if (provider === "antigravity" && recoveredAntigravityAnswer) {
2181     closeStatusBlock();
2182     onChunk({ text: recoveredAntigravityAnswer, done: false });   // <- pushed to the UI as a real chunk
...
2224   } else if (emittedAnswer.length === 0) {
2225     // the ONLY branch that would have told the user something went wrong
2229     const errText = fullStderr.trim();
2230     reject(new Error(`${provider} returned no answer (empty response)...`));
2237   } else {
2238     onChunk({ text: "", done: true });
2239     this.recordUsage(provider, observedUsage);
2240     resolve(fullOutput);                                          // <- resolves SUCCESSFULLY with the diagnostic as the answer
2241   }
```

`extractAntigravityAnswerFromStderr` (`messageUtils.ts:296-304`) strips ANSI
and drops lines matching `isAntigravityStatusLine` (`messageUtils.ts:268-294`)
— spinner glyphs, `thinking/processing/generating/...`-prefixed lines,
`mcp servers available/using tool/...`-prefixed lines. Agy's auto-deny
explanation (*"jetski: no output produced — a tool required the ... permission
... auto-denied. Add an allow-rule ... Alternatively, re-run with
--dangerously-skip-permissions..."*) is plain declarative prose. It begins
with none of the recognized progress verbs and is not the "MCP servers
available" banner, so it survives the filter, becomes
`recoveredAntigravityAnswer`, and — because `emittedAnswer.length` is then
nonzero — the code takes the success path at line 2237-2241 instead of either
error branch. The user sees this text rendered with identical styling to a
real assistant reply, including agy's own suggestion to add a
`$read_url$()`-style rule (a form this same file's own comments record as
**pruned/inert** — `LLMClient.ts:76-84`) or to pass
`--dangerously-skip-permissions` — a flag this codebase explicitly refuses to
ever install (`LLMClient.ts:61-63`, `2663-2665`, `2942-2949`). The failure
mode is not "the user got nothing"; it is worse — the user got bad advice,
attributed to the assistant, recommending a security posture this repo has
permanently rejected.

**The fix — a dedicated classifier, sibling to `isAntigravityStatusLine`:**

```ts
// messageUtils.ts
/**
 * agy's own fixed-template explanation for a headless auto-denied tool call.
 * "jetski" is agy's internal codename (confirmed via its own binary's debug
 * symbols, e.g. `google3/third_party/jetski/...` — see plan 77's
 * containment proposal §1.2). This is NOT `isAntigravityStatusLine`: it is
 * plain prose, not a spinner/progress line, so it survives that filter and
 * — without this check — is indistinguishable from a genuine answer rescued
 * from stderr by the caller of `extractAntigravityAnswerFromStderr`.
 *
 * Matched on the fixed signature agy emits, not a loose "permission" or
 * "denied" substring — a genuine answer that happens to discuss a paper's
 * treatment of access control or permissions must not be misclassified as
 * this diagnostic. "no output produced" + "auto-denied" is agy's own
 * template wording (v0.77.0 bug report, captured verbatim), not phrasing an
 * LLM would produce as prose about a subject.
 */
export function isAgyToolDenialMessage(text: string): boolean {
  const value = text.toLowerCase();
  return value.includes("no output produced") && value.includes("auto-denied");
}
```

Integration point (replaces lines 2168-2173 above):

```ts
if (provider === "antigravity" && fullOutput.trim().length === 0) {
  const recovered = extractAntigravityAnswerFromStderr(fullStderr);
  if (recovered && !isAgyToolDenialMessage(recovered)) {
    recoveredAntigravityAnswer = recovered;
    fullOutput = recoveredAntigravityAnswer;
  } else if (recovered) {
    // A tool-denial diagnostic and nothing else. Leave fullOutput empty so
    // the EXISTING `emittedAnswer.length === 0` branch below produces the
    // honest "no answer" error, instead of presenting agy's own raw
    // diagnostic — which recommends --dangerously-skip-permissions, a flag
    // this codebase refuses to ever install — as if it were the assistant's
    // reply.
    agyToolDenialDiagnostic = recovered;
  }
}
```

And enriching the existing empty-answer error (lines 2224-2236) rather than
adding a new branch:

```ts
} else if (emittedAnswer.length === 0) {
  const errText = fullStderr.trim();
  const denialNote = agyToolDenialDiagnostic
    ? "\n\nAntigravity attempted to use a tool that isn't available in this " +
      "context and was auto-denied in headless mode, producing no other " +
      "answer. Try rephrasing so the request doesn't need that tool, or retry."
    : "";
  reject(new Error(
    `${provider} returned no answer (empty response).${denialNote}` +
      (errText ? `\n\n${errText.slice(0, 400)}` : "") +
      `\n\nThis usually means the provider quota/capacity is exhausted, the ` +
      `request timed out, or the model returned nothing. Switch provider/` +
      `model or retry after quota resets.`
  ));
}
```

This is deliberately the minimal change, matching resilience_engineer's
Option A rather than their explicitly-not-recommended Option B (retry with a
no-tools instruction — I agree with their three reasons against it, in
particular that it races the existing, more specific
`isUnambiguousQuotaError`/`isQuotaErrorMessage` checks earlier in the same
function). It converts a fabricated-looking success into an honest,
UI-distinct error. I am **not** proposing the more ambitious "salvage genuine
partial prose that preceded the diagnostic" refinement (splitting recovered
text into a pre-diagnostic segment and returning that as a degraded partial
answer) as part of this pass — in the one captured instance of this bug,
stderr contained nothing but the diagnostic, so there was no prose to salvage,
and building a splitter against a single observed case risks over-fitting a
template that could shift with an agy version bump. I record it as a
plausible future refinement, not a requirement.

**Why this integrates cleanly with §1.4:** once fetch_url is correctly wired
and the wording is fixed, this specific `read_url` denial should stop
occurring — but the classifier is not scoped to `read_url`. Any other native
CLI tool the model reaches for that isn't in `AGY_REQUIRED_PERMISSIONS`
(future capability the model discovers, a change in agy's own built-in tool
set) hits the identical "jetski: no output produced ... auto-denied" template,
and this fix covers all of them, not just the one in the bug report.

### 1.6 Design Q6 — testing without ever invoking the real `agy` CLI

Every technique below already has a precedent in this test suite; none
require the live binary, matching the standing constraint (memory:
`do-not-invoke-agy-cli.md`) and the reason it exists (real invocations spend
the user's own account/quota).

**1. `plugin/src/agent/sandboxWrapper.test.ts`** (pure functions, no I/O) —
extend the existing `describe("macOS seatbelt profile (v0.23.0)")` and
`describe("Linux bwrap args (v0.23.0)")` blocks (already at lines 8-65) with a
direct call proving the §1.4.3 change works at the profile-generation level,
entirely independent of `LLMClient`:

```ts
it("an empty write-root list denies the vault while still allowing the CLI's own dir (ephemeral popover shape)", () => {
  const profile = buildMacosSeatbeltProfile(["/cli-cwd-only"], "/home", "/tmp");
  expect(profile).not.toContain('(subpath "/Vault")');
  expect(profile).toContain('(subpath "/cli-cwd-only")');
});
```

This locks the primitive `buildSandboxPlan`/`buildMacosSeatbeltProfile`/
`buildBwrapArgs` compose correctly with a vault-excluding root list — the
exact shape `sandboxWriteRoots(true)` will hand it.

**2. `plugin/src/agent/llmClient.test.ts`**, extending the existing
`describe("CLI tool-scope sandbox source contract (v0.23.0)")` block
(source-string assertions against the raw `.ts` file, the established pattern
in this file at lines 973-1054 — no execution, no spawn):

```ts
it("scopes the OS sandbox write set by ephemeral, not just --add-dir visibility", () => {
  expect(source).toContain("private sandboxWriteRoots(ephemeral: boolean)");
  expect(source).toContain("if (ephemeral) return [];");
  expect(source).toContain("this.wrapWithOsSandbox(base, p, ephemeral)");
});
```

This is the same technique already used at line 1042
(`expect(source).toContain("ephemeral ? [] : this.allowedRoots().flatMap")`)
for the `--add-dir` visibility gate — extending an existing, already-accepted
pattern rather than introducing a new one.

**3. `plugin/src/agent/llmClient.test.ts`**, extending
`describe("Antigravity CLI stderr recovery")` (lines 901-926, pure string
function `extractAntigravityAnswerFromStderr` plus the new
`isAgyToolDenialMessage`, zero process spawn):

```ts
it("classifies agy's own auto-deny diagnostic as a denial, not a rescued answer", () => {
  const denial =
    'jetski: no output produced — a tool required the "read_url" permission ' +
    'that headless mode cannot prompt for, so it was auto-denied. Add an ' +
    'allow-rule under permissions.allow in settings.json (e.g. $read_url$()). ' +
    'Alternatively, re-run with --dangerously-skip-permissions to auto-approve ' +
    'all tools.';
  expect(isAgyToolDenialMessage(denial)).toBe(true);
});

it("does not misclassify ordinary prose that happens to mention permissions", () => {
  const answer = "The paper's appendix discusses file permissions and access " +
    "control models in distributed systems.";
  expect(isAgyToolDenialMessage(answer)).toBe(false);
});
```

— the first fixture is the literal string from `00_problem.md`'s "The
report" section, so this test reproduces the bug offline; the second is the
adversarial case the predicate's own doc comment commits to not
misclassifying (a real answer discussing permissions as a *subject*).

**4. `plugin/src/agent/llmClient.test.ts`**, extending
`describe("shouldInjectMcpTools (popover tool isolation, v0.19.0)")`
(lines 729-763) with a test that names the gap this whole document is about,
so the distinction between "the plugin injects no MCP tool descriptions" and
"the CLI-loaded agy process has no MCP tools available" cannot silently
re-blur:

```ts
it("does NOT claim CLI-routed MCP availability — shouldInjectMcpTools governs plugin-injected tool descriptions only", () => {
  // This function returning false for useCli=true says nothing about whether
  // agy itself has MCP tools loaded — that is syncAgyMcpConfig + mcp(*),
  // entirely independent of this function (00_problem.md item 7). A future
  // reader must not treat a green test here as proof of the popover's
  // zero-MCP guarantee on the CLI path.
  expect(shouldInjectMcpTools("local-only", true, true)).toBe(false);
  // ^ true regardless of what agy's own registry contains.
});
```

This test does not newly *prove* anything about agy's behavior (nothing here
can, without invoking it) — its value is documentary: it sits next to the
existing assertions the docs currently over-read as "enforcement," with a
comment pointing at why they are not sufficient, so the next person who
touches this code does not repeat the inference PLUGIN_SCHEMA §13.7 currently
makes.

**5. Static/manual verification only, never automated, never run by me or in
CI** — the live-gated pattern this repo already has for measuring real CLI
behavior, `plugin/src/agent/agyPermissionLive.test.ts`: `describe.skip` unless
`INCURATOR_LIVE_AGY=1` is set by a human who owns the quota being spent. If
the system_synthesizer wants stronger evidence than §1.2's static string
search for "no per-invocation MCP scope exists," extending this file with an
analogous gated case (spawn two overlapping `agy` calls with deliberately
different registries and see which one each process actually loaded) is the
correct home for it — genuinely live-testing the race in §1.1, gated exactly
like the existing permission tests, never run by default, never run by me.

**Everything above runs under** `cd plugin && npx vitest run -c
./vitest.config.ts` and `cd plugin && npx tsc --noEmit`, per `AGENTS.md`/
`CLAUDE.md` — no network access, no CLI binary, no cost.

---

## 2. Pros & Cons

### Pros

- **Answers the enforcement question honestly instead of asserting a false
  guarantee.** §1.1–§1.3 conclude, with cited evidence rather than assumption,
  that per-invocation MCP-server scoping is not available in this codebase.
  That negative result is itself valuable: it directly falsifies
  PLUGIN_SCHEMA §13.7's current claim that "Enforcement is behavioral, not
  textual... locked by tests asserting that MCP injection is refused for the
  popover policy under every combination of MCP-manager presence and CLI
  routing" — the tests it points at (`shouldInjectMcpTools`) govern a
  different mechanism (plugin-injected tool descriptions for API providers)
  and say nothing about what `agy` itself loads. Whoever synthesizes the
  master plan needs this corrected regardless of which containment strategy
  is chosen.
- **The OS-sandbox write-narrowing in §1.4 is genuinely enforceable, race-free,
  and small.** One boolean threaded through two already-existing private
  methods (`sandboxWriteRoots`, `wrapWithOsSandbox`), zero changes to the pure,
  already-tested `sandboxWrapper.ts` primitives, zero changes to
  `syncAgyMcpConfig`. It closes a real, previously-undocumented gap between
  the popover's stated "no filesystem roots" contract and its actual OS-level
  write access — a gap that existed independently of the fetch_url decision
  and would still be worth closing even if the MCP question were resolved a
  different way.
- **§1.5's fix is scoped, additive, and converges with an independently-derived
  finding.** `03_proposal_degradation.md` traced the identical mechanism from
  a different angle and reached the same conclusion (Option A). Two personas
  arriving at the same root cause and remedy shape via different investigation
  paths is exactly the kind of cross-validation the Arena process is for.
- **The tool enumeration in §1.4.1 is exhaustive, not illustrative** — all 50
  `incurator` tools are individually classified with line citations, so the
  master plan does not have to take "mutating tools exist" on faith; it can
  see exactly which 20 they are and decide the acceptable-risk question with
  full information.
- **Every proposed test in §1.6 runs offline** and either extends an existing
  `describe` block using a pattern this file already uses (source-string
  contracts, fixture-string classifiers, pure sandbox-profile calls) or is
  explicitly routed to the one file already built and gated for live
  verification — no new testing infrastructure, no invented pattern.

### Cons — what this proposal does NOT solve, stated plainly

- **It does not stop a mutating tool call from being attempted.** `mcp(*)`
  still approves every `incurator_*` call at the agy permission layer,
  unconditionally, regardless of §1.4's OS-sandbox change. A prompt-injected
  popover turn can still cause the `incurator` MCP server to spin up, receive
  a mutating tool call, and spend a full round-trip attempting a write that
  then fails at the kernel level. The attempt, the process spawn, and the
  model's turn are not prevented — only the write's *effect* is. This is a
  containment boundary, not a block.
- **It does not stop `curator_query`/`curator_explore` from running.** Both
  are read-semantics by my classification (§1.4.1) — they synthesize an
  answer and record a trace, they do not write vault files — but both invoke
  the user's configured LLM provider and cost real quota if triggered by
  injected content, and §1.4's OS-sandbox change does nothing to gate that,
  because there is no filesystem write to deny.
- **The `.cache/vaults/state.sqlite` write-path question (§1.4.5) is left
  open, not resolved.** I found, while verifying the sandbox write-root logic,
  that the DB path used by every `incurator` tool that touches `state.sqlite`
  is not in the OS sandbox's write-allow list for *either* surface today. I
  am naming this rather than either fixing it (out of scope: it affects the
  sidebar identically, and fixing it might mean *widening* what's writable,
  which cuts against this proposal's whole direction) or asserting confidently
  it is or isn't already broken in production — I did not trace far enough to
  know which. Whoever picks this up next should settle that before treating
  "mutation is contained" as complete.
- **No amount of this proposal makes the wording correct.** §1.4.5's last
  bullet says this directly: the prompt still needs to stop claiming "NO MCP
  tools" and start saying what is actually true (fetch_url only, by policy,
  not by hard enforcement). That is not an engineering gap this document
  closes — it is the sibling half of the same fix, explicitly out of my
  assigned angle, and the master plan must not treat this document as having
  shipped it.
- **§1.2's negative result ("no per-invocation scoping mechanism") rests on
  static string inspection of one installed binary version, not on
  documentation or a definitive negative from the vendor.** I named exactly
  what would raise confidence further (`agy --help` / `agy mcp --help` against
  the live binary, or the vendor's own CLI reference) and why I am not doing
  it myself. A future `agy` upgrade could add a flag this search would not
  have found if it were assembled from string fragments at runtime rather
  than a literal. This is a real, bounded uncertainty, not a rounding error —
  I am flagging it rather than overstating §1.1–§1.2's certainty.
- **The classifier in §1.5 is a single fixed-template match** ("no output
  produced" + "auto-denied"), matched against exactly one observed instance of
  agy's diagnostic wording. If a future agy version rephrases this message,
  the classifier silently stops firing and the bug this section fixes could
  reopen without any test catching the *regression* (the fixture-string test
  in §1.6.3 would still pass against the old wording; it would not know the
  live CLI had changed its wording). This is the same category of risk the
  existing `AGY_READ_PERMISSION`/`AGY_MCP_PERMISSION` comments already live
  with for permission-rule syntax, and the same mitigation applies: the
  live-gated test file (§1.6.5) is where a human re-verifying this after an
  agy upgrade should look, not something this static classifier can
  self-detect.
