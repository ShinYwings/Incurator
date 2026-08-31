# RELAY

**IDLE.** No active goal. `master` is at v0.78.0, working tree clean.

Git log is the history; this file is live state only. It is a stub on purpose —
accumulating session notes here is what buries the one thing the next agent
actually needs.

## Where to pick up

`.agents/ROADMAP.md`. The queue is Phase E and Phase F.

Two items are already approved by the user and waiting:

- **E2** — retrieval chunks are too small (median 181 chars; 56% under 200).
  Shipping it re-embeds the corpus, which is a reindex of the user's vault. The
  user approved that on 2026-08-31.
- **E6's sibling work is done** — shipped v0.78.0.

## Two things this repo keeps re-learning

Both cost a release each in v0.77.0 and v0.78.0, and both were caught by review
rather than by the author:

- **Cutting from the wrong end.** A constant correct for a paper is wrong for a
  book; head truncation is wrong whenever the reader is not at the head.
- **Half-wiring.** A fix lands on one surface, one call site, one code path — and
  its sibling ships unchanged behind a green test. If a guard cannot see the
  sibling, widen the guard, not the exemption.
