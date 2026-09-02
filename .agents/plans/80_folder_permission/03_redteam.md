# Red Team — v0.80.0 "Incurator knows which folder to ask for and never asks"

Role: `permission_redteam`. Angle: adversarial — attack the premises before
anyone builds. Every claim below is grounded in a file:line citation, a quoted
live command, or is explicitly marked unknown. No implementation code was
written into the repo. No permission was granted, changed, or reset — every
probe below is read-only, and the two synthetic `chmod 000` fixtures used to
isolate specific code paths were created under this session's own scratchpad
(`/private/tmp/claude-501/.../scratchpad/`), never under the repo or the vault,
and were deleted immediately after each test (`chmod 755` then `rm -rf`, shown
in the transcript for each).

---

## 1. Is `grant_root` actually right?

**No — it has three distinct, independently reproduced failure modes.** The
mechanism `grant_root` uses (`backend/src/curator/file_access.py:119-127`) is:

```python
shallowest_denied: Path | None = None
for ancestor in path.parents:
    try:
        with os.scandir(ancestor) as it:
            next(iter(it), None)
    except PermissionError:
        shallowest_denied = ancestor
    except OSError:
        continue
return shallowest_denied
```

This walks `path.parents` — the **ancestors** of the path — and never once
inspects `path` itself. That asymmetry is invisible for the shape the function
was built and measured against (a *file* sitting inside a denied folder), and
it is a real bug for two other shapes that occur in this exact codebase.

### 1a. The leaf path itself is the denied node (confirmed live, no synthetic needed)

Read-only probes against real folders on this machine, using the actual
production functions (`.venv-dev/bin/python3`, `from curator import
file_access as fa`):

```
probe(/Users/shin/Documents)              -> missing
probe(/Users/shin/Desktop)                -> missing
probe(/Users/shin/Downloads)              -> denied
probe(/Users/shin/Library/Mobile Documents) -> denied
probe(/Users/shin/shinywings/Incurator/testbed) -> missing
probe(/Users/shin/shinywings/Incurator)   -> missing
probe(/nonexistent/path/does/not/exist.pdf) -> missing

grant_root(/Users/shin/Documents)              -> None
grant_root(/Users/shin/Desktop)                -> None
grant_root(/Users/shin/Downloads)              -> None
grant_root(/Users/shin/Library/Mobile Documents) -> None
grant_root(/Users/shin/shinywings/Incurator/testbed) -> None
grant_root(/Users/shin/shinywings/Incurator)   -> None
grant_root(/nonexistent/path/does/not/exist.pdf) -> None
```

`~/Downloads` and `~/Library/Mobile Documents` both probe as **DENIED as
directories** — this shell's TCC identity cannot even `open()` them (confirmed
separately: `os.scandir(~/Downloads)` and `os.scandir(~/Library/Mobile
Documents)` both raise `PermissionError: [Errno 1] Operation not permitted`
directly, in this same process). Yet `grant_root()` on those exact two paths
returns `None` — "nothing needs granting" — for the two folders that are, at
this moment, on this machine, actually denied. The bug: `grant_root(root)`
walks `root.parents` (`/Users/shin`, `/Users`, `/`), all of which list fine,
and never checks whether `root` itself is the denied node.

Isolated synthetically to rule out any confound from `~/Downloads`/`~/Library`
being special TCC categories (fixture created and destroyed inside the
scratchpad only, `chmod 000` then `chmod 755` + `rm -rf` immediately after):

```
Case A: probe/grant_root on the FILE inside a chmod-000 folder (normal case)
probe(leaf) -> Reachability.DENIED
grant_root(leaf) -> .../scratchpad/denytest/deniedroot        # CORRECT

Case B: probe/grant_root on the DENIED DIRECTORY itself
probe(root) -> Reachability.DENIED
grant_root(root) -> None                                       # WRONG
```

Case A (a file inside a denied folder — the shape `grant_root`'s docstring and
cost comment were written against) works correctly: this is real, verified,
and is also the shape the actual July/August incident hit (7 PDFs inside
`~/Library/Mobile Documents`, per `00_problem.md`). Case B is a clean,
reproducible bug: **when the thing being probed is itself the denied
directory — not a file inside it — `grant_root` returns `None`.**

