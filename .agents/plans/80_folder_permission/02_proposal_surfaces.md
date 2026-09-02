# Surface Proposal: The First-Touch Prompt and the Dashboard Access Tab
Date: 2026-09-02 | Agent Persona: `surface_designer`

> Scope discipline up front: this document answers the five questions the
> briefing assigned to the surfaces angle. It does **not** redesign
> `file_access.py` itself, does not decide the Master Plan's version bump, and
> does not perform the TCC propagation measurement — it specifies exactly how
> to perform it, because §"The measurement this release must start with" in
> `00_problem.md` makes every downstream design choice here conditional on
> that result. Every code block below is a sketch for the Master Plan's P1/P3
> phases, not code written into the repo now.

---

## 0. What changed under me while reading

`00_problem.md` was edited mid-session (a "Re-measured after the grant
appeared, 2026-09-02" section was inserted). Two sentences from it constrain
everything below and I am holding them explicitly rather than letting them
get lost in the two-surfaces framing:

> "The feature being built here is worth building because a permission
> problem cost a release's verification... It is NOT worth building to fix a
> code limit, because there wasn't one."

> "The v0.79.0 fallback counter is what surfaced the remaining five. Whatever
> this release adds must not replace that signal — a UI that only appears
> when someone opens it is weaker than a number the reindex prints
> unprompted."

Both surfaces I'm designing — a first-touch prompt (appears only when an
ingest hits `ParserAccessDenied`) and a Dashboard tab (appears only when the
user opens the Dashboard) — are **pull, not push**. Neither is "a number the
reindex prints unprompted." I say exactly where this falls short in §2
Pros & Cons rather than quietly pretending my two surfaces are the whole
answer.

---

## 1. Core Logic & Implementation

### 1.0 The measurement this design is conditional on

The briefing is explicit that this machine can no longer produce a fresh
denial for the one folder that already failed
(`~/Library/Mobile Documents`), so I cannot validate propagation by pointing
the new UI at that folder and watching it flip green — it would already be
green, and that proves nothing about the picker.

**Protocol** (to run once, by hand, before P3 is trusted — not something I
executed as part of this research pass):

1. Pick a folder this Obsidian install has **never** been granted — not
   `~/Documents`/`~/Desktop`/`~/Downloads` if any tool on this machine has
   already been through a grant dialog that covers them; safest is a fresh
   `mkdir ~/tcc_probe_test` that has no TCC history at all.
2. From a plain Terminal (a *different* responsible process than Obsidian),
   confirm the baseline is denied for a bare Python process:
   `python3 -c "import os; os.open('/Users/<u>/tcc_probe_test', os.O_RDONLY)"`
   should raise `PermissionError` if the folder is under a TCC-protected
   container, or succeed if it is not — either way, know the baseline before
   touching Obsidian.
3. Temporarily register it as a root (`wiki config set
   external.path_roots.tcc_probe_test ~/tcc_probe_test`) so it shows up as a
   row in the new Access tab (§1.3).
4. In Obsidian, open the Access tab, click **Grant** on that row, and in the
   native panel (§1.5) select `~/tcc_probe_test` itself.
5. Immediately re-run `wiki plugin access` — a **fresh spawn**, not a
   restart of anything (`plugin/main.ts:1036-1056`'s `runBackendCommand`
   calls `spawn(command, ...)` per invocation; there is no long-lived backend
   daemon whose own permission cache could be stale — see §1.2). If the row
   flips to `ok` on that very next call, propagation holds and this design
   ships as-is. If it stays `denied`, **stop** — per the briefing, the design
   changes to reading inside the Obsidian process or a security-scoped
   bookmark, and that is a different proposal, not a patch to this one.
6. Undo step 3 (`wiki config set external.path_roots.tcc_probe_test ""`
   or remove the key) — it is a throwaway probe root, not a real one.

