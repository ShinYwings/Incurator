# AGY launch-context probe: isolation prerequisite remains unproven

Date: 2026-09-14. Bounded follow-up to `05_handoff_consensus.md`.

## Result

The installed binary does not document a per-launch or project-local MCP
configuration surface. A disposable-directory discovery check did not list
the private server placed in either `.mcp.json` or `mcp_config.json`. This is
evidence about the management command, not proof that every internal runtime
loader ignores these files. Consequently no authenticated sentinel tool call
was attempted: safe isolated server selection was not established.

Actual environment forwarding, simultaneous launch isolation, daemon reuse,
cancellation and subsequent launch behavior remain **unproven**. Do not mark
the Antigravity route ready based on this probe. No application code changed.

## Exact evidence

- Executable: `/Users/shin/.local/bin/agy`, Mach-O ARM64, 178935744 bytes,
  file timestamp September 10 10:53.
- SHA256: `f3671863b53ecef2c45a41673677fe603fbe5d73df33d744feec3e88d5af0199`.
- `agy --help` includes `--project`, `--new-project`, `--sandbox`,
  `--print-timeout`, but no per-call MCP configuration flag.
- `agy mcp add --help` accepts server name/command and static `--env KEY=value`,
  but no project/scope flag. Embedded changelog explicitly describes these
  commands as managing the **user-level** `mcp_config.json`.
- Installed primary documentation, read in full:
  `/Users/shin/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/mcp_servers.md`.
  It lists only global `~/.gemini/config/mcp_config.json` and enabled-plugin
  `plugins/<plugin_name>/mcp_config.json`. Stdio processes are launched by the
  language server; the documentation does not promise inheritance of the
  invoking CLI's environment.
- Binary strings contain `.mcp.json`, but also a Claude plugin importer and
  `stageClaudeMCPServers`; that string alone does not establish a project-local
  AGY runtime contract. No internal override protobuf field was treated as a
  supported CLI configuration API.
- Created disposable directory `/tmp/incurator-agy-handoff.iHBuTO` with two
  private candidate config files, each defining only
  `incurator-handoff-private-probe` with command `/usr/bin/false`. This harmless
  placeholder tests discovery before introducing an actual sentinel server.
- Ran `agy mcp list` from that cwd with pipeline failure propagation enabled.
  Exit 0, three output lines; exact-name presence check returned
  `private_probe_present=false`. Other registry contents were not printed.

## Scope and remaining verification

No global registry, authentication, provider settings, vault, or production
database was edited. No authenticated provider request was made. No permission
bypass or blanket tool grant was used. The two disposable candidate config
files remain for reproducibility; they contain no credentials or user content.

A successful integration test needs a supported isolated MCP configuration
surface first. With that established, use a stdio server returning only the
single harmless `INCURATOR_CHAT_DIAGNOSTIC_CONTEXT` sentinel, and test real
authenticated calls with two different simultaneous launch values, reused
daemon/server state, cancellation and a fresh subsequent launch. Do not read
or return the rest of the environment. A fake child process inheriting env
cannot close the real CLI-to-language-server-to-MCP gap.

Do not mutate the user's shared registry merely to manufacture test access.
Until a supported isolated route is established, the consensus must retain
this explicit integration gap rather than promising AGY retention coverage.

## Follow-up: documented project-plugin route found

Reading the complete installed `docs/plugins.md` and its referenced
`docs/json_configs.md` establishes a supported project-local route that the
plain-config discovery probe above did **not** exercise:

- Plugins live in `plugins/<name>/` under a customization root, explicitly
  including project `.agents/plugins/`.
- A minimal `plugin.json` with `name` marks a plugin. Its `mcp_config.json`
  supplies MCP servers. Most discovered plugins are enabled by default unless
  their manifest says `disabled: true` or an existing preference overrides it.
- `json_configs.md` explicitly allows `.agents/plugins.json` registration in
  the project root and resolves relative entries from the workspace/repo root.
- Global `plugin enable` is unnecessary for a uniquely named default-enabled
  disposable project plugin. `agy plugin enable --help` is not a help surface:
  it returned `plugin "--help" not found or invalid`; no plugin was enabled.
- `agy agent --help` only documents listing agents. The inspected customization
  documentation provides no automatic conversation/session identifier in MCP
  request `_meta` that could substitute for the explicit launch context.

Therefore the next concrete integration test is a **disposable project plugin**,
not a shared-registry change. Project-plugin discovery, actual sentinel call
and per-launch environment isolation still need execution; they are not proven
by these documentation findings. The earlier statement about no documented
project-local surface applies to standalone MCP config, not this plugin route.

## Real authenticated disposable-project attempts

The root authorized testing the documented plugin route. Created only inside
the disposable directory a `.agents/plugins/incurator-private-handoff-probe/`
manifest and MCP config pointing to `probe.py` there. This minimal JSON-RPC
stdio server reads **only** `INCURATOR_CHAT_DIAGNOSTIC_CONTEXT`, records that
synthetic value plus its own PID to a private observation file on startup, and
exposes `read_handoff_sentinel` returning that value. It does not enumerate
environment variables or read any user file. Configuration carries no static
context env value, so a returned sentinel would test actual inheritance.

`agy plugin validate .agents/plugins/incurator-private-handoff-probe` returned
exit 0 and `mcpServers: 1 processed`.

Two actual authenticated invocations used `--sandbox --disable-slash-commands
--print-timeout 45s --output-format json -p`, a prompt restricted to that single
MCP tool, and explicit instructions to stop if unavailable or denied. No
permission bypass was supplied. The prompt never contained the sentinel value.

1. Launch env `incurator-probe-launch-A`; initial disposable workspace.
   Conversation `1bf1e37a-7259-4392-ad30-a212e915fb4c`, exit 0, provider
   status `SUCCESS`, duration 4.109046 seconds, one turn. Response: the named
   MCP tool is unavailable; stopping as instructed.
2. Initialized Git only in the disposable directory, then added documented
   `.agents/plugins.json` with `entries: [{path: ".agents/plugins"}]` to remove
   ambiguity about repository-root discovery. Launch env
   `incurator-probe-launch-B`; conversation
   `c7596f8c-6f72-4420-9371-f6d14446b1b8`, exit 0, provider status `SUCCESS`,
   duration 3.445112 seconds, one turn. Same unavailable-tool response.

After both invocations, no `observed-*.json` file existed. This independently
corroborates that this private server never started; model prose alone is not
the evidence. The successful provider status means the request completed, not
that the integration passed. The docs/validation path did not result in runtime
MCP activation in this sandboxed print configuration.

Authentication is therefore available, but the project plugin runtime route
remains unresolved. No conclusion about environment forwarding can yet be
drawn, and simultaneous/daemon/cancellation tests would add no information
until the server launches. These attempts supersede the earlier statement
that no authenticated request had been made. Only synthetic probe prompts were
submitted; global config/auth and vault contents remain untouched.
