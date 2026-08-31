# RELAY

**Branch:** `release/v0.77.0` — pushed, PR open, awaiting review + CI.

## What shipped

The Quick Query popover returned nothing when asked for a reference's title, and
the answer was in the last pages of the PDF already open. The root cause was a
prompt that promised a tool the CLI path never injects and denied having the one
it does; the model reached for a URL reader outside the allow-list and the turn
was auto-denied.

That opened a coverage audit across {paper PDF, book PDF, markdown note} x
{popover, sidechat}, on the axis the user corrected it to: not what a reader
needs, but what a reader DOES. Sixteen findings across two Arena audits —
thirteen fixed, three judged and recorded. Two more came from driving the real
Obsidian vault, which fixtures could not have produced.

Two patterns recur and are worth remembering:

- **Cutting from the wrong end.** A book's outline, a long note, the system
  prompt, a bibliography scan — all correct for a paper, all wrong once the
  reader is not at the head.
- **Half-wiring.** A feature landed on one surface and silently absent on the
  other, four separate times.

## Status

- [x] Implementation, docs (EN then KR), version bump, CHANGELOG
- [x] Local gates: pytest 1884, vitest 1234, ruff, mypy, tsc
- [x] Verified live in Obsidian against the real vault
- [ ] `/code-review:code-review <PR#>` — MANDATORY before merge
- [ ] CI green, then merge

## Next

Run the code-review skill on the PR, fix what it finds, merge. Then the next
ROADMAP item — E2 (chunk size / reindex, user already approved) and E6's
duplicate-source merge (also approved).