**`chmod 000` is NOT a substitute for step 4, and I am saying so per the
briefing's instruction.** `file_access.probe()` catches Python's
`PermissionError`, which is raised for *both* a TCC refusal (`EPERM` at the
sandbox/MAC-framework layer) and an ordinary POSIX permission refusal
(`EACCES` from `chmod 000`) — so a `chmod 000` directory is a good,
CI-safe, deterministic fixture for unit-testing the **endpoint's DENIED-path
branching logic** (§1.2's `_probe_root`), because that logic only cares that
`PermissionError` was raised, not why. It tells you nothing about whether an
Obsidian-side grant reaches the spawned Python, because `chmod` bits are
per-file, not per-responsible-process — no picker selection fixes a
`chmod 000` directory, and granting Full Disk Access to Obsidian does nothing
for one either. Use `chmod 000` fixtures for the pytest coverage in P3; use
the untouched-folder protocol above for the one P0 fact this whole release
stands on.

This reasoning is also why `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`
§12.3 needs a line added once (and only once) step 5 above resolves either
way — its current text ("Nothing here requests a permission... macOS has no
API to ask for a folder grant", `SYSTEM_BEHAVIOR.md:1636-1639`) was written
before this release's central claim (an `NSOpenPanel` selection *is* a grant,
which is different from a formal `requestAccess`-style API) and will read as
contradicted by the shipped feature if left untouched. That's a docs task for
whichever Master Plan phase implements this, not a decision I'm making here.

### 1.1 What is a root worth showing

Enumerated from `config.py`/`db/schema.py`, not imagined. Four buckets, and
I built the list by grepping for every place a filesystem root is *defined*
in this codebase, not by guessing what "a root" should mean:

**(a) The vault root.** `WikiPaths.root` (`config.py:65`). Exactly one row.
Worth its own row separately from the raw dirs below because a vault that
itself lives under `~/Documents` or `~/Desktop` (both named as
TCC-protected-by-default in the briefing) can be denied at the
`os.scandir()`/`.rglob()` level used by auto-discovery
(`commands/core.py:528`, `raw_dir.rglob("*")`) even before any individual
source file is probed — a distinct failure mode from "one PDF is denied,"
worth surfacing at its own root rather than only inferred from raw-dir rows
failing too.

**(b) Each configured raw directory.** `WikiPaths.raw_dirs`
(`config.py:73-76`) — `[self.root / d for d in (raw_dirs_override or
DEFAULT_RAW_DIRS)]`, where `DEFAULT_RAW_DIRS = [DIR_WIKI, DIR_NOTES,
DIR_RESOURCES]` = `["02_Wiki", "03_Notes", "04_Resources"]`
(`config.py:34`, `constants.py:6-8`). This is the **complete** set of
directories `sources.relpath` can point into — `add_file()`'s guard at
`ingest_raw.py:2067-2084` rejects anything not under `raw_dirs` — so I do
**not** additionally run a `SELECT DISTINCT` over `sources.relpath` prefixes
to find "the distinct parent folders of registered `sources.relpath`": that
query could only ever reproduce a subset of `raw_dirs`, never surface a root
outside it, so it would add cost (a DB round trip) without adding
information. I verified this by reading the guard rather than assuming it —
`_is_inside_raw()` is the only gate `add_file()` has for where a `relpath`
source may live.

**(c) Every key in `external.path_roots`.** This is the generic mechanism
`path_refs.configured_roots()` reads (`path_refs.py:62-75`) and it is
**exactly** where the two Zotero directories live, as two *separate* keys
written by `zotero_tools.zotero_init()`
(`zotero_tools.py:119-122`):
`external.path_roots.zotero_data` (the directory holding `zotero.sqlite` —
the index) and `external.path_roots.zotero_linked` (the linked-attachment
base directory — where the bytes are, "often iCloud" per this repo's own
prior correction, recorded in memory as `zotero-two-directories.md`). Iterating
`external.path_roots` generically rather than hardcoding `"zotero"` means
the Zotero-two-directories constraint is satisfied **structurally**, not by
special-casing Zotero in the endpoint — any future integration that
registers a third `path_roots` key gets a row for free, and nothing in the
endpoint needs to know Zotero exists.

**(d) An `external_ref` key referenced by a real source row but absent from
`external.path_roots`.** This is the literal `sources.external_ref` half of
the briefing's enumeration instruction, and it surfaces a state that (c)
alone cannot: a source was registered with `external_ref = '@some_key/...'`
(`db/schema.py:205`, portable-ref format defined in `path_refs.py:23-34`),
but `some_key` has since been removed from `external.path_roots` — config
drift, not a filesystem permission problem. `path_refs.resolve_ref()` would
raise `RootUnregisteredError` for it (`path_refs.py:100-105`), so showing
nothing for that source, rather than a distinct "unconfigured" row, would be
the same "silently deduplicate and hide a real defect" mistake
`_report_unreadable_sources()` explicitly refuses to make for Unicode-doubled
sources (`commands/core.py:445-450`, "SAY SO rather than hiding it"). One
cheap query gets this:
```sql
SELECT DISTINCT external_ref FROM sources
WHERE external_ref IS NOT NULL AND external_ref != '';
```
— parse each with `PortablePathRef.parse()`, collect `.root_key`, subtract
`configured_roots(config).keys()`.

**What this enumeration deliberately does NOT cover**, named honestly rather
than left implicit: `_resolve_reference_source()` has a *third* resolution
path beyond Zotero and `external_ref` — a plain `target_path` read live out
of a reference-stub's frontmatter when no `zotero_key` is present
(`ingest_raw.py:144-145`). That path is never written to
`sources.external_ref` at all, so no DB query can find it; finding every such
stub would mean opening and parsing frontmatter for every `.md` file under
`raw_dirs`, which is exactly the 123ms-for-44-sources cost
`_report_unreadable_sources()`'s own comment says makes `wiki status`
"visibly slow" at vault scale (`commands/core.py:417-422`). I am treating
this as an accepted, named gap (see §2), matching the briefing's own literal
scope ("registered `sources.relpath` / `external_ref`") rather than silently
expanding scope to close it.

**Concrete example shape**, four buckets, on a vault with Zotero configured
and the iCloud folder from `00_problem.md`:

```
vault_root                 /Users/shin/.../MyVault
raw_dir:02_Wiki             .../MyVault/02_Wiki
raw_dir:03_Notes            .../MyVault/03_Notes
raw_dir:04_Resources         .../MyVault/04_Resources
zotero_data                  ~/Zotero
zotero_linked                 ~/Library/Mobile Documents/com~apple~CloudDocs/Zotero
```
plus zero or more `unconfigured:<key>` rows only when (d) finds drift.

### 1.2 The backend endpoint

**New module** `backend/src/curator/plugin_api/access.py`, following the
existing `plugin_api/` package shape (`pdf.py`, `sources.py`, `context.py`,
`query_api.py`, re-exported through `plugin_api/__init__.py:6-29`). One
function:

```python
# backend/src/curator/plugin_api/access.py
from __future__ import annotations
from pathlib import Path
from typing import Any

from .. import config as cfg, db, file_access, path_refs


def _probe_root(path: Path) -> tuple[str, str]:
    """(state, grant_folder) for a DIRECTORY root.

    `file_access.probe()` opens the path AS A FILE (`file_access.py:69-79`):
    it does `os.open(...)` then checks `stat.S_ISREG`, and a directory always
    fails that check — so for a directory, `probe()` can return DENIED
    (correctly: a TCC-denied `os.open` raises PermissionError regardless of
    whether the target is a file or a directory, same syscall-level check)
    but can NEVER return OK, because the S_ISREG guard fires before the read
    that would prove it. It can only ever report OK-directories as MISSING.

    So MISSING is ambiguous for a directory in exactly one way: "does not
    exist" vs. "exists, is a directory, `os.open` already succeeded on it".
    A plain `Path.is_dir()` resolves the ambiguity WITHOUT reintroducing the
    `os.access`/`exists()` trap this module's own docstring warns against
    (file_access.py:1-27) — that trap is about using a stat-only check
    INSTEAD OF an open-based probe to decide READABILITY. Here `is_dir()` is
    used only to decide TYPE (does the thing that already didn't get a
    PermissionError look like a directory), never to decide DENIED vs. not —
    that decision is still made entirely by `probe()`'s open() result.
    """
    state = file_access.probe(path)
    if state is file_access.Reachability.OK:
        return "ok", ""
    if state is file_access.Reachability.DENIED:
        grant = file_access.grant_root(path)
        return "denied", str(grant or path)
    # MISSING: disambiguate without re-deciding readability ourselves.
    if path.is_dir():
        return "ok", ""
    return "missing", ""


def list_access_roots(paths: cfg.WikiPaths) -> dict[str, Any]:
    """Every folder Incurator needs to read, and whether it currently can.

    Reuses ONLY `file_access.probe`/`grant_root` for the readability verdict
    (SYSTEM_BEHAVIOR §12.3) — this module contributes no new TCC-detection
    logic of its own, only the enumeration of WHICH paths count as roots
    (see plan doc §1.1) and the directory-vs-file disambiguation above.
    """
    config = cfg.load_config(paths)
    rows: list[dict[str, Any]] = []

    def add(key: str, label: str, kind: str, path: Path | None) -> None:
        if path is None:
            rows.append({
                "key": key, "label": label, "kind": kind,
                "path": "", "state": "unconfigured", "grant_folder": "",
            })
            return
        state, grant_folder = _probe_root(path)
        rows.append({
            "key": key, "label": label, "kind": kind,
            "path": str(path), "state": state, "grant_folder": grant_folder,
        })

    add("vault_root", "Vault", "vault_root", paths.root)
    for d in paths.raw_dirs:
        add(f"raw_dir:{d.name}", d.name, "raw_dir", d)

    configured = path_refs.configured_roots(config)
    for key, root_path in configured.items():
        label = {"zotero_data": "Zotero (data)", "zotero_linked": "Zotero (attachments)"}.get(key, key)
        add(key, label, "external_root", root_path)

    with db.connect(paths.state_db) as conn:
        ref_rows = conn.execute(
            "SELECT DISTINCT external_ref FROM sources "
            "WHERE external_ref IS NOT NULL AND external_ref != ''"
        ).fetchall()
    referenced_keys: set[str] = set()
    for r in ref_rows:
        try:
            referenced_keys.add(path_refs.PortablePathRef.parse(str(r["external_ref"])).root_key)
        except ValueError:
            continue
    for key in sorted(referenced_keys - set(configured.keys())):
        add(key, f"{key} (unconfigured)", "external_root", None)

    return {"ok": True, "roots": rows}
```

**CLI command**, following the flat single-purpose pattern already used for
`plugin_query`/`plugin_promote` (not a new sub-typer — there is exactly one
read here, not a family of subcommands yet):

```python
# backend/src/curator/commands/plugin.py, alongside plugin_source_status etc.
@plugin_app.command("access")
def plugin_access(
    workspace_path: str = typer.Option("", "--workspace-path", help="Vault root override."),
) -> None:
    """Return every root Incurator reads and its live probe verdict."""
    from .. import plugin_api
    try:
        _print_json(plugin_api.list_access_roots(_plugin_paths(workspace_path)))
    except Exception as exc:
        _print_json({"ok": False, "error": str(exc)})
        raise typer.Exit(code=1)
```

`wiki plugin access` — JSON shape:

```json
{
  "ok": true,
  "roots": [
    {"key": "vault_root", "label": "Vault", "kind": "vault_root",
     "path": "/Users/shin/.../MyVault", "state": "ok", "grant_folder": ""},
    {"key": "raw_dir:04_Resources", "label": "04_Resources", "kind": "raw_dir",
     "path": ".../MyVault/04_Resources", "state": "ok", "grant_folder": ""},
    {"key": "zotero_data", "label": "Zotero (data)", "kind": "external_root",
     "path": "/Users/shin/Zotero", "state": "ok", "grant_folder": ""},
    {"key": "zotero_linked", "label": "Zotero (attachments)", "kind": "external_root",
     "path": "/Users/shin/Library/Mobile Documents/com~apple~CloudDocs/Zotero",
     "state": "denied", "grant_folder": "/Users/shin/Library/Mobile Documents"}
  ]
}
```

**Why NOT fold this into `wiki status --json`**, which the Dashboard already
fetches once per render (`incuratorDashboardModal.ts:211-233`,
`fetchLiveStatus()`): I checked, and `runtime_state._portable_status_config()`
**deliberately zeroes `external.path_roots`** before it goes into that
snapshot — `external_cfg["path_roots"] = {}` at `runtime_state.py:296`,
with the comment "Machine-local absolute paths stay outside the vault"
(`runtime_state.py:283-285`). That snapshot is written to a machine cache
file and its whole design intent is to be safe to leave lying around /
potentially portable; deliberately stripping real filesystem paths out of it
is a design decision I should not quietly reverse by piggybacking a
path-carrying payload onto the same call. A separate `wiki plugin access`
call, fetched only when the Access tab is open, keeps that boundary intact.
(Side finding, not mine to fix here: the Overview tab's System card already
reads `status?.external?.zotero?.roots`,
`incuratorDashboardModal.ts:688-689,811-818` — given the redaction above,
that field is always empty in the live payload today, which is presumably
why that fallback path silently degrades to `"~/Zotero (default)"` /
`"no roots"` and nobody noticed. Worth a one-line mention to whoever owns
Overview cleanup; not this proposal's job to fix.)

### 1.3 The Dashboard tab

New `TabId` member and `TABS` entry, same array shape as the existing six
(`incuratorDashboardModal.ts:28-37`):

```ts
type TabId = "overview" | "jobs" | "sources" | "traces" | "synthesis" | "insights" | "persona" | "access";
const TABS: { id: TabId; label: string; icon: string }[] = [
  // ...existing six...
  { id: "access",   label: "Access",   icon: "shield-check" },
];
```

New `case "access": this.renderAccess(view); break;` in `switchTab()`'s
switch (`incuratorDashboardModal.ts:163-171`).

**The pattern I am following** is `renderSources()`
(`incuratorDashboardModal.ts:1372-1451`) almost verbatim — same
`ai-agent-dashboard-table-container` / `-table-header` / `-table-row`
structure, same `readFreshRuntimeJson`-style loading/empty/error scaffolding
— because the task is structurally identical: one row per item, a status
badge, a conditional action. I'm reusing `renderSources()`'s exact badge CSS
classes (`styles.css:2751-2755`: `badge-curated` green,
`badge-error` red, `badge-ready` neutral) rather than inventing new ones:

```ts
private async renderAccess(el: HTMLElement) {
  el.createEl("h3", { text: "Folder Access", cls: "ai-agent-dashboard-section-title" });
  const loading = el.createDiv({ cls: "ai-agent-dashboard-loading", text: "Loading…" });
  const data = await this.runPluginJson(["plugin", "access"]);
  loading.remove();
  if (!data?.ok) { el.createDiv({ cls: "ai-agent-dashboard-empty", text: "Failed to load — backend unavailable." }); return; }

  const container = el.createDiv("ai-agent-dashboard-table-container");
  const header = container.createDiv("ai-agent-dashboard-table-header");
  for (const c of ["Root", "Path", "Status", ""]) header.createDiv({ text: c });

  const badge = (state: string) => ({
    ok:           { str: "Readable",     cls: "badge-curated" },
    denied:       { str: "Denied",       cls: "badge-error" },
    missing:      { str: "Not found",    cls: "badge-ready" },
    unconfigured: { str: "Unconfigured", cls: "badge-error" },
  }[state] ?? { str: "—", cls: "badge-ready" });

  for (const root of data.roots ?? []) {
    const row = container.createDiv("ai-agent-dashboard-table-row");
    row.createDiv({ text: root.label });
    const pathCell = row.createDiv({ text: root.path || "(no path configured)" });
    pathCell.style.fontSize = "11px";
    pathCell.style.color = "var(--text-muted)";
    const b = badge(root.state);
    row.createDiv().createSpan({ cls: `ai-agent-dashboard-badge ${b.cls}`, text: b.str });

    const actionCell = row.createDiv();
    if (root.state === "denied") {
      this.addActionBtn(actionCell, "Grant", "folder-open", async () => {
        await this.requestFolderGrant(root.grant_folder || root.path);
        el.empty();
        await this.renderAccess(el);
      });
    }
  }
}
```

`addActionBtn()` (`incuratorDashboardModal.ts:286-299`) is the existing
disable-while-running / restore-label button helper, reused unmodified —
same pattern the "Retry errored sources" button in `renderSources()` uses
(`incuratorDashboardModal.ts:1394-1410`).

**`unconfigured` gets NO button** — there is no path to open a picker at,
because by definition nothing is configured for that key; the row exists
only to say "a source depends on a root this vault's config no longer
defines," which is a config-repair problem (`wiki config set
external.path_roots.<key> <path>`), not a folder-grant problem. Collapsing
it into the same button as `denied` would send the user into a picker that
cannot fix what's actually wrong.

### 1.4 The first-touch prompt — tracing `ParserAccessDenied` to the plugin today

I traced every one of the three sites the briefing names
(`parsers/base.py:54-57`: "all three existing `except ParserError` sites").
**Current line numbers have drifted from that docstring's `2054`/`2201`**
(the file has grown since it was written) but the count of three still
holds — I re-verified with `grep -n "except parsers.ParserError\|except
ParserError"` and found exactly three, at `ingest_raw.py:2090`,
`ingest_raw.py:2240`, and `commands/sources.py:187`.

**Site 1 — `ingest_raw.py:2038-2096`, `add_file()`.** Used by `wiki add`
(`commands/core.py:825`, no `--json` flag exists on this command at all —
confirmed by reading the full `add()` typer signature,
`commands/core.py:780-796`) and by `ingest_llm._auto_discover_pending()`
(`ingest_llm.py:315`, background auto-discovery). On `ParserAccessDenied`,
line 2090 returns `AddOutcome(result=AddResult.ERROR, message=f"Parse
failed: {e}")`. The caller in `commands/core.py:828-829` does
`_err(outcome.message)` — a Rich console print. **The plugin never calls
`wiki add` and never reads this.** Dead end for the plugin, full stop.

**Site 2 — `ingest_raw.py:2207-2246`, `import_source_file()`.** This IS
plugin-reachable: `plugin_api.sources.import_source()`
(`plugin_api/sources.py:174-196`) calls it, and `wiki plugin source import`
(`commands/plugin.py:292-321`) is what `IncuratorClient.ingestPdf()`
(`incuratorClient.ts:239-284`) calls for every plugin-driven "add this PDF"
action. On `ParserAccessDenied`, line 2240 returns the identical
`AddOutcome(result=AddResult.ERROR, message=f"Parse failed: {exc}")` shape,
and `plugin_api/sources.py:182-196`'s return dict carries **only**
`"message": outcome.message` — a **prose string** containing "Not permitted
to read `<path>` — grant access to `<folder>`"
(`parsers/base.py:64-68`'s `__str__`). There is no `grant_folder` key on
this JSON response at all. `AddOutcome` (`ingest_raw.py:47-73`) has no field
for it either — the exception's own `.grant_folder` attribute
(`parsers/base.py:65-66`) is discarded the moment it's interpolated into the
`message` string at line 2245, even though `ParserAccessDenied` is carrying
it as structured data right up until that point.

**This is the concrete gap the first-touch prompt needs closed, and it is
small**: add `grant_folder: str = ""` to `AddOutcome`
(`ingest_raw.py:47-73`), set it from `exc.grant_folder` at the `except
ParserAccessDenied` branch (note: `import_source_file()`'s current except
clause catches the broader `parsers.ParserError` at line 2240 — it needs a
`except parsers.ParserAccessDenied as exc:` branch ahead of the existing
`except parsers.ParserError` to actually reach `.grant_folder`, since
`ParserAccessDenied` is a subclass and the broader catch currently treats it
identically to a corrupt-file parse failure), then add `"grant_folder":
outcome.grant_folder` to the dict at `plugin_api/sources.py:195`, then have
`IncuratorClient.ingestPdf()` read it into the `IncuratorSourceStatus`
returned at `incuratorClient.ts:260-268` instead of only forwarding
`message`. None of this is implemented by me — it's the P1 contract change
the Master Plan needs, named precisely enough that whoever writes P1 doesn't
have to re-derive it.

**Site 3 — `commands/sources.py:160-189`, `sources_show_cmd()`.** `wiki
sources show <id>` — pure human CLI (`_err()`, Rich console), no JSON mode,
and `grep`-confirmed the plugin has no command that calls it. Same dead end
as Site 1.

**A fourth, adjacent path already carries `grant_folder` structurally — and
silently drops it in the plugin layer, which is a second concrete bug worth
fixing in the same release.** `zotero_tools._denied_result()`
(`zotero_tools.py:319-344`) — reached via `wiki plugin zotero resolve-pdf`
(`commands/plugin.py:1289-1308`) when a Zotero-linked PDF is denied — DOES
put `"grant_folder": str(root) if root else ""` on its JSON response
(`zotero_tools.py:338`). The TypeScript interface even documents the intent:
```ts
// incuratorClient.ts:90-92
/** Set with state="attachment_file_denied": the folder the user must grant.
 *  Carried explicitly rather than parsed back out of `error`, which is prose. */
grant_folder?: string;
```
But `resolveZoteroPdf()`'s normalizer (`incuratorClient.ts:881-899`) never
reads it — the return object at lines 888-898 sets `ok`, `path`,
`attachmentKey`, `state`, `error`, `dbPath`, `zoteroDb`, `rootsChecked`,
`pathsChecked`, and **not** `grant_folder`, despite the interface declaring
the field one line above. `ZoteroRepairModal`
(`plugin/src/ui/zoteroRepairModal.ts`, read in full) confirms the
consequence: it never displays a specific folder either —
`describeZoteroState("attachment_file_denied")`
(`zoteroRepairModal.ts:30-33`) hard-codes the generic instruction "Grant
access to its folder in System Settings → Privacy & Security → Full Disk
Access, then restart" with no folder name filled in, because the modal has
never had the folder name to fill in. **This bug predates this release and
is not something my proposal introduces — but the first-touch prompt I'm
designing needs the same field on the Zotero path too, so fixing the TS
normalizer's dropped field is in scope for the same P1/P3 pass.**

**Conclusion for §4**: `ParserAccessDenied` is not fully swallowed before
reaching the plugin — it reaches `wiki plugin source import`'s JSON output
today, but only as unstructured prose inside `message`, with no field a UI
could hand to a folder picker without regex-scraping "grant access to
(.+)$" out of a human sentence (exactly the anti-pattern
`incuratorClient.ts:91`'s own comment on `ZoteroPdfResolution.grant_folder`
warns against for the *other* path). The first-touch prompt cannot be built
against today's contract; it needs the `grant_folder` field threaded through
`AddOutcome` → `plugin_api.sources.import_source()` → `ingestPdf()`, plus the
existing-but-dropped `grant_folder` on the Zotero resolve-pdf path wired
through `resolveZoteroPdf()`. Both are one-field, mechanical, low-risk
changes with an exact call chain named above — this is the honest
"structured field, not prose" fix, in the spirit of Root Cause Over
Workarounds rather than parsing the message string in the UI layer.

### 1.5 The picker

**No native folder picker exists anywhere in this plugin today** — I
searched for `showOpenDialog`/`electron` across `plugin/src` and found
exactly one Electron usage, `getElectronShell()`
(`incuratorQueryTrace.ts:457-470`), which only reaches `electron.shell` (for
`openPath`/`openExternal`), not `dialog`. `ZoteroRepairModal`
(`zoteroRepairModal.ts:137-159`), the closest existing "point the backend at
a folder" UI, uses two plain `Setting(...).addText(...)` fields — the user
types or pastes a path. There is no precedent to follow for the picker
itself; I'm designing it from the same defensive `require()` pattern
`getElectronShell()` already establishes, because `electron` is marked
external in the plugin's own build (`esbuild.config.mjs:33`) and Obsidian
supplies it at runtime rather than the plugin bundling its own copy —
`@electron/remote` is not a declared dependency in `plugin/package.json`
either, so it has to be resolved the same speculative way at runtime that
`getElectronShell()` already does for `shell`.

`dialog` is main-process-only in modern Electron (unlike `shell`, which
`getElectronShell()` can reach directly) — a renderer needs
`@electron/remote`'s `dialog`, or the older `electron.remote.dialog` on
Electron builds where remote wasn't split out. Obsidian's own host process
bundles `@electron/remote`, so `require("@electron/remote")` from plugin
code resolves to Obsidian's own copy via Node's normal module resolution,
without the plugin adding it as a dependency — the same trick
`getElectronShell()`'s fallback branch already relies on.

```ts
async function pickFolder(defaultPath?: string): Promise<string | null> {
  let dialog: any = null;
  try { dialog = (require("electron") as any)?.remote?.dialog ?? null; } catch { /* noop */ }
  if (!dialog) {
    try { dialog = (require("@electron/remote") as any)?.dialog ?? null; } catch { /* noop */ }
  }
  if (!dialog) return null;                       // no native picker available
  const result = await dialog.showOpenDialog({
    defaultPath,                                    // pre-selects/navigates to grant_folder
    properties: ["openDirectory", "createDirectory"],
    buttonLabel: "Grant Access",
  });
  if (result.canceled || !result.filePaths?.length) return null;
  return result.filePaths[0];
}
```

**Exact call**: `dialog.showOpenDialog({ properties: ["openDirectory", ...] })`.
`"openDirectory"` is load-bearing, not decorative — it's what puts the
`NSOpenPanel` into folder-selection mode on macOS, and it is the macOS
folder-selection-and-confirm interaction that registers the sandbox/TCC
grant as a side effect (the mechanism the briefing's Scope §1 is banking on).
An `"openFile"` panel selecting a single PDF would not grant the *folder*,
only that one file, which is useless here since every later read is a
different file in the same folder.

**Pre-selection**: `defaultPath` is set to the row's `grant_folder` from the
`wiki plugin access` payload (§1.2) — i.e. the shallowest denied ancestor
`file_access.grant_root()` already computed, not the leaf file. This is the
same value the endpoint already surfaces per row, so the Dashboard button
(`renderAccess()`, §1.3) and the first-touch prompt (§1.4, once wired) both
call `pickFolder(root.grant_folder || root.path)` — one function, two
call sites, no duplicated picker logic.

**After the user chooses**: no backend write is required for the grant
itself — per the briefing, "choosing it IS the grant." The only backend
call after a successful pick is the same read the row already uses:
re-run `wiki plugin access` (Dashboard tab) or re-attempt the import (Site 2
above, first-touch context) and re-render. Concretely, for the Dashboard's
`requestFolderGrant()`:

```ts
private async requestFolderGrant(suggestedPath: string): Promise<void> {
  const chosen = await pickFolder(suggestedPath);
  if (!chosen) { new Notice("No folder selected."); return; }
  new Notice(`Requested access to ${chosen} — rechecking…`);
  // No backend write: the native panel selection is itself the grant (macOS).
  // Every `wiki plugin ...` call is a fresh spawn (main.ts:1036-1048, no
  // daemon), so the very next call already runs in a freshly-launched
  // process — nothing to restart before re-checking.
}
```

— and the caller (`renderAccess()`'s button handler, §1.3) re-fetches and
re-renders immediately after this resolves, so the row's own badge is the
confirmation.

**What they see if the grant did not take** — this is the "visible rather
than silent" branch the briefing requires if propagation turns out not to
hold (§1.0 step 5), and it must degrade to something useful rather than a
silent no-op re-render that looks identical to "nothing happened yet":

```ts
if (chosen) {
  const after = await this.runPluginJson(["plugin", "access"]);
  const stillDenied = (after?.roots ?? []).find((r: any) => r.path === root.path)?.state === "denied";
  if (stillDenied) {
    new Notice(
      `Selected ${chosen}, but Incurator's backend still cannot read it. ` +
      `This app may need Full Disk Access instead — System Settings → ` +
      `Privacy & Security → Full Disk Access.`,
      0 // sticky
    );
  }
}
```

— reusing the exact fallback instruction text already established in
`_report_unreadable_sources()` (`commands/core.py:472-475`) and
`describeZoteroState("attachment_file_denied")`
(`zoteroRepairModal.ts:33`), rather than inventing new copy for the same
fallback. This is also precisely why §1.0's protocol has to run before P3 is
trusted: if it turns out propagation *never* holds on this architecture, the
picker still degrades to "tell the user to go to System Settings" — which is
exactly the status quo today, just reached one click later and with the
right folder named instead of a generic instruction. It would not be a
regression, but it would mean Surface 1's core promise ("no trip to System
Settings") did not ship, and the Master Plan needs to say that plainly
rather than let the UI imply a fix that isn't there.

---

## 2. Pros & Cons

**Pros**

- Every "root" shown is derived from `config.py`/`db/schema.py`, not
  invented — §1.1's four buckets are traceable to exact fields
  (`WikiPaths.root`, `WikiPaths.raw_dirs`, `external.path_roots`,
  `sources.external_ref`), so the endpoint cannot drift from what the
  backend actually reads without the enumeration code itself changing.
- The directory-probing trap (§1.2's `_probe_root`) is resolved using
  **only** primitives `file_access.py` already exposes (`probe`,
  `grant_root`) plus a plain `Path.is_dir()` used strictly for type, never
  for readability — no new TCC-detection logic anywhere outside
  `file_access.py`, honoring "the plugin must not become the place that
  decides what a root is; the backend already owns `grant_root`" and
  extending that same ownership boundary to the new module.
- The Zotero-two-directories constraint is satisfied structurally (iterating
  `external.path_roots` generically) rather than by special-casing "zotero"
  in the endpoint, so it can't regress the way a hardcoded two-row UI could.
- §1.4 turned up two concrete, narrowly-scoped, low-risk bugs with exact
  fixes named (the missing `grant_folder` field on `AddOutcome`/
  `import_source`'s JSON, and the already-declared-but-never-read
  `grant_folder` in `resolveZoteroPdf()`) rather than either inventing new
  plumbing from scratch or hand-waving "the plugin will need some data
  here."
- The picker reuses the plugin's one existing Electron-access pattern
  (`getElectronShell()`'s defensive dual `require()`) instead of introducing
  a new dependency or a new access pattern.
- §1.0 gives the Master Plan an executable, falsifiable P0 test — using a
  never-granted folder rather than the now-useless already-granted one — and
  explicitly separates it from the `chmod 000` fixture, so P3's pytest
  coverage doesn't get mistaken for having validated propagation when it has
  only validated the endpoint's branching logic.

**Cons — named plainly, not solved here**

- **This does not add an unprompted signal.** Both surfaces are pull:
  the Dashboard tab requires opening the Dashboard, and the first-touch
  prompt requires an ingest to already be failing. Per the briefing's own
  updated framing, "a UI that only appears when someone opens it is weaker
  than a number the reindex prints unprompted" — that stronger signal is the
  v0.79.0 fallback counter, which this proposal does not touch, must not
  regress, and does not replace. If the Master Plan wants a third,
  unprompted surface (e.g. a startup or post-sync banner), that's a
  different persona's angle, not covered here.
- **The `target_path`-only reference-stub gap is real and unclosed** (end of
  §1.1): a Reference Mode stub resolved via bare frontmatter `target_path`
  with no `zotero_key` never gets an `external_ref` row, so its folder never
  appears in the Access tab even if it is currently denied. Closing it means
  parsing frontmatter for every candidate stub, which is the exact cost
  `_report_unreadable_sources()` already measured as vault-scale-prohibitive
  for a status check. I left it out rather than pay that cost silently.
- **Everything here is conditional on §1.0's propagation result**, which I
  have not run. If it comes back negative, Surface 1's headline promise ("no
  trip to System Settings") does not materialize, and both surfaces degrade
  to a same-folder-named version of the status quo — still worth shipping
  (naming the folder beats not naming it), but not the release the briefing
  describes.
- **The `unconfigured` root-key state (§1.1d) has no self-service fix in
  this UI** — I deliberately did not give it a Grant button (§1.3), because
  a picker cannot repair a missing config key. It surfaces the problem
  honestly but hands the user a `wiki config set` command, not a click. A
  friendlier fix (an inline text field that writes the key) is possible but
  is scope creep beyond "the two surfaces" as briefed.
- **The picker's `require("@electron/remote")` resolution is unverified in
  this Obsidian version** — I traced that it's the established pattern this
  plugin already leans on for `shell`, but nobody in this codebase has
  exercised the `dialog` half of that module before. It should be smoke
  tested against the actual Obsidian/Electron version this plugin targets
  before P3 is considered done, not assumed from the `shell` precedent
  alone.
- **`SYSTEM_BEHAVIOR.md` §12.3 needs a documentation follow-up** (noted in
  §1.0) once the P0 measurement resolves either way — I have not written
  that update, since writing it before the measurement runs would be
  documenting a claim I have not verified, which is exactly the kind of
  premature certainty this whole release exists to avoid repeating.