This matters directly for the Dashboard tab in scope item 2 of the briefing
("one row per configured root and per source root, its `probe` verdict, and
the same grant button on a denied row"): if that tab calls `grant_root`
directly on a *root* path (which is exactly what "configured root" means —
`02_Wiki`, `03_Notes`, `04_Resources`, or an `external.path_roots` entry), and
that root itself is the denied node (plausible: `~/Library/Mobile Documents`
IS such a root candidate, and is denied-as-a-directory on this very machine
right now), the grant button on that row has nothing to point at. `grant_root`
must be called on a representative *file inside* the root, never the root path
itself, or it must be fixed to probe `path` in addition to `path.parents`.

### 1b. Symlinks (confirmed live, synthetic)

`Path.parents` does not resolve symlinks; `os.open()` (inside `probe()`) does.
Built and tore down in the scratchpad: a symlink in a normal, fully-readable
directory, pointing at a file inside a separate `chmod 000` directory.

```
Symlink lives in a normal, readable directory. Its TARGET is inside a chmod-000 folder.
probe(symlink_path) -> Reachability.DENIED
grant_root(symlink_path) -> None
symlink_path.parents -> [.../linktest/normal, .../linktest, .../scratchpad]
```

`probe()` is honest here — it follows the symlink via `os.open()` and correctly
reports DENIED. `grant_root()` is not: it walks the ancestors of the *symlink's
own path* (all in the harmless `normal/` directory), never the ancestors of
the resolved target, and returns `None`.

Whether this is *reachable* in production is a separate question from whether
it's a bug — it is a bug regardless. Reachability: I found no symlink-specific
handling anywhere in `zotero_tools.py`, `file_access.py`, or `path_refs.py`
(`grep -n "symlink\|is_symlink\|readlink" backend/src/curator/{zotero_tools,file_access,path_refs}.py`
returned nothing project-relevant). Zotero's own "linked attachment" feature
stores a path string in Zotero's DB, not necessarily a filesystem symlink, so
I cannot confirm this is what actually happened to the 7 denied sources in the
motivating incident — and the problem doc's own claim that `grant_root`
"verified on this machine, it returned `~/Library/Mobile Documents` exactly"
is independent evidence that the real incident's files were *not* behind a
symlink (Case A worked for them). But a symlinked Zotero storage folder or a
symlinked vault (both common workarounds people use to force Zotero/Obsidian
onto iCloud-synced storage) is a plausible way to trigger this on someone
else's machine. **Marking this "reachable in the wild: plausible, not
confirmed in this repo's own incident."**

### 1c. A folder that `scandir` succeeds on while its bytes are refused — does the docstring's claim hold?

The docstring says: "a folder can enumerate fine while the bytes beneath it are
refused; breaking early on the first successful listing would return `None`
for exactly the case this exists to describe." I read this claim narrowly and
it holds **for the walk's own purpose** (walking past a listable folder to find
a shallower one that is not) — but the live probes above show the opposite
failure mode is *also* real: a folder that does **not** even `scandir`
successfully (`~/Downloads`, `~/Library/Mobile Documents` on this machine) is
walked straight past too, just for the reason in 1a (only `path.parents` is
checked, never `path`). The docstring's claim about *why* the full walk is
needed is correct; it does not mention, and the code does not handle, the case
where the walk's own starting point is the denied node.

**Minor, unrelated to correctness:** `ParserAccessDenied`'s docstring
(`backend/src/curator/parsers/base.py:55-57`) cites catch sites at
`ingest_raw.py:2054`, `:2201`. The actual lines today are `2090` and `2240`
(confirmed by `grep -n`). Pre-existing drift, not introduced by this plan —
noting it because CLAUDE.md's docs-must-track-code rule would flag it if
touched.

---

## 2. Does the denial even reach the plugin today?

**No. This is the single most important finding.** I traced every call site
of `ParserAccessDenied` from where it is raised to what JSON, if any, reaches
`plugin/src`. Four independent paths, four independent losses of the
structured `grant_folder`, plus one path where it *is* structured and is dead
code on the frontend.

**Where it's raised:**
- `backend/src/curator/parsers/__init__.py:55` — `parsers.parse()`, the
  central dispatch every parser goes through.
