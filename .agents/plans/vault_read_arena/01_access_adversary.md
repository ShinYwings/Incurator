# Independent access and containment adversary

Date: 2026-09-21. Scope: read-only investigation and private temporary probes;
no application, production vault, global CLI configuration, or credentials edits.

## Evidence and causal distinction

`LLMClient.buildCliCommand` currently builds Codex with native `read-only` or
`workspace-write` and then unconditionally calls `wrapWithOsSandbox`. On macOS,
that wrapper executes the entire CLI inside Seatbelt. Codex subsequently applies
its own Seatbelt profile when executing a tool. This is a nested sandbox setup.

A private, non-LLM subprocess probe on this host establishes:

- `/usr/bin/sandbox-exec -p PROFILE /usr/bin/true` succeeds, exit 0.
- The same single wrapper successfully reads this Arena's `00_problem.md`.
- `/usr/bin/sandbox-exec -p PROFILE /usr/bin/sandbox-exec -p
  '(version 1) (allow default)' /usr/bin/true` exits 71 with the exact reported
  `sandbox-exec: sandbox_apply: Operation not permitted` string.

The outer PROFILE permits reads and denies writes. Therefore this failure is
not a note-path lookup failure and not a vault read grant being absent from that
profile. The nested sandbox application itself fails before the child command.
This proves the causal mechanism on this host; the original incident's raw
provider trace has not been inspected, so do not claim an exact trace match.

Installed `codex exec --help` explicitly describes `--add-dir` as additional
**writable** directories. The current shared `allowedRoots()` includes vault,
Zotero base, and Zotero storage and incorrectly describes that set as mere read
visibility for Codex. The outer sandbox has been the layer preventing writes to
Zotero. Removing only the wrapper while retaining those flags is not correct.

## Preferred repair

Use native Codex containment as its sole sandbox. The existing Seatbelt/bwrap
wrapper remains on the providers that need it. Apply the Codex case to every
provider branch actually implemented through the `codex` executable, including
any DeepSeek/Ollama CLI fallback, rather than checking only a marketing provider
name.

For non-ephemeral sidechat, use `workspace-write`, make only the vault an
additional writable directory, and retain the existing CLI working directory as
the operational write root. Clear inherited `sandbox_workspace_write.writable_roots`
so the generated launch does not accidentally inherit unrelated user-configured
write grants. Disable broad `/tmp` write admission with
`sandbox_workspace_write.exclude_slash_tmp=true`. Preserve the plugin's explicit
CLI TMPDIR, already underneath the CLI cwd. Reads of the configured Zotero
reference remain possible without granting Zotero writes.

For ephemeral surfaces, retain native `read-only` and grant no additional writable
vault or reference directories. Do not reduce sidechat to read-only: native write
capability exists today and the user explicitly asked for reliable source access,
not a narrower editing product.

Do not replace either native mode with `danger-full-access` or a blanket bypass.
Keeping the outer sandbox and disabling Codex's own layer could be made to work,
but it requires a different write-root policy for ephemeral calls and unavailable
wrapper handling, while the currently installed CLI exposes only dangerous native
bypass modes on its ordinary exec interface. It is a larger repair with more
failure modes than retaining Codex's working native boundary.

Explicit approval policy `never` is consistent with a headless workflow, but its
purpose must be clear: necessary vault reads already succeed inside the native
sandbox. Denied operations outside the write boundary do not become approved.

## Provider parity and user intent

The user's statement clearly authorizes directly reading vault notes. The present
Claude implementation deliberately lists native `Read` among forbidden tools on
text-only turns and allows it only for image turns, where the vault is explicitly
removed from `--add-dir`. That behavior is a separate deterministic limitation,
not the cause of the user's actual Codex sandbox error.

Antigravity already has a measured native `read_file(*)` grant, but its chat policy
instructs the agent to use MCP for missing evidence and only mentions native reads
for explicitly supplied images. That wording should be examined for parity: native
vault source reads requested by a user should not be discouraged by a prompt rule.

Restoring Codex first is a legitimate scoped hotfix, but do not report that every
provider is now fixed or omit the known Claude limitation. Record a follow-up Arena
item for the remaining provider contract. Enabling Claude vault reads reverses an
explicit prior user-facing contract, so under this repository's release criteria
it should be planned as a separate capability release rather than silently included
in a patch. A follow-up should preserve Bash/Write/Edit/WebFetch denials, preserve
image access alongside vault access, and verify an actual permitted native read
under the installed Claude version rather than relying only on flag-string tests.
This does not require asking the user to approve their already explicit read intent.

## Required regressions and native evidence

1. Built Codex launch executes Codex directly, has exactly the selected native
   sandbox mode, and no `sandbox-exec` or `bwrap` outer prefix.
2. Sidechat vault is writable, Zotero/storage are absent from `--add-dir` and
   explicit writable roots, and caller-provided global writable roots cannot leak
   through. Paths containing spaces and symlinked vault roots remain valid.
3. Ephemeral launch remains read-only and has no vault write grant, including
   image-bearing calls and CLI fallback provider labels.
4. Claude and Antigravity retain their current wrapper and unavailable-wrapper
   behavior in this hotfix.
5. A real native sandbox probe in private sibling fixture directories reads an
   unindexed vault note and a Zotero-like reference, writes inside the intended
   vault when non-ephemeral, and fails writes to the reference and outside root.
6. The same native probe under ephemeral mode cannot write into the vault. Verify
   broad system tmp is not inadvertently writable while CLI operational temp is.
7. A model-backed sidechat smoke reads a unique marker from a private vault note;
   the completion must include the marker, not merely announce a successful read.

One attempted private native probe via `codex sandbox -c sandbox_mode=...` was
rejected before execution because this installed CLI's diagnostic sandbox command
requires a named permission profile. This does not invalidate the nesting probe;
it means the release needs a valid native-profile probe or an actual `codex exec`
smoke, not a claimed successful native permissions test based on that invocation.

## Documentation risks

Update the documentation that currently says every CLI is OS-wrapped; that Codex
`--add-dir` merely conveys read visibility; and that all providers share a single
outer write set. Keep read visibility and write grants separate in both comments
and docs. Do not silently change claims about Claude's text-only read denial in a
Codex-only patch. Existing source-string tests fossilize those old claims; replace
relevant ones with launch-behavior assertions so another unconditional wrapper
cannot satisfy a superficial text match while breaking native execution again.
