# RELAY — IDLE

## Last shipped

**v0.63.0 (#171) — graph extraction that can finish.** Hartley is published:
`attempt=1 staged 0->24 calls=44 failed` then `attempt=2 staged 24->0 calls=0
done`. One `authoritative` generation, all 5,358 units attributed,
`graph_entities` 1,347 -> 2,196.

## `.agents/` was consolidated on 2026-08-23

Three Arena audits and two umbrella plans had been running in parallel with
overlapping numbering (`5c`, `11` and `12` each appeared twice in the roadmap).
Every open item was re-checked against the code at v0.63.0 and folded into one
queue: `ROADMAP.md` is now a single numbered list, 660 lines -> 513.

`USER_REPORT.md` is empty; its two items became ROADMAP 19 and 20.

**What the walk found.** `knowledge_value_arena` had **never been triaged** — its
four P1s are now items 1, 3 and 5. `system_defect_audit_arena` shipped ~29 of 29
findings except one (item 6), which survived because the synthesis said "merge
rather than fix twice" and the batch fixed two of three sites.

## Where to start

The queue is ordered by **stability**, per the user's rule (2026-08-23):
*"기능을 추가하기보다는 시스템 안정이 우선"*. Phases A→F; within a phase order is
free, across phases it is not.

**Phase A is next** — no schema, no contract, nothing that can destabilise a
release. It makes the system stop lying about its own state, which is the
precondition for judging anything in B–F:

- **A1** Korean questions never reach the global/explore routes (`router.py:41`
  is a pure-English regex; 514 community reports exist, so the fix pays off
  immediately)
- **A2** query expansion fails silently — three unlogged swallows
- **A3** 977 units (11%) never enter the index — *report* the gap first
- **A4** `wiki status` calls the vault healthy with an empty L4

**Two constraints on every release**, recorded at the top of the roadmap: at most
**one** contract or schema change per release (v0.63.0 carried two), and a **live
run is a release gate** for anything touching ingest or retrieval.

## Found while sequencing

**L4 has never produced anything** — `synthesis_nodes` 0, SYN files 0, sources at
`l4_status='done'` 0, while three retrieval modules read that table. This is not
"L4 failed recently": L3 has 514 community reports dated 2026-08-22 and its
`error` is a capacity failure on a working layer. L4 has no such history.
Filed as **C2 — diagnose before designing**.

## Environment notes

`.venv` is an **editable install pointing at the working tree**, so every `wiki`
call on this machine — including the plugin's backend — runs whatever is checked
out. It matched master at v0.63.0.

The vault DB is at `SCHEMA_VERSION 14`. A peer's export in `.curator/sync/` is at
v12 and was already being skipped before this release (local was 13).
