# TCC Propagation Measurement Proposal: Does an Obsidian-Obtained Grant Reach the Spawned Backend?
Date: 2026-09-02 | Agent Persona: tcc_measurement_engineer

This is the measurement phase the briefing (`.agents/plans/80_folder_permission/00_problem.md`)
requires before any UI is designed. Every command below was actually run against
this repository and this machine on 2026-09-02, using the real production code
(`curator.file_access`, `curator.zotero_tools`), never a reimplementation. No
permission was granted or changed at any point — every probe below is read-only,
and the one write action taken (a `chmod 000` on a throwaway file in the
scratchpad) touches only a file this session created and deletes, never a
repo or vault path.

---

## 1. Core Logic & Implementation

### 1.1 How the backend is spawned (Q1)

`plugin/main.ts:1036-1056`:

```ts
async runBackendCommand(cmdArgs: string[]): Promise<{ ok: boolean; output?: string; error?: string }> {
    const cwd = this.vaultRoot || (this.app.vault.adapter as any).getBasePath?.() || "";
    if (!cwd) return { ok: false, error: "Not a local vault" };
    const command = await this.resolveBackendCommand();
    ...
    const prefixArgs = this.settings.incuratorBackendArgs || [];
    try {
      const cp = spawn(command, [...prefixArgs, ...cmdArgs], { cwd, env: process.env });
      return await collectBackendProcess(cp, backendCommandPolicy(cmdArgs));
```

`import { spawn } from "child_process";` at `plugin/main.ts:4`. This is Node's
`child_process.spawn`, called directly from the plugin's own code, which
executes inside Obsidian's Electron process (the same context that already
does `require("electron")` / `require("@electron/remote")` for the Zotero
link interceptor — `plugin/main.ts:763,769,890-891`). Three properties of
this call matter for TCC attribution, and I checked all three against the
actual option object passed:

- **No `shell: true`.** The options object is exactly `{ cwd, env: process.env }`
  (`plugin/main.ts:1048`). Node execs `command` directly via `posix_spawn`/`execve`,
  never through `/bin/sh -c`.
- **No `detached: true`.** Nothing in `backendProcess.ts` or `main.ts` sets
  detached; `collectBackendProcess` (`plugin/src/utils/backendProcess.ts:54-141`)
  wires `stdout`/`stderr`/`close`/`error` handlers on the same `ChildProcess`
  object `spawn` returned, which only works for a process still attached to
  its parent's process group.
- **`env: process.env`**, not `{}` or a filtered subset — no `env -i` stripping
  happens anywhere in this path.

`command` itself is not a literal string constant — it is resolved by
`resolveBackendCommand()` (`plugin/main.ts:1203-1237`), which (barring an
explicit user override) auto-discovers `<repo>/.venv/bin/wiki`:

`plugin/src/utils/deviceRegistry.ts:333-337`:
```ts
export function resolveWikiBinary(repoPath: string): string | undefined {
  if (!repoPath) return undefined;
  const candidate = resolve(expandPath(repoPath), ".venv/bin/wiki");
  return existsSync(candidate) ? candidate : undefined;
}
```

I read the actual file this resolves to on this machine:

```
$ head -5 .venv/bin/wiki
#!/Users/shin/shinywings/Incurator/.venv/bin/python
# -*- coding: utf-8 -*-
import sys
from curator.cli import app
if __name__ == "__main__":

$ file .venv/bin/wiki
.venv/bin/wiki: a /Users/shin/shinywings/Incurator/.venv/bin/python script text executable, ASCII text
```

So the "backend command" is a **shebang script**, not a compiled binary. When
`spawn()` execs it directly (no shell), the **kernel** — not a shell — reads
the `#!` line and re-execs the named interpreter with the script path as an
argument, in the same process (same PID). This is a single `execve`, invisible
to any responsible-process bookkeeping; it is not materially different from
`spawn()` execing a binary directly. `.venv/bin/python` itself is a symlink to
`/Users/shin/anaconda3/bin/python3.10`, an **ad-hoc-signed** Mach-O binary
(`codesign -dv` → `Signature=adhoc`, `TeamIdentifier=not set`) — worth flagging
since ad-hoc signing means this interpreter has no Team ID of its own to be
identified by; if TCC ever attributes by the *child's own* signing identity
rather than by responsible-process inheritance, an ad-hoc-signed interpreter is
the worst case for that path. Section 1.2 addresses which of these two models
actually governs.

