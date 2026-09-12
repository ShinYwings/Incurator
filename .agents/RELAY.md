# RELAY

**Branch:** `fix/gc-cache-preservation`

## Goal

Resume ROADMAP.md's active queue, starting with B1/B2 state retention.

## Plan Reference

`.agents/plans/06_gc_cache_preservation.md` — approved cache-only v0.82.6;
independent proposals, cross-critiques and defenses are complete.

## Analysis & Reasoning

The prior IDLE stub was stale: the inbox is empty but the roadmap explicitly
queues retention first. v0.82.5 remains the current release. Existing GC already
supports session windows, an unreferenced prompt-run cap and conservative cache
cleanup. Reconcile shipped behavior against remaining requests before coding.

## Progress Status

- Read relay, repository rules, inbox, roadmap and planning template.
- Clean master at `218176e3`; `git pull --ff-only origin master` is current.
- Arena concluded; discovered cache misclassification/schema mutation and separate
  prompt-lifetime/session-writer defects. Findings triaged into ROADMAP.md.
- Implementation phase: documentation and failing cache regressions in progress.
- Retried interrupted agents successfully after user requested retry.

## Critical Context/Blockers

Keep full active-session replay (v0.82.3 user correction). Actual production
deletion/migration needs authorization. Tombstones must not expire without a
proven offline-peer floor. Session windows belong to the user; prompt-run policy
was delegated. Inspect remaining history policies for a real product fork.

## Immediate Next Action

Finish docs-first/TDD cache correction, verify, invoke actual review skill, run
CI and merge v0.82.6. Prompt lifecycle and GC Dashboard remain distinct follow-ups.
