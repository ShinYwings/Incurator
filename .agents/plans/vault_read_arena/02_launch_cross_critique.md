# Critique on Independent Access and Containment Adversary
Date: 2026-09-21 | Agent Persona: CLI Runtime Engineer

## 1. Vulnerabilities & Flaws

The core proposal is accepted: a single native Codex sandbox fixes the measured
nested Seatbelt launch failure without sacrificing the existing sidechat write
capability. The insistence on removing Zotero from Codex `--add-dir` is mandatory,
not optional hardening. The installed CLI calls that option a write grant.

Two evidence qualifications must remain visible. First, the minimal nested
Seatbelt reproduction proves the mechanism and produces the identical error, but
does not recover the original failed request's raw trace. Second, `codex sandbox`
is a diagnostic interface whose configuration behavior differs from `codex exec`:
our legacy-flag probe allowed reads but denied even intended vault writes. A
passing direct-read diagnostic is insufficient evidence of preserved edit
capability. The proposed real `exec` qualification is the decisive release gate.

The remaining danger is accidentally allowing inherited permission state. An
empty `sandbox_workspace_write.writable_roots` override is a good minimal fix for
the observed legacy configuration shape, but source-string checks cannot prove
that another active named permission profile is dominated by `--sandbox`.
Use the installed CLI's effective state and actual writes in disposable fixtures
to settle that question. Do not broaden implementation speculatively to every
possible future configuration format. If an observed profile defeats the
intended write boundary, resolve that concrete case before releasing.

The phrase "only the vault" requires one more qualification: the CLI cwd and its
explicit temporary directory remain writable for existing operational needs.
An image directory is already under that cache; retaining its explicit root
argument is harmless but it must never turn an ephemeral call into workspace
write. A Zotero directory physically nested under the allowed vault overlaps the
existing broad vault write grant. Neither the old outer profile nor the proposed
native workspace grant makes that topology read-only; do not overclaim it.

The provider-parity diagnosis is correct and should remain in tracked work.
Fixing only Codex while telling the user all Obsidian agents can now directly read
all vault files would be inaccurate. Conversely, mixing Claude's intentionally
disabled Read tool into this patch adds a distinct contract reversal and makes
the confirmed production fix harder to qualify. A separate planned follow-up is
acceptable only if the parent continues it under the user's existing authorization
and reports the actual hotfix scope clearly.

## 2. Suggested Alternatives

Lock the smallest implementation to the executable branch already responsible
for Codex: construct Codex-specific write directories, pin approval and legacy
write-root/temp settings, and return that launch without entering the OS-wrapper
path. Apply it to all labels taking that exact branch, including CLI fallback
labels. Keep other provider launch behavior unchanged in this patch.

Replace the relevant source-string assertions with tests that inspect the built
command and argv. Required tests cover sidechat and both ephemeral policy values,
image-bearing calls, fallback labels, empty Zotero settings, and path
realpath/space handling. Verify the launch is directly `codex`, retains the
selected native mode, grants only vault/cache writes, clears inherited extra
roots, excludes broad `/tmp`, and retains explicit no-prompt behavior. Existing
AGY/Claude wrapper tests must keep passing.

For native qualification, have the actual plugin-built command read a random
marker from a disposable unindexed note and an external reference, successfully
write a file in the disposable vault, and attempt writes to disposable external
reference and unrelated sibling locations. The last two must fail. Repeat under
read-only with the vault write failing. Add an unrelated inherited writable root
to disposable configuration and demonstrate that it is still denied. These
checks must exercise the actual `exec` invocation, not a re-created approximation
of the intended arguments or the diagnostic sandbox command. Parent owns this
bounded model-backed smoke so the Arena does not duplicate it.

Consensus: native-only Codex launch is the root repair; no danger-full-access
mode, no global permission changes, no unsandboxed retry, and no user access
question. Native evidence and matching docs/tests are required before release.