- `backend/src/curator/parsers/pdf.py:160` — PDF-specific.
- `backend/src/curator/ingest_raw.py:139-142` — inside
  `_resolve_reference_source`, when Zotero resolution reports
  `attachment_file_denied`.

**Path A — `wiki add` / `ingest_raw.add_file` (the general ingestion path,
the one the actual incident's 7 PDFs went through):**
`ingest_raw.py:2087-2096`:
```python
try:
    resolved_source = _resolve_reference_source(paths, source)
    parsed = parsers.parse(resolved_source)
except parsers.ParserError as e:
    return AddOutcome(
        result=AddResult.ERROR,
        source_path=source,
        relpath=str(source),
        message=f"Parse failed: {e}",
    )
```
`AddOutcome` (`ingest_raw.py:47-61`) has fields `result`, `source_path`,
`relpath`, `title`, `file_type`, `bytes`, `word_count`, `content_hash`,
`source_id`, `context_id`, `message: str`. **There is no `grant_folder`
field.** `str(e)` on a `ParserAccessDenied` already renders as `"Not permitted
to read {path} — grant access to {grant_folder}"` (`parsers/base.py:64-68`),
so the folder text survives as a *substring of free-form prose*, prefixed with
"Parse failed:" — the exact framing `ParserAccessDenied` was created to avoid
(`parsers/base.py:59-61`: "wrapping this as a parse failure was actively
misleading"). A consumer that wants to build a folder-picker button from this
would have to regex a human sentence out of a field literally named `message`.
Second identical instance at `ingest_raw.py:2238-2246` (`import_source_file`,
`policy="reference"`), same pattern: `message=f"Parse failed: {exc}"`.

**Path B — `plugin source import` (the JSON-over-CLI boundary the plugin
actually calls):** `backend/src/curator/plugin_api/sources.py:174-196` calls
`ingest_raw.import_source_file(...)` and returns a dict whose only textual
field is `"message": outcome.message` — the same flattened prose from Path A,
now one hop further from the code that raised it. `commands/plugin.py:306-321`
wraps this in `try/except Exception as exc: _print_json({"ok": False, "error":
str(exc)})` — a second flattening layer that would apply if anything raised
past `import_source_file` (it doesn't, in this path, since `import_source_file`
already catches `ParserError` internally — but it means even a future leak
would still lose structure here).

**Path C — the one place `grant_folder` *is* carried structurally, and it's
dead on the frontend:** `zotero_tools.py:319-344`, `_denied_result()`, called
from `resolve_pdf()` when a Zotero attachment's file is found but refused:
```python
root = file_access.grant_root(Path(path))
return {
    "ok": False,
    "state": "attachment_file_denied",
    "error": f"Not permitted to read {path}" + (f" — grant access to {root}" if root else ""),
    "path": path,
    "grant_folder": str(root) if root else "",
    ...
}
```
This dict flows through `plugin_api/sources.py:159-166` (`"resolution":
resolved`, only when a Zotero-attachment-key import is requested) into the
plugin's own TypeScript type: `plugin/src/agent/incuratorClient.ts:92`:
```ts
/** Set with state="attachment_file_denied": the folder the user must grant.
 *  Carried explicitly rather than parsed back out of `error`, which is prose. */
grant_folder?: string;
```
The comment on this field explicitly names the exact disease Path A/B have —
and correctly avoids it. But:
```
$ grep -rn "grant_folder\|grantFolder" plugin/src
plugin/src/agent/incuratorClient.ts:92:  grant_folder?: string;
```
**That is the only hit in the entire plugin tree.** The field is declared,
populated by the backend, sent over the wire — and never read by any UI code.
I traced its one consumer, `ZoteroRepairModal`
(`plugin/src/ui/zoteroRepairModal.ts`), in full: `render()` displays
`this.resolution?.error` (prose), `this.status?.dbPath`, `.dataDir`,
`zoteroRepairCandidates()` (built from `rootsChecked`/`pathsChecked`, not
`grant_folder`), and a hardcoded generic string for the
`attachment_file_denied` state (`zoteroRepairModal.ts:30-33`):
```ts
case "attachment_file_denied":
  return "The PDF exists but this app is not permitted to read it. Grant access to its folder in System Settings → Privacy & Security → Full Disk Access, then restart.";
```
This is worse than merely "not reading the field" — it's the **exact
regression** `grant_root`'s own docstring says this repo already paid for once
("a table would have named `~/Library/CloudStorage`... sending the user to
change a setting that was never the problem"). Generic "go grant Full Disk
Access" is the same failure class with less information than a stale lookup
table: it doesn't even name a folder. The dashboard-adjacent System card
already has a click target for this exact modal
(`incuratorDashboardModal.ts:722-728`, the "Zotero" row), so this is not a
theoretical UI — real users hit `describeZoteroState("attachment_file_denied")`
today and are told to go to System Settings with no folder named, while the
correct folder sits unread in `this.resolution.grant_folder`.

**Path D — the search/index code the actual motivating incident ran through:**
`retrieval/materializer.py:212-229`, `_hydrated_span_texts`:
```python
try:
    from ..pipeline.compile import hydrate_spans
    return hydrate_spans(db_path, span_ids)
except Exception:  # noqa: BLE001 - degrade to previews, and say so
    ...
    "could not hydrate span text for the search index; "
```
and the summary at `materializer.py:616-622`:
```python
if preview_fallbacks:
    _LOG.warning(
        "search index: %d of %d spans could not be hydrated and were indexed "
        "from their 200-char preview",
        preview_fallbacks, len(spans),
    )
```
This is a **count**, logged, not a folder, not even prose containing a folder.
`MaterializeResult.preview_fallbacks` (returned to callers) is an `int`. This
is the actual code path that produced "10,176 of 11,774 spans" in the
briefing, and it discards the denial reason entirely — more thoroughly than
Paths A/B, which at least keep the folder as a substring somewhere.

**A fifth, silent path, found in passing:** `search.py:351-354`,
`search_source_pages` (used for provenance/page-number lookups):
```python
try:
    parsed = parsers.parse(file_path)
except Exception:
    continue
```
No log, no count, no message. A `ParserAccessDenied` here vanishes completely.

**Confirming the JSON the plugin dashboard actually polls has zero permission
data:** `commands/core.py:486-515`, `status(json_output=True)` returns
`{"status": build_status_snapshot(...), "sources": build_sources_snapshot(...),
"jobs": build_jobs_snapshot(...)}` and `return`s at line 515 — **before** line
633's `_report_unreadable_sources(paths, console)` call, which is the one
function in this codebase that already does per-root grouping correctly (see
§3 below) and is reached only in the plain-text, non-JSON branch of `status`.
`grep -rn "grant_root\|file_access\|ParserAccessDenied\|Reachability"
backend/src/curator/runtime_state.py` returns nothing — the module that builds
every JSON payload the plugin reads never touches this subsystem at all.

**Verdict on the briefing's claim ("`grep -r` over `plugin/src` for any of
this returns zero hits"):** technically false as literally stated — there is
one hit, `grant_folder?: string` in `incuratorClient.ts:92` — but the spirit
of the claim is correct and actually stronger than "nobody built this yet":
**somebody already built exactly this, for one call path, and it was wired to
nothing.** That is worse for the plan than a blank slate, because it means the
next implementer must (a) not duplicate `ZoteroPdfResolution.grant_folder`
with a second, parallel field for the general path, and (b) explicitly wire
`ZoteroRepairModal` to read the field that's already sitting there, or the new
"first-touch prompt" and the existing Zotero repair modal will tell the user
two different things (one generic-Settings, one folder-specific) for what may
be the same underlying denial.

---

## 3. Attack the Dashboard tab

**On a machine where nothing is denied:** a tab that is always green is a tab
nobody opens twice. The codebase already has the right precedent for this
shape and the plan should follow it, not invent a new one: the existing
"Zotero" row in the System card (`incuratorDashboardModal.ts:722-728`) is a
single line, `is-ok`/`is-warn` colored, click-through to detail only when
something needs attention. A **persistent tab** (the briefing's "Dashboard tab
for granted folders," a new entry in `TabId`,
`incuratorDashboardModal.ts:28`) is a heavier commitment than that pattern —
it's a permanent extra click in the tab bar for information that, on a fully
granted machine, is "everything is fine" forever. Recommend: a single
indicator (in Overview, next to or inside the existing System card) that
expands to a detail view only when there is at least one denied root, rather
than a standing seventh/eighth tab.

**On a vault with 49 sources across many folders:** whether this is "49 rows"
depends entirely on whether the new code groups by `grant_root`'s result or
not, and **both patterns already exist in this codebase, on opposite sides of
the plugin boundary**:
- `commands/core.py:_report_unreadable_sources` (413-475) does it right: it
  collects `(relpath, resolved_path, grant_folder)` tuples and groups by
  `grant_folder` (`by_root: dict[str, list[str]]`, line 457-459), so N denied
  sources under the same folder produce **one** grouped line, not N.
- `incuratorDashboardModal.ts:renderSources` (1372-1451), the existing
  "Sources" tab, renders **one row per source**, no grouping, no dedup — and
  the briefing's own scope note ("49 sources... 49 rows?") describes exactly
  this tab's existing behavior.

If whoever builds the Dashboard tab copies the pattern that's already sitting
in `plugin/src` (`renderSources`) rather than the one sitting in
`backend/.../core.py` (`_report_unreadable_sources`), the "one row per source
root" language in the briefing's scope item 2 will produce up to 49 rows for
what might be 1-2 actual folders to grant — because `grant_root`'s own design
(shallowest denied ancestor) already collapses most real-world cases to a
small number of folders, and the *backend* already knows how to group them.
**Concretely: the grouping should happen in the backend JSON payload (a new
`denied_roots: [{root, sources: [...]}]` shape, reusing the `by_root`
algorithm already proven in `_report_unreadable_sources`), not be re-derived
client-side over a flat list.** That also avoids a second re-implementation of
the grouping logic that could drift from the CLI's.

**Refresh story — is a stale "denied" row a real risk?** Yes, and it's not
hypothetical, it's how the modal already behaves. `fetchLiveStatus()`
(`incuratorDashboardModal.ts:211-232`) caches `_liveStatusPromise` for the
**lifetime of the modal instance** — every tab switch
(`readRuntimeJson`/`readFreshRuntimeJson`, despite the "Fresh" name, at line
235-247) reuses the same cached promise. It is only invalidated by an explicit
`fetchLiveStatus(true)` call, done today at `refreshRuntimeSnapshots()`
(line 241-243), documented as "call after any mutation so the next read is
current." If a new Dashboard tab reads denial state from this same cache and
the "Grant" button's picker-close handler does **not** explicitly call
`refreshRuntimeSnapshots()`, the row will keep showing "denied" after a
successful grant until the user closes and reopens the whole modal — a worse
UX than no feedback at all, because it actively contradicts what the user just
did. This is fixable (call the existing `refreshRuntimeSnapshots()` after the
picker resolves) but it is not automatic, and the plan should say so
explicitly rather than assume the caching layer will do the right thing.

**A cost concern nobody has flagged yet:** `file_access.py`'s own docstring
(lines 17-26) measures `denied` at **0.722 ms per probe**, "two orders of
magnitude dearer than a stat," and says outright: "That is affordable only
because the caller's candidate list is short (2 on the measured vault). If
resolution ever walks many roots, re-measure before assuming this is still
free." A Dashboard tab that probes "one row per configured root and per
source root" is, by construction, exactly the "walks many roots" case the
docstring is warning about — and if this probing is folded into the payload
`wiki status --json` returns (the plugin's existing polling primitive), every
`wiki status --json` call pays it, not just Dashboard-tab opens, for a vault
where some external root is *permanently* unreadable (e.g., a user who
intentionally keeps some sources local-only and never grants a given root).
This should be measured against a vault with a realistic number of distinct
external source roots before deciding whether probing belongs in the default
`status` payload versus a separate, explicitly-triggered command.

---

## 4. The scenario nobody tested — how "access existed in July and stopped existing" actually happens

**iCloud evicting the local copy of a file — this is the one that is NOT a
permission problem, and this entire feature would misdiagnose it.** Traced
precisely, by code, not by assertion:

`parsers/__init__.py:53-57`:
```python
match file_access.probe(path):
    case file_access.Reachability.DENIED:
        raise ParserAccessDenied(path, file_access.grant_root(path))
    case file_access.Reachability.MISSING:
        raise ParserError(f"File not found: {path}")
```
`probe()`'s only route to `DENIED` is `except PermissionError` (`file_access.py:80-81`).
Every other failure — `FileNotFoundError`, `IsADirectoryError`, and the
catch-all `except OSError` (lines 82-93, explicitly including "a broken
symlink, a dead mount, a name too long") — resolves to `MISSING`. A file that
macOS's File Provider mechanism has evicted to iCloud-only ("dataless": the OS
keeps the directory entry and the filename, materializing bytes on demand when
opened, distinct from the older Desktop-and-Documents-sync `.name.ext.icloud`
sidecar-rename mechanism) will, on an `open()` attempt, do one of: succeed
after a transparent background download (fine, no bug), or fail with
something in the `OSError` family that is **not `PermissionError`** — no
network, a paused/throttled download, or a genuine materialization failure. In
every one of those non-success cases, `probe()` returns `MISSING`, not
`DENIED`, and `parsers.parse()` raises a plain `ParserError("File not found:
...")` — never `ParserAccessDenied`. **The entire first-touch design is gated
on catching `ParserAccessDenied` specifically; a `ParserError` never triggers
it.** The user sees "File not found," goes looking for a deleted or moved
file, and the Dashboard tab's own `probe()` on that same path (if the file
happens to still show `MISSING` at that moment) would show nothing wrong to
grant — because nothing about *permission* is wrong. The fix for this
scenario is "reconnect to the network" or "free up iCloud storage," not
"pick a folder in an open panel," and the picker would do a true no-op: macOS
would report the grant as already satisfied (access was never revoked),
re-close the dialog, and the file would still fail to parse.

I could not obtain a live dataless placeholder on this machine to observe the
exact `errno` — `~/Desktop` and `~/Documents` (the two directories this
process can already list) have zero `.icloud`-suffixed sidecar files
(`0 .icloud placeholder(s) found` for both, checked via `os.scandir` filtering
on `.name.endswith(".icloud")`), and I do not have list access to `~/Library/
Mobile Documents` from this process to look for the modern dataless form
either (`scandir` denied there too, confirmed above). **The exact non-`Permission
Error` exception class is therefore unverified live; the structural claim
(probe() cannot return DENIED for anything except a literal PermissionError,
so this path is real regardless of which specific OSError fires) is grounded
in the code, not in a live repro, and I am flagging that distinction rather
than asserting a specific errno I have not seen.**

**The other three candidates, each checked against the actual code:**

- **App update changing the code-signing identity.** TCC's "responsible
  process" attribution and per-directory grants are tied to the requesting
  app's signing identity in the general Apple model. A re-signed Obsidian
  build (a channel switch, an Insiders build, a notarization change) plausibly
  invalidates a prior grant and macOS would then genuinely deny `open()` —
  `probe()` correctly reports `DENIED` (`PermissionError`), and `grant_root`'s
  walk correctly finds the ancestor **as long as the leaf handed to it is a
  file, not the root itself** (Case A from §1, not Case B). A fresh folder
  picker re-grant would fix it, because NSOpenPanel-based consent is
  independent of prior grant history. **Correctly diagnosed and fixed by this
  design**, modulo the Case B / symlink bugs in §1.
- **A folder moving between volumes** (internal disk → external drive,
  or into a different iCloud/Network Volume category). macOS TCC has separate
  categories for local vs. removable vs. network volumes; moving a folder
  across that boundary plausibly requires a fresh grant even if the path
  string looks similar. Same analysis as above: correctly diagnosed and fixed
  by a fresh picker grant, for a *file* leaf; vulnerable to the Case B bug if
  the new volume's mount root itself becomes the leaf `grant_root` is asked
  to probe. **I could not test this live — no second volume was mounted on
  this machine during the probe — marking this "plausible, not verified."**
- **A TCC reset** (`tccutil reset`, or a manual toggle-off in System
  Settings). This is the textbook case the whole mechanism was built for:
  `PermissionError` on `open()`, `probe()` → `DENIED`, `grant_root` walks
  correctly for a file leaf, a fresh picker grant fixes it. **Correctly
  diagnosed and fixed**, same caveats as above.

---

## 5. What would make this release not worth shipping

Named specifically, not generically:

1. **Propagation does not hold.** This is the briefing's own stated
   precondition ("the measurement this release must start with"), and I could
   not resolve it — the machine genuinely cannot produce a fresh denial for
   this specific pairing (Obsidian/Electron picker grant → spawned Python
   subprocess read) because every candidate directory this shell can reach is
   either already granted (`~/Documents`, `~/Desktop`) or was already denied
   before this session and stays denied after a probe (`~/Downloads`,
   `~/Library/Mobile Documents` — probing never grants anything). I can offer
   one piece of supporting, not conclusive, evidence: the backend is a plain
   POSIX child process (`plugin/src/utils/backendProcess.ts` confirms it is
   collected as a Node `ChildProcess`, not launched as a separate `.app`
   bundle), and Apple's documented "responsible process" attribution for
   non-bundled child processes spawned via fork/exec generally follows the
   parent's identity — which is the same reason Terminal.app needing Full Disk
   Access is sufficient for arbitrary CLI tools run inside it. That is a
   *reasonable expectation*, grounded in how the process is spawned, not a
   verified fact. The existing spec text is worth weighing here too —
   `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md` §12.3 states plainly:
   "Nothing here requests a permission, and nothing changes what a spawned
   process is allowed to read. macOS has no API to ask for a folder grant; a
   background process receives a silent denial rather than a prompt." That
   sentence is about the *background* process specifically having no way to
   prompt — which is exactly why the plan correctly routes the picker through
   Obsidian's own (foreground, GUI) process rather than through Python. It
   does not resolve whether the resulting grant reaches the child. **If it
   turns out it does not propagate, the entire release is a UI that tells the
   user their problem is fixed while the spawned process that does the real
   work is silently denied exactly as before — worse than shipping nothing,
   because it actively removes the (bad, but at least honest-about-being-
   confusing) signal the user currently has to notice something is wrong.**
   Ship-blocking until measured, per the briefing's own framing.

2. **The Dashboard tab calls `grant_root` on bare root paths.** §1a proved
   this returns `None` for exactly the folders most likely to need it
   (`~/Downloads`, `~/Library/Mobile Documents`, both denied-as-directories on
   this machine right now). If the tab is built this way, the one row the
   user opens the tab to act on will have no working grant button on it — a
   silent dead end the release exists to prevent. This is a straightforward
   pre-implementation fix (probe a representative file, not the root), but if
   it ships unfixed, the release actively fails its own stated goal.

3. **The new first-touch prompt and the existing `ZoteroRepairModal` disagree
   with each other.** §2 established that `ZoteroRepairModal` already tells
   users to go to System Settings with no folder named, for the exact same
   `attachment_file_denied` state that already carries a correct
   `grant_folder`. If the new release ships a folder-specific first-touch
   picker for the general ingestion path while leaving the pre-existing Zotero
   modal on its generic-Settings message, the product now gives two different
   answers to the same underlying denial depending on which code path
   triggered it — which is a worse, more confusing state than either
   consistently-generic or consistently-specific messaging. Wiring the
   already-populated `grant_folder` field into `ZoteroRepairModal` is small
   and should ride in the same release, not be left as a "later" item.

4. **The Dashboard tab is built as one row per source (49 rows) instead of
   grouped by `grant_root`.** §3 showed the correct grouping algorithm already
   exists in `commands/core.py:_report_unreadable_sources` and the wrong
   pattern already exists in `incuratorDashboardModal.ts:renderSources`. If
   the new tab is a copy-paste of the latter, it ships a worse version of a
   report the CLI already does correctly, and reintroduces the "wall of green
   or wall of near-duplicate rows" problem this whole feature is supposed to
   fix for permission errors — just moved into a new UI surface.
5. **No plan for the stale-row-after-grant case.** §3 showed the modal's own
   caching (`_liveStatusPromise`, lifetime of the modal instance) will produce
   this by default unless the grant flow explicitly calls the existing
   `refreshRuntimeSnapshots()`. Shipping without this is shipping a "did it
   work?" uncertainty into a feature whose entire purpose is removing
   uncertainty about permission state.

None of these five are reasons to abandon the release — all five are fixable
before or during implementation, and #1 is explicitly flagged in the briefing
as the thing to resolve first. They are reasons the release is not ready to
build against the current sketch in `00_problem.md` without addressing them,
and #1 specifically should gate starting implementation at all.
