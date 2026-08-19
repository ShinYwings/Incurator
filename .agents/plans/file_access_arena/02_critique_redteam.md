# Critique on the probe-and-state proposal

Date: 2026-08-20 | Agent Persona: red_teamer

## 1. Vulnerabilities & Flaws

### F1 — CRITICAL. `probe()` opens files during resolution and nobody measured it

The proposal admits this under Cons and moves on. That is not good enough,
because the cost is not one `open()` — `resolve_pdf` walks a *candidate list*,
and `zotero_root_candidates` grows with every configured root plus every
`prefs.js` value. Today each candidate costs a `stat`. After this each costs an
`open` + `read(1)` + `close`.

Worse, the pathological case is exactly the case this plan exists for: a
**denied** candidate. A TCC denial is not a fast `EACCES` from the filesystem —
it can involve a userspace daemon. If a denial costs milliseconds rather than
microseconds, and resolution walks several denied candidates per source, an
ingest over hundreds of sources pays for it repeatedly.

**Required before any code: measure `probe()` on OK, MISSING and DENIED paths,
and measure the candidate-list length on the real vault.** If DENIED is slow,
the design needs a per-run cache keyed on the grant folder, not the file — one
denial for `~/Documents` answers for every file beneath it.

### F2 — The retry loop turns one denial into N denials

`_first_readable_pdf` keeps walking after a DENIED candidate to look for a
readable one. Combined with F1 that multiplies the expensive case. And it runs
again for the **next source** in the same folder, and the one after that. A
vault with 40 Zotero attachments behind one ungranted folder pays 40× for a fact
that was settled on the first probe.

**Required:** a process-lifetime memo of denied grant roots. It is not a cache
of file state — grants do not change mid-run without the app restarting, which
the docs already tell the user to do.

### F3 — Letting `PermissionError` escape the parser breaks a boundary on purpose

`parsers/pdf.py` raising `ParserError` for everything is not sloppiness; it is a
typed boundary. Callers catch `ParserError`. Letting a bare `PermissionError`
through means every caller of `parsers.parse` now has a second exception type to
handle, and the proposal audits none of them.

**Required:** enumerate the callers. Either they all handle it, or the boundary
keeps its type and carries the reason — e.g. `ParserError` with a
`reason="denied"` attribute, or a `ParserAccessDenied(ParserError)` subclass so
existing `except ParserError` keeps working while new code can be specific.
The subclass is almost certainly right and the proposal did not consider it.

### F4 — `_grant_root` guesses, and a wrong guess is worse than no guess

Walking up to "the first TCC-relevant ancestor" hardcodes a list of macOS
locations. On a path that matches none of them it returns… what? The proposal
does not say. And the measured table shows `~/Library/CloudStorage` is *readable*
here — so a Dropbox path would produce a `grant_folder` the user does not
actually need to grant, sending them into System Settings for nothing.

**Required:** derive the grant root by *probing*, not by matching a list — walk
up from the file and report the shallowest ancestor that is itself denied. That
is measurable and needs no table. If every ancestor is readable, say only that
the file is denied and do not invent a folder.

### F5 — "a denied candidate outranks missing" is a silent behavior change

Today the first *existing* candidate wins. After this a later *readable*
candidate can win instead — the proposal calls it intended. But `resolve_pdf`
also returns `path` that callers persist (`sources.external_ref`, the plugin's
open-in-viewer). Changing which candidate wins can silently repoint a source at
a different file with the same name in a different root. The proposal has no
test for this and does not mention identity at all.

**Required:** a test pinning that when two candidates both exist and the first
is denied, resolution reports DENIED for the first rather than silently
selecting the second — or, if selecting the second is genuinely wanted, that the
switch is recorded. Quietly changing which file a source points to is worse than
either failure.

### F6 — The plugin is out of scope and the plan does not say what that costs

`ExternalPdfView.ts:1385` goes `existsSync` → `readFileSync`. After this change
the backend reports DENIED correctly and the plugin still throws a raw Node
error at the user. Half a fix, shipped as a whole one.

**Required:** either include the plugin's read path or state in the plan that
the plugin still surfaces raw errors and why that is acceptable for one release.

## 2. Suggested Alternatives

- Keep `probe()`. Opening is right; the objection is cost, not correctness.
- **Add a P0 that measures probe cost by outcome and candidate-list length**,
  and let the number decide whether F2's memo is required or merely nice.
- Subclass `ParserError` (F3) rather than escaping it.
- Derive the grant root by probing ancestors (F4).
- Pin the selection-order change with a test (F5).
- Say explicitly what the plugin does not get (F6).
