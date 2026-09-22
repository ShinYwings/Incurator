# Independent implementation review — PR #210

Date: 2026-09-21. Reviewed implementation commit `a44962fb` against base
`f184c99d`. Scope: measured root cause, containment and capability regressions,
changed launch tests, and matching guide/spec changes. This is an additional
adversarial review; the parent separately invoked the actual code-review skill.
No application or production data edits were made by this reviewer.

## Findings

No introduced actionable finding meeting confidence >=80 was found in this
bounded review. This is not a claim that every provider's vault-reading behavior
is fixed; the remaining Claude/AGY parity work is explicitly retained in the plan
and roadmap.

## Evidence checked

- The Codex switch branch returns the command directly before the common OS
  wrapper. The shared OpenAI/DeepSeek/Ollama branch makes the fix apply to every
  existing Codex-backed CLI label. Claude and Antigravity still flow through
  the original wrapper.
- Sidechat builds writable arguments from `sandboxWriteRoots()` rather than
  `allowedRoots()`, removing the external Zotero roots from Codex's write grants.
  The scoped chat image path remains plugin-created under the CLI cache.
- Per-invocation overrides clear inherited legacy writable roots, exclude broad
  `/tmp`, and pin headless approval policy. The command retains `workspace-write`
  for normal sidechat and `read-only` for both ephemeral policies. Neither native
  full-access mode nor an unrestricted retry was introduced.
- Both streaming and non-streaming callers still supply `getCliCwd()` as cwd and
  use `getAugmentedEnv()`, preserving the cache-local temporary directory and
  existing stdin/output-file behavior.
- Regression tests invoke the real builder and make any wrapper dispatch throw.
  They exercise all three Codex-backed labels, an image-bearing sidechat, a path
  containing spaces, and both ephemeral modes. The source-level existing tests
  are no longer the sole evidence that the launch bypasses the outer wrapper.
- Independently inspected the completed `command_execution` events in the parent
  fixture logs, not only the final model response:
  `.cache/vault-read-live/exec-auto.log`, `exec-none.log`, and
  `exec-inherited.log`. In all three runs both unindexed-note and reference
  markers were actually read with exit 0. Normal and inherited-config sidechat
  runs wrote the vault fixture with exit 0 and received `Operation not permitted`
  for the external-reference and sibling writes. The read-only run received
  `Operation not permitted` for all three write attempts, including the vault.
  These traces complete the runtime qualification missing during the original
  Arena; they contain native tool results instead of mere asserted capability.
- Changed English and Korean guide text agree on the Codex-only repair, retained
  ephemeral policy, external Zotero protection, invocation-local overrides, and
  removal of the outer wrapper. Plugin spec text includes the nested-Zotero
  topology caveat and the separate external-MCP trust boundary. The old explicit
  Claude Read restriction is not misrepresented as fixed.
- Version manifest edits agree on the patch line `0.82.9`, and the changelog
  contains a Fixed entry. No schema or user-data migration is introduced.

## Bounds and remaining release work

Actual native exec behavior was inspected on the installed macOS Codex version.
This review does not independently qualify Linux or Windows enforcement, nor all
possible future Codex configuration schemas. It does not independently rerun the
full repository test suite, which the parent owns. Release mechanics must still
wait for the actual skill review, required local/remote CI, and cleanup. The
provider-parity follow-up remains authorized work after this incident patch.
