# v0.80.0 Briefing — Incurator knows which folder to ask for and never asks

## What happened, in order

2026-09-01, shipping v0.79.0: hydrating span text for the search index failed on
**10,176 of 11,774 spans**. Not a code fault — 7 of 49 documents raised
`ParserAccessDenied` because their PDFs sit in `~/Library/Mobile Documents`
(iCloud) and the process could not read it. One book accounted for 8,692 of them.

Those sources ingested fine in July and August. Access existed then and stopped
existing, with nothing said. That is the user's own scenario, in their own vault:
**the PDF store moved to the cloud after ingest, and the system went quiet about
it.**

2026-09-02, this session: the grant now exists on this machine. All 49 documents
reparse, the reindex dropped from 10,176 failures to 5, and truncated index
bodies went 4,304 → 26 (21 of which are spans whose true text is exactly 200
chars, so only 5 are real failures). **The v0.79.0 fix was never the limit; the
permission was.**

That is the whole argument for this release. The system did the right thing and
could not say why it was failing, and the user had to find out by asking an agent
to dig through a database.

## Re-measured after the grant appeared, 2026-09-02

Same code, same vault, permission now present:

```
documents reparseable:            42 -> 49   (0 blocked)
hydration failures on reindex: 10,176 -> 5
truncated index bodies:         4,304 -> 26
```

Of those 26, **21 are spans whose true text is exactly 200 characters** — not
truncated at all, merely the same length as the cap. Five are real failures. So
the vault-wide figure is 99.5%, matching exactly what was measured on the 42
readable documents before. **The v0.79.0 fix was never the limit.**

Two things follow, and a proposal must respect both:

- The feature being built here is worth building because a permission problem
  cost a release's verification and was found only by an agent reading a database
  by hand. It is NOT worth building to fix a code limit, because there wasn't one.
- The v0.79.0 fallback counter is what surfaced the remaining five. Whatever this
  release adds must not replace that signal — a UI that only appears when someone
  opens it is weaker than a number the reindex prints unprompted.

## What already exists, and what does not

`file_access.probe(path)` classifies OK / DENIED / MISSING.

`file_access.grant_root(path)` walks upward and returns the **shallowest folder
the user must grant** — verified on this machine, it returned
`~/Library/Mobile Documents` exactly. Its docstring already records why it probes
instead of consulting a table of known macOS locations: a table would have named
`~/Library/CloudStorage`, which was readable, sending the user to change a
setting that was never the problem.

`ParserAccessDenied` carries that folder to three call sites that surface the
message.

`grep -r` over `plugin/src` for any of this returns **zero hits**. The backend
computes the answer and nobody shows it.

## Scope, agreed with the user 2026-09-01

1. **A first-touch prompt.** On `ParserAccessDenied`, the plugin offers a button
   that opens a native folder picker at `grant_root(path)`. macOS grants access
   to a folder chosen in an open panel, so choosing it IS the grant — no trip to
   System Settings and no instructions to follow.

2. **A Dashboard tab for granted folders** (user, 2026-09-02: *"어떤 폴더의 권한
   부여를 얻었는지 backend 쪽에서 tab 하나 만들어서 확인할수 있으면 좋을거같아"*).
   The reader should see which roots Incurator can read and which it cannot,
   **without hitting an error first**. Same modal as the other diagnostics
   (`plugin/src/ui/incuratorDashboardModal.ts`). One row per configured root and
   per source root, its `probe` verdict, and the same grant button on a denied
   row.

## The measurement this release must start with

The backend is a **separate process** Obsidian spawns. TCC attribution normally
follows the responsible process, so a grant to Obsidian ought to reach the
spawned Python — but this repo has been wrong about TCC repeatedly, and
`grant_root`'s own docstring is a record of one such correction.

**The machine is now a poor test bed for exactly this**, because the grant
already exists here and every process can read the folder. A proposal must say
how it establishes propagation WITHOUT relying on a fresh denial that this
machine can no longer produce. Options worth costing: a folder that is still
denied (`~/Documents`, `~/Desktop`, `~/Downloads` are TCC-protected by default),
a synthetic denial via a `chmod 000` directory (NOT the same mechanism — say so
if you propose it), or accepting the uncertainty and designing so that a failed
grant is visible rather than silent.

If propagation does NOT hold, the design changes: read inside the Obsidian
process, or pass a security-scoped bookmark. Building the UI first and finding
out afterwards is the failure this phase exists to prevent.

## Constraints

- Zotero has TWO directories — the data dir and the attachment dir — granted
  separately. A UI that shows one and calls it done is the same mistake in a new
  place.
- `probe()` opens the path as a file, so a DIRECTORY returns MISSING, not OK.
  Any UI reading `probe` on a folder must account for that or it will report
  every readable folder as missing.
- No new always-on subprocess, no new external dependency.
- The plugin must not become the place that decides what a root is; the backend
  already owns `grant_root`.
