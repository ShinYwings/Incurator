# v0.80.0 Master Implementation Plan — say which folder, and say it where the user is

## 1. What the Arena established, and what it changed

The briefing asked for a first-touch grant prompt and a Dashboard tab. Three
independent passes found that **the foundation for both is missing**, and one
found a case the whole feature would misdiagnose.

### The denial never reaches the plugin

`ParserAccessDenied` carries `.grant_folder` — the exact folder to grant. Traced
across four call paths, it is flattened into prose or dropped to a bare count
before the plugin ever sees it (`ingest_raw.py:2090`, `:2240`,
`plugin_api/sources.py:174-196`, `retrieval/materializer.py:212-229`).

`AddOutcome` has no `grant_folder` field at all, so the structured answer is
discarded at the boundary.

One path DOES carry it structurally — `zotero_tools.resolve_pdf` emits it and
`incuratorClient.ts:92` declares it in the TypeScript interface — and the
normalizer at `incuratorClient.ts:881-899` **never reads it**. Meanwhile
`ZoteroRepairModal` still tells the user to go to System Settings without naming
a folder, which is precisely the mistake `grant_root`'s own docstring records
this repo already paying for once.

**So there is no message to attach a button to.** Building the UI first would
have produced a prompt that could not say which folder.

### `grant_root` is wrong for the Dashboard's main case

It walks `path.parents` and never tests `path` itself. Verified live:

```
probe(~/Downloads)                  -> denied     grant_root -> None
probe(~/Library/Mobile Documents)   -> denied     grant_root -> None
```

A Dashboard row is a ROOT. Calling `grant_root` on a denied root returns `None`,
so the grant button would have had nothing to open. It is correct only for the
"file inside a denied folder" shape, which is what the July incident happened to
be. Symlinks are also unhandled: `probe` follows them, `Path.parents` does not.

### An iCloud-evicted file is not a permission problem, and this feature would misdiagnose it

`probe()` reaches `DENIED` only through `except PermissionError`. A file macOS
has evicted to iCloud-only — dataless, a placeholder on disk — fails some other
way and falls to `MISSING`, surfacing as `ParserError("File not found")`.

A first-touch prompt gated on `ParserAccessDenied` would **never fire**, and a
folder picker would be a **no-op**, because access was never revoked. The file is
simply not local. Any honest version of this feature has to tell those two apart.

### The denial is not stable, and that is the actual user experience

Observed live within this session: `~/Library/Mobile Documents` was readable
(the whole vault reindexed, 49/49 documents, failures 10,176 → 5), and minutes
later the same call from the same code returned `PermissionError` again.

TCC is per-responsible-process, so "does Incurator have access" has no single
answer — it depends on which process asked. **A Dashboard tab showing a snapshot
can be stale within minutes**, and a cached one (the modal holds
`_liveStatusPromise` for its lifetime) can be stale immediately.

## 2. Objective

When Incurator cannot read a file, it says **which folder to grant**, in the
place the user already is — and it distinguishes "not permitted" from "not
downloaded", because a picker fixes only the first.

## 3. Explicit Non-Goals

- Nothing about the two surfaces. **Corrected 2026-09-02, by the user:** the
  first draft of this plan deferred BOTH the picker and the Dashboard tab on the
  grounds that TCC propagation was unverified. That was the wrong call and the
  user said so — *"저게 이번 릴리즈 핵심인데 다 빼버리면 어떡해"*.

  CLAUDE.md is explicit that the stability tiebreaker settles engineering trades
  and NOT this one: *"when the stable option means the product does less, that is
  a product decision"* and it goes to the user. Deferring the deliverable on an
  unfinished measurement was a product decision made silently.

  It was also unnecessary, and the plan already said why: design so a failed
  grant is VISIBLE rather than silent. See D6.
- A tab of green rows. If nothing is denied, the surface says so in one line.
- Widening `probe`'s contract or adding TCC detection logic.

## 4. Locked Design Decisions

### D1. Carry `grant_folder` to the boundary, then read it

The structured folder survives from the exception to the plugin. `AddOutcome`
gains the field; the four flattening sites pass it through; `incuratorClient.ts`'s
normalizer reads the one that already arrives and is thrown away.

This is the whole foundation. Everything else is a consumer of it.

### D2. Fix `grant_root` to consider the path itself

Test `path` before walking `path.parents`, and resolve symlinks so `probe` and
`grant_root` agree on what they are looking at. A denied root must return itself.

The existing behaviour for a file inside a denied folder is preserved, and a test
pins both shapes.

### D3. Distinguish "not permitted" from "not downloaded"

`Reachability` gains a value for a dataless/evicted file. `probe` classifies it
rather than collapsing it into `MISSING`, and the message says "not downloaded
from iCloud" instead of naming a folder to grant that is already granted.

Getting this wrong sends the user to change a setting that was never the problem
— the same failure `grant_root`'s docstring was written about.

### D4. Report unprompted, and only report what is wrong

`wiki reindex` already prints the fallback count, and that is the signal that
found the remaining five. This release makes the same information name folders,
and keeps it on the unprompted path. **A tab the user must open is weaker than a
line the command prints**, so the tab comes second and shows one line when
nothing is denied.

### D5. The Dashboard tab ships, and it is the button that makes it worth opening

One row per root, its verdict, and a grant button on any row that is denied. When
nothing is denied it collapses to a single line rather than a wall of green rows
nobody needs.

The row's verdict must come from the backend, not the plugin: `probe` and
`grant_root` already own that logic and a second implementation in TypeScript
would drift. Note the trap — `probe` opens a path as a FILE, so a readable
DIRECTORY returns MISSING; the endpoint disambiguates rather than the caller.

### D6. The picker ships, and VERIFIES rather than assumes

Whether a grant obtained through an Electron open panel reaches the spawned
Python backend is not fully established. The measurement did find a live analog —
Claude.app, an Electron app with the same hardened-runtime, non-sandboxed shape
as Obsidian, propagates its own TCC grants through four process hops into
arbitrary spawned commands — but Obsidian itself is unconfirmed, and this machine
can no longer produce a fresh denial to confirm it with.

So the button does not assume. After the user picks a folder, the backend
**re-probes it and reports what it found**:

- readable → say so, and offer to retry whatever failed.
- still denied → say THAT, plainly: the folder was granted to Obsidian and the
  backend still cannot read it. Name the folder for System Settings, which is
  where the user would otherwise have been sent with nothing.

That turns the open question into a visible outcome on the user's own machine.
It is strictly better than today, which says nothing at all, in both branches —
and it is the measurement, run by the feature instead of before it.

## 5. Stop Conditions

Stop and report if fixing `grant_root` changes what any existing caller receives
for the file-inside-denied-folder shape — that is the shape production depends on.

## 6. Execution Phases

- **P1** — `grant_root` considers the path itself and resolves symlinks. Tests
  for both shapes plus a symlink.
- **P2** — `probe` separates evicted from missing; the message differs.
- **P3** — `grant_folder` survives to the plugin: `AddOutcome`, the four
  flattening sites, and the normalizer that drops the one already arriving.
- **P4** — the unprompted report names folders, grouped, not one line per source.
- **P5** — `wiki plugin access`: one backend command returning a row per root
  with its verdict and the folder to grant. Disambiguates a readable directory
  from MISSING.
- **P6** — the Dashboard tab, rendering those rows.
- **P7** — the picker, and the re-probe that reports what actually happened.
- **P8** — docs (SYSTEM_BEHAVIOR §12.3, PLUGIN_SCHEMA, guides EN then KR),
  version bump, CHANGELOG, ROADMAP.
