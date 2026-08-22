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

The queue is ordered by leverage. The top three:

1. **Korean questions never reach the global/explore routes** — `router.py:41`
   is a pure-English regex, verified unchanged. A Korean "synthesise across my
   sources" is answered from spans alone; L3/L4 are unreachable from the language
   the user writes in.
2. **L3 has no resume** — all 36 sources sit at `l3_status='error'` on one
   capacity refusal. The v0.63.0 shape transfers, but L3's unit of work is a
   corpus-wide cluster, so the key needs its own design.
3. **`.curator` state is growing** — `sessions.json` 17 MB (was 15), sync
   journals 89 MB (was 24), `compress=True` still unused.

## Environment notes

`.venv` is an **editable install pointing at the working tree**, so every `wiki`
call on this machine — including the plugin's backend — runs whatever is checked
out. It matched master at v0.63.0.

The vault DB is at `SCHEMA_VERSION 14`. A peer's export in `.curator/sync/` is at
v12 and was already being skipped before this release (local was 13).