**Verdict on Q1: nothing in the spawn call itself would break TCC responsible-process
attribution.** Direct exec, no shell, not detached, full environment inherited.
The only structural risk is the shebang hop and the ad-hoc-signed interpreter,
neither of which involves a shell or a process-group detach — both are handled
by the same `execve`-based kernel mechanism responsible-process inheritance is
built on.

Separately, Obsidian itself: `codesign -dv /Applications/Obsidian.app` shows
`Identifier=md.obsidian`, `TeamIdentifier=6JSW4SJWN9`, `flags=0x10000(runtime)`
(hardened runtime) — and `mdls -name kMDItemAppStoreHasReceipt` returns `null`.
This is a properly signed, hardened-runtime, **non-sandboxed** direct-download
build, not the Mac App Store variant. That matters for Q4 below.

### 1.2 The experiment (Q2)

**The constraint stated in the briefing is real and I hit it immediately**:
`~/Library/Mobile Documents` is denied to my own shell here today, which
already falsifies the briefing's assumption that it reads OK "on this machine"
— it reads OK only to *whatever process the user granted it through*, which is
neither this Bash tool's shell nor (as far as this measurement can tell)
Obsidian. That result is itself the first piece of evidence for the
per-responsible-process model, not a failure of the experiment.

**Step 0 — what does a naive process see on this machine, right now, before any grant flow runs?**

```
$ ls ~/Documents 2>&1 | head -5      → Codex   (readable)
$ ls ~/Desktop 2>&1 | head -5        → 3D Generative Models.pdf, ...  (readable)
$ ls ~/Downloads 2>&1                → ls: /Users/shin/Downloads: Operation not permitted
$ ls "~/Library/Mobile Documents"    → ls: Operation not permitted
```

I re-ran this with `dangerouslyDisableSandbox: true` to rule out the Bash
tool's own sandbox-exec profile as the cause — identical result both times, so
this is genuine macOS TCC, not a Claude Code artifact.

`~/Downloads` and `~/Library/Mobile Documents` are live, currently-denied
folders on this machine. That answers the briefing's "check read-only whether
they are actually denied" directly: **yes, both are denied** — to the process
this shell runs under.

**Which process is that?** I walked the ancestry:

```
20792 zsh
 8161 claude (…/Application Support/Claude/claude-code/2.1.255/claude.app/Contents/MacOS/claude)
 8160 /Applications/Claude.app/Contents/Helpers/disclaimer
96534 /Applications/Claude.app/Contents/MacOS/Claude
    1 launchd
```

