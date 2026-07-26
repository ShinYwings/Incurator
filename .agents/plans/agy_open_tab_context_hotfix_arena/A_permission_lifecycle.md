# Permission Lifecycle Domain Analysis

Date: 2026-07-26

## Design Constraints From The Codebase

- `syncAgyHeadlessReadPermission()` atomically merges only
  `$read_file$()` into the CLI-owned Antigravity settings and preserves unknown
  fields (`plugin/src/agent/llm/LLMClient.ts:52-125`).
- Every Antigravity CLI command calls the sync before spawn
  (`LLMClient.ts:1889-1907`, `2222-2250`).
- `setup.sh` and the in-plugin update action copy new bundle files but only print
  or display a reload instruction (`setup.sh:29-40`, `plugin/main.ts:1276-1297`).
- The current update banner changes its label to `Restart Required`, but a second
  click repeats the copy path instead of reloading the renderer.
- Static security contracts prohibit blanket permission bypasses and keep path
  visibility separate from tool approval.

## Alternatives And Trade-offs

### A. Restore `--dangerously-skip-permissions`

Rejected. It grants unrelated write/shell/network tools and violates the locked
v0.23.0 sandbox contract.

### B. Rewrite Antigravity settings from `setup.sh`

Rejected as the primary fix. It would mutate a user security setting even on
machines that build but never run Antigravity, duplicate the TypeScript merge
implementation, and still would not prove which plugin bundle is active.

### C. Re-run the same permission merge at plugin startup

Useful only as defense-in-depth, but not a root fix: a stale pre-v0.36.4 bundle
cannot execute new startup code. It also broadens when the plugin mutates the
CLI settings. The invocation-time merge remains the least-privilege boundary.

### D. Detect disk/runtime bundle divergence and require a real reload

Selected. Compare the active runtime manifest/build fingerprint with the
installed bundle on disk. If they differ, block provider launch with an
actionable reload state. After the update action copies files, its button must
perform a real renderer/plugin reload rather than merely changing its label.

## Final Decision

- Keep the v0.36.4 permission merge unchanged unless a failing test proves a
  defect in it.
- Add a testable runtime-versus-disk bundle check.
- Fail before provider startup when a newer/different installed bundle is not
  active.
- Convert the successful update banner to an actual `Reload Obsidian` action.
- Make `setup.sh` state explicitly that the running process still executes the
  old code until reload.
- Keep malformed Antigravity settings fail-closed and visible to the user.

## Implementation Pseudocode

```ts
type PluginReloadState =
  | { required: false }
  | { required: true; runtimeVersion: string; installedVersion: string };

function comparePluginBundle(runtimeManifest, installedManifest):
    parse installed manifest without replacing malformed files
    return required when version/build identity differs

beforeSidechatProviderLaunch():
    state = plugin.getReloadState()
    if state.required:
        throw actionable ReloadRequiredError

updateButton():
    if phase == "copy":
        copied = copy all required artifacts
        if copied != requiredCount: fail without reload
        phase = "reload"
        label = "Reload Obsidian"
    else:
        execute the supported Obsidian renderer reload command
```

