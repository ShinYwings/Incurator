# RELAY

**Branch:** `release/v0.79.0` — pushed, PR open, awaiting review + CI.

## What shipped

ROADMAP E2. The entry asked for a bigger chunk size and a reindex; measuring the
cause first said the chunker never fires and the INDEX was holding each span's
first 200 characters. Fixed by indexing hydrated full text.

Verified on the 42 of 49 documents this machine can read: truncated index bodies
564 -> 3, and a term past character 240 went from 1-of-6 findable to 65-of-65.

## The thing to pick up next

**E5 — folder permission.** Not optional bookkeeping: it is what blocks the other
7 documents, one of which holds 8,692 spans. Their PDFs are in
`~/Library/Mobile Documents` and macOS denies the process access, so no code can
hydrate them.

The backend ALREADY computes the answer — `file_access.grant_root` returns the
exact folder to grant, verified as `~/Library/Mobile Documents` on this machine —
and `plugin/src` contains zero references to it. Scope agreed with the user:
a first-touch grant button, and a Dashboard tab showing which roots are readable.

**Start with the measurement, not the UI.** The backend is a separate process
Obsidian spawns; whether a grant made through an Electron folder picker reaches
it is unestablished, and this repo has been wrong about TCC repeatedly.

## Two patterns this repo keeps re-learning

- **Check the premise before building.** E2's stated cause was wrong, and three
  releases running, the entry's own framing was the thing to measure first.
- **Half-wiring and cutting from the wrong end** — v0.77.0 and v0.78.0 each paid a
  release for these, both caught by review rather than by the author.