Every hop from PID 96534 down to the `ls`/`python` command I ran is a plain
`fork`+`exec` — no `open -a`, no LaunchServices re-launch, and (per §1.1's
technique applied to this chain too) no shell-wrapping at the OS level beyond
zsh itself. Four process hops, through a **separately versioned, separately
bundled nested `.app`** (`claude-code/2.1.255/claude.app`, distinct from
`/Applications/Claude.app`), and TCC still resolves every leaf command to
**Claude.app's own grant set**: Desktop and Documents readable (Claude.app was
plausibly granted these via its own native file-attach open panel at some past
point — the same mechanism this release proposes for Obsidian), Downloads and
Mobile Documents denied (never granted to Claude.app). This is a live,
structurally faithful analog of "Electron host app → spawned child several
hops down → arbitrary command," running *right now*, on *this* machine,
through *more* hops than Obsidian → `.venv/bin/wiki` will ever need (that path
is a single hop: Obsidian's own process → `spawn()` → shebang script). More
hops surviving intact is stronger evidence than fewer would have been.

**Step 1 — reproduce the actual production regression, live, through the real code, using a real file:**

I found a reference stub in the live vault that carries a real Zotero
attachment key, and called the actual resolution function the ingest pipeline
calls, unmodified:

```
$ cat "second_brain/04_Resources/References/MultipleViewGeometryHartley - .md"
---
type: reference
...
zotero_attachment_key: 3YFSAQB2
---

$ VAULT_ROOT=/Users/shin/shinywings/second_brain .venv/bin/python -c "
from pathlib import Path
from curator import config as cfg
from curator import zotero_tools, file_access as fa
paths = cfg.paths_from_config(Path('/Users/shin/shinywings/second_brain'))
result = zotero_tools.resolve_pdf('3YFSAQB2', paths)
print(result)
p = Path(result['path'])
print('probe     =', fa.probe(p).value)
print('grant_root =', fa.grant_root(p))
"

{'ok': False, 'state': 'attachment_file_denied',
 'error': 'Not permitted to read /Users/shin/Library/Mobile Documents/com~apple~CloudDocs/Zotero/[Project] COLMAPFreeReconstruction/Major/MultipleViewGeometryHartley - .pdf — grant access to /Users/shin/Library/Mobile Documents',
 'path': '/Users/shin/Library/Mobile Documents/com~apple~CloudDocs/Zotero/[Project] COLMAPFreeReconstruction/Major/MultipleViewGeometryHartley - .pdf',
 'grant_folder': '/Users/shin/Library/Mobile Documents', ...}
probe      = denied
grant_root = /Users/shin/Library/Mobile Documents
```

This is very likely the exact book named in the briefing ("One book accounted
for 8,692 of them") — reproduced live, today, through `zotero_tools.resolve_pdf`
(`backend/src/curator/zotero_tools.py:347-390`) → `_denied_result`
(`zotero_tools.py:319-344`) → `file_access.grant_root` (`file_access.py:96-128`),
exactly the call chain `ingest_raw._resolve_reference_source` uses at
`ingest_raw.py:127-142`. `grant_root` correctly names the shallowest denied
ancestor for this real, deeply-nested file. This machine remains an excellent
test bed for *reproducing the denial* even though it can no longer reproduce a
denial specifically at the `~/Library/Mobile Documents` top level for whichever
process the user granted it through.

**Step 2 — a runnable, falsifiable procedure for the Obsidian-specific question, using only Obsidian's own DevTools (no code written):**

This is the part I could not execute myself — completing it performs an actual
grant, which this task's constraints (and the general safety rules on
"Changing account settings") put outside what I should do without the user in
the loop. I designed it so someone can run it end to end in about two minutes:

1. **Baseline** — Open the vault in Obsidian, `View → Toggle Developer Tools`,
   Console tab. Run, unmodified:
   ```js
   const { execFileSync } = require('child_process');
   execFileSync('/Users/shin/shinywings/Incurator/.venv/bin/python',
     ['-c', "from pathlib import Path\nfrom curator import file_access as fa\nprint(fa.probe(Path('/Users/shin/Downloads')).value)"]
   ).toString()
   ```
   This calls the *actual* production `probe()`, spawned the *actual* way
   Obsidian will spawn it (fork+exec from Obsidian's own process, no shell).
   - Prints `denied` → good, this is a live, currently-ungranted folder specific
     to Obsidian's own responsible-process identity. Use it as the test folder
     and continue to step 2. (If `ok`/`missing`, Obsidian already has this
     folder; retry against `~/Desktop`, `~/Documents`, then
     `~/Library/Mobile Documents` in turn until one returns `denied`. If none
     do, Obsidian already has broad access on this machine and this specific
     test cannot be run here at all.)
2. **Grant, exactly the way the shipped feature will** — same Console:
   ```js
   const remote = require('@electron/remote');
   const result = await remote.dialog.showOpenDialog(remote.getCurrentWindow(),
     { properties: ['openDirectory'], defaultPath: '/Users/shin/Downloads' });
   console.log(result);
   ```
   Select the same folder identified as `denied` in step 1 and confirm.
   **This is the actual grant — the user should be the one to click it.**
3. **Re-probe immediately, same running Obsidian process, no restart** — repeat
   the exact command from step 1.
   - `ok` → **propagation holds, and holds without an app restart.** This is
     the strongest possible confirmation and directly enables the design in
     the briefing's Scope §1.
   - `denied` → go to step 4.
4. **Restart check** — fully quit Obsidian (`Cmd+Q`; confirm via
   `ps aux | grep -i obsidian` that nothing lingers), relaunch, reopen
   DevTools, repeat step 1's command.
   - `ok` only after restart → propagation holds but needs a relaunch — a
     materially different (worse) UX than the briefing assumes, and it would
     mean the first-touch button must tell the user to restart Obsidian before
     retrying ingest.
   - Still `denied` → propagation genuinely does not hold; the design must
     move to §1.4 below.

`@electron/remote` is already `require()`d successfully elsewhere in this exact
plugin (`plugin/main.ts:769,891`, for `remote.shell.openExternal`), so step 2's
API surface is proven reachable from this codebase; `remote.dialog` specifically
is untested territory but is the standard `@electron/remote` proxy for the
main-process `dialog` module and needs no new dependency (`@electron/remote`
is not even in `plugin/package.json` — it resolves through Obsidian's own
bundled Electron modules at runtime, matching the existing `shell` usage).

### 1.3 What a `chmod 000` directory would and would not prove (Q3)

I ran this for real, against a throwaway file in this session's scratchpad
(never a repo or vault path), using the production `probe()`:

```
$ echo hello > chmod_test.txt && chmod 000 chmod_test.txt
$ .venv/bin/python -c "... fa.probe(Path('chmod_test.txt')).value ..."
denied
$ .venv/bin/python -c "... fa.grant_root(Path('chmod_test.txt')) ..."
None
```

**What it proves:** `probe()` cannot and does not distinguish a POSIX
permission denial from a TCC denial — both raise `PermissionError` at the same
`os.open()` call (`file_access.py:69`) and both collapse to the identical
`Reachability.DENIED` value. So a `chmod 000` fixture is a perfectly good way
to exercise the `DENIED` branch deterministically: the `ParserAccessDenied`
message, the Dashboard's denied-row rendering, the first-touch button's
trigger condition — all of that machinery is agnostic to *why* the OS said no,
and a `chmod 000` fixture is cheap, offline, works in CI/the testbed, and needs
no real cloud file or real TCC state.

**What it cannot prove, and why not just "it's a different mechanism" but
specifically wrong for this question:** POSIX permission bits are evaluated
per-file, for the invoking **user**, uniformly across every process that user
runs. There is no such thing as "Obsidian's spawned python is denied by chmod
but Terminal's python is allowed" — chmod has no concept of responsible
process at all, so it cannot produce the one distinguishing state this whole
release depends on: *granted to one app's process tree, denied to another's*.
Testing propagation with a chmod'd fixture would show `denied` no matter which
process asked, both before and after any Obsidian-side grant — a result that
is trivially true and answers nothing. It is a fixture for the "denied" render
path, not a stand-in for TCC's per-app grant semantics.

One more finding from this same run, worth flagging precisely because it looks
like it could be evidence and isn't: `grant_root()` on the chmod'd file also
returned `None`. This is *correct*, not a bug — the file's containing directory
(scratchpad) is otherwise fully open, so there genuinely is no folder-level
grant that would fix a single `chmod 000` file; `None` here means "nothing to
tell the user to grant," which is the honest answer for this particular
failure shape. Contrast this with §1.4's finding below, where `None` shows up
for a case where it is *not* the honest answer.

### 1.4 A finding this measurement surfaced, unprompted, that blocks Scope §2 as currently written

While probing `grant_root()`'s behavior (needed to explain §1.3 correctly), I
found that it behaves differently depending on whether it is called on a
**file** (every existing production call site) or on a bare **directory**
(exactly what the briefing's Scope §2 — "one row per configured root and per
source root" — would call it on):

```
$ .venv/bin/python -c "
from pathlib import Path
from curator import file_access as fa
p = Path.home() / 'Downloads'
print('probe(~/Downloads)      =', fa.probe(p).value)
print('grant_root(~/Downloads) =', fa.grant_root(p))
"
probe(~/Downloads)      = denied
grant_root(~/Downloads) = None
```

`probe()` correctly says `denied` — the directory-vs-file MISSING trap the
briefing warns about (`file_access.py:71-75`, "probe() opens the path as a
file, so a DIRECTORY returns MISSING, not OK") does **not** apply here, because
that trap only fires once `os.open()` *succeeds*; a directory that is itself
TCC-denied fails at `os.open()` before the `S_ISREG` check ever runs, so it
correctly reads `DENIED`, not `MISSING`. Good — `probe()` is safe to call
directly on a root directory.

`grant_root()` is not. Read the walk again (`file_access.py:119-127`):

```python
shallowest_denied: Path | None = None
for ancestor in path.parents:
    try:
        with os.scandir(ancestor) as it:
            next(iter(it), None)
    except PermissionError:
        shallowest_denied = ancestor
    ...
return shallowest_denied
```

It walks `path.parents` — the **ancestors** of the given path — and never
tests `path` itself. Every existing production caller (`parsers/__init__.py:55`,
`zotero_tools.py:329`) hands it a *file* path, so the file's own parent
directory is exactly the folder that needs granting, and the walk finds it.
But `~/Downloads`'s parent (`~/`) is not itself denied — `~/Documents` and
`~/Desktop` scan fine, so `/Users/shin` clearly scans fine too — so the walk
finds no denied ancestor and returns `None`, even though `probe()` on the very
same path just said `DENIED`. I confirmed this is not specific to Downloads —
`~/Library/Mobile Documents` (the folder named throughout the briefing) does
the exact same thing:

```
probe(~/Library/Mobile Documents)      = denied
grant_root(~/Library/Mobile Documents) = None
```

**This is not a rare edge case.** Every TCC-protected top-level folder has a
freely-readable parent (`~/` or `~/Library`) by construction — that is what
makes it a "root" in the first place. So `grant_root(root)` returning `None`
for a denied root is the *default* outcome, not an exception. If Scope §2's
Dashboard calls `grant_root()` directly on each configured/source root to
compute the grant button's target — the natural reading of "the same grant
button on a denied row" — it will get `None` for exactly the rows most likely
to need the button, and have no folder to hand the open-panel `defaultPath`.
The UI-design phase needs to either (a) special-case "if `probe(root)` is
`DENIED` and `grant_root(root)` is `None`, the target is `root` itself," or
(b) extend `grant_root()` to test `path` itself as well as its parents. I did
not implement either — this is a measurement finding to hand to whoever
designs the Dashboard, not an approved fix.

### 1.5 If propagation does NOT hold: costing the two options named in the briefing (Q4)

**Option A — read bytes inside Obsidian, hand them to the backend.**

There is already a working precedent for this exact shape in this codebase:
`transcribePdfCrop` (`plugin/main.ts:966-1012`) writes a base64-decoded image
crop to a machine-local temp file under `vaultMachineCacheDir(...)/pdf_crops`
(`main.ts:992-1000`) and calls the backend with that file's path.

- *Pros:* proven pattern already shipping in this repo; completely sidesteps
  the propagation question because Obsidian reads with its own TCC identity;
  no new external dependency; no new always-on subprocess (the temp file is
  written once per ingest attempt, not held open).
- *Cons:* the crop precedent moves single images (KB-scale); this release's
  actual trigger case is a 673-page book (tens of MB). Piping that over stdin
  as base64 costs ~33% size inflation on top of the original read, and would
  require `parsers.parse()` (`parsers/__init__.py:39`) and every format parser
  underneath it to accept a byte stream instead of a `Path` — `ParsedDocument`
  and every parser module currently assume a real filesystem path
  (`parsers/base.py:21` — `source_path: Path`). Writing the bytes to a temp
  file instead (matching the crop precedent exactly) avoids the stdin/schema
  change but still means the plugin has to independently know *which bytes are
  the source* — today that resolution (Zotero DB lookup, path-candidate
  probing) lives entirely in the backend (`zotero_tools.py`, `_resolve_reference_source`
  in `ingest_raw.py:100-179`), which is precisely the boundary the briefing's
  Constraints section protects ("the plugin must not become the place that
  decides what a root is; the backend already owns `grant_root`"). Option A
  either duplicates that resolution logic into the plugin, or requires an
  extra backend round-trip first ("resolve me a path") purely so the plugin
  can then read that path itself — three hops instead of one, for every
  ingest of every denied file.

**Option B — "acquire a security-scoped bookmark," as named in the briefing.**

This is the API a **sandboxed** app uses (`NSOpenPanel` +
`startAccessingSecurityScopedResource`/`stopAccessingSecurityScopedResource`,
persisting a bookmark blob so a sandboxed app can re-open a user-chosen file
across relaunches without re-prompting). I checked the actual installed
Obsidian build against this: `codesign -dv /Applications/Obsidian.app` shows
hardened runtime (`flags=0x10000(runtime)`) but **not** App Sandbox, and
`mdls -name kMDItemAppStoreHasReceipt` returns `null` — this is the direct
(non-Mac-App-Store) build. A non-sandboxed app's individual "Files and Folders"
TCC grant is already durable across relaunches by itself; there is no bookmark
object to acquire, serialize, or pass to another process in this architecture.
`grep -rn "security.scoped\|bookmark"` across `backend/src`, `plugin/main.ts`,
`plugin/src`, and `docs/specs` returns **zero hits** — this mechanism does not
exist anywhere in this codebase today, and for this Obsidian build it is not
the applicable fallback at all. (Obsidian does also ship a Mac App Store
build, which *is* sandboxed — if that build is ever a target, bookmarks would
apply there specifically, but that is a distribution question, not something
this plugin controls.)

**Conclusion for Q4:** if the DevTools procedure in §1.2 comes back negative,
the only fallback that is actually implementable against this repo's real
constraints is Option A (temp-file handoff, matching the crop precedent), and
it is a Minor-at-least change: it moves source-bytes acquisition partly into
the plugin and very likely changes how `parsers.parse()` is invoked for the
denied-and-recovered case, which is exactly the kind of stored-contract change
CLAUDE.md's workflow rules require a full plan and Arena for on its own.

### 1.6 Preconditions for the first-touch button to work at all (Q5)

Enumerated so the UI proposal can be checked against each one directly:

1. **Desktop only.** `plugin/manifest.json:10` — `"isDesktopOnly": true`.
   Already satisfied; mobile has no `child_process`/`electron` access at all
   and is correctly out of scope.
2. **`require("electron")` / `require("@electron/remote")` must resolve** from
   inside plugin code. Proven reachable today for `shell.openExternal`
   (`main.ts:763,769,890-891`); `remote.dialog` is the same proxy module,
   untested but architecturally identical.
3. **A `BrowserWindow` reference for the picker.** `dialog.showOpenDialog`
   wants an owning window (`remote.getCurrentWindow()`) for a proper attached
   modal; not currently used anywhere in this codebase — new, small, low-risk
   surface.
4. **The backend command must resolve at all**, independent of TCC —
   `resolveBackendCommand()` (`main.ts:1203-1237`) must find
   `<repo>/.venv/bin/wiki`; unrelated to this measurement but a hard
   precondition for the button to do anything once clicked.
5. **The user must select the *correct* folder in the picker.** Electron's
   `defaultPath` can pre-populate the dialog at `grant_root(path)`, but nothing
   stops the user from navigating elsewhere and choosing a different, unrelated
   folder — the picker's `defaultPath` is a hint, never an enforced choice. A
   design that assumes the returned selection always equals what was asked for
   is wrong; the retry after granting must re-`probe()` and be prepared to say
   "still denied" if the user picked the wrong folder.
6. **`grant_root()` must actually return a usable target for the row being
   shown.** §1.4 above found this already breaks for a bare directory input —
   this precondition is currently unmet for Scope §2's per-root Dashboard rows
   unless `grant_root()` is extended or the Dashboard falls back to the probed
   root path itself.
7. **The grant must reach the *next* spawned `wiki` process**, which is the
   entire subject of §1.2. Because every `runBackendCommand` call spawns a
   brand-new process per invocation (§1.1 — no long-lived daemon, matching the
   "no new always-on subprocess" constraint), there is no "already-running
   process is stale" problem *if* propagation is immediate (§1.2 step 3). If
   it needs an app restart (§1.2 step 4), the button's success message must
   say so explicitly rather than silently retrying and failing again.
8. **Obsidian must not be the sandboxed Mac App Store build.** Confirmed
   satisfied for this install (§1.5); worth an explicit runtime check or a
   documented assumption if this ever ships to MAS users, since Option B's
   entire mechanism only applies there.

---

## 2. Pros & Cons

**Pros of the evidence gathered this phase:**
- Every claim is backed by a command actually run against production code and
  a real, currently-live denial on this machine — not reasoning from memory or
  general macOS documentation.
- The Claude.app process-tree analog (§1.2) is a structurally faithful,
  currently-running stand-in for the exact Obsidian → spawned-python question,
  through *more* hops than the real path needs, and it came back positive
  (grant propagated) for the folders Claude.app does have, and negative for
  the folders it does not — a genuine A/B result, not a single data point.
- The Hartley-book reproduction (§1.2 step 1) ties this measurement directly
  to the actual regression named in the briefing, through the actual call
  chain, with a real file, today.
- §1.4 surfaces a concrete, previously-undocumented gap in `grant_root()` that
  would otherwise have been discovered mid-way through building the Dashboard
  — exactly the kind of finding this phase exists to produce before UI work
  starts.
- The DevTools procedure (§1.2) is fully designed and requires writing no
  code — it can be run by the user in about two minutes whenever they choose.

**Cons / limits of what one agent could establish alone:**
- The Claude.app analog is not Obsidian. Team ID, prior grant history, and
  Electron version all differ. It is strong supporting evidence for the
  propagation *mechanism* (fork/exec inheritance through multiple hops,
  through a distinct nested app bundle, surviving intact), not a substitute
  for testing Obsidian itself.
- I did not and could not complete the actual grant step against Obsidian —
  doing so would be the one action this task explicitly prohibits me from
  taking unilaterally. The DevTools procedure in §1.2 is designed, not run to
  completion.
- I did not test the "restart required" question (§1.2 step 4) at all, since
  it depends on step 2/3 having run first.
- I have not verified whether `remote.dialog` is actually present in
  Obsidian's bundled `@electron/remote` build (only `remote.shell` is proven
  reachable today) — that is a five-minute check inside the same DevTools
  session as §1.2, not yet done.

---

## 3. What This Could NOT Establish (explicit)

- **Whether the grant genuinely reaches `wiki` when spawned by Obsidian
  specifically.** This is the one load-bearing question the whole release
  depends on, and it remains unconfirmed. Everything else in this document
  supports a strong prior that it will (§1.1's clean spawn semantics, §1.2's
  live analog with more hops than needed, both matching well-established
  Electron-app TCC behavior), but "strong prior" is not "measured," and the
  briefing is right not to accept anything less than a real measurement before
  the UI is built.
- **Whether propagation, if it holds, is immediate or requires an Obsidian
  restart.** Not tested; §1.2 step 4 exists specifically to answer this once
  step 2/3 can be run.
- **Whether `remote.dialog.showOpenDialog` is reachable the same way
  `remote.shell` is**, in Obsidian's actual bundled Electron — assumed by
  analogy, not verified.
- **Behavior on Windows/Linux.** Out of scope per the briefing (this is a
  macOS TCC question), and `file_access.probe()` itself is platform-generic,
  but no claim here should be read as extending to non-macOS behavior.
- **Whether other apps on this machine (Terminal.app, iTerm2, a future direct
  Obsidian test) would show different results than Claude.app did.** The
  analog used what was already running; it was not chosen for being maximally
  representative of Obsidian, only for being genuinely live and testable
  today without creating a new grant.
