# v0.82.6 Cache Preservation Evidence Ledger

## Rollback anchor and repository state

Baseline `218176e3` on master; v0.82.5, SCHEMA_VERSION 14. Work branch
`fix/gc-cache-preservation`. Initial worktree clean; all subsequent dirty paths
before implementation were this session's `.agents/` records. Revert commits
for rollback; never reset shared history. No production migration or deletion.

## P0 evidence

Independent Arena confirmed a zero-source DB with a tombstone is reclaimable,
and unknown populated SQLite is schema-mutated then classified empty. Disposable
fixtures only. Code also passes stale preview entries directly to rmtree.

Read-only production measurement: DB 341782528 bytes; sources 49; prompt_runs
5059; query_traces 123; compiler_generations 184; job_events 6615; deleted_records
54274. Sessions file 9284872 bytes, 18 sessions, 65 tombstones. No gc settings.
These counts are not a reclaimable-byte estimate or permission to delete.

Actual cache namespace file inventory includes marker, database, runtime dirs,
dashboard/log markdown, sync reports, database backups and WAL/SHM. Only the
marker and a recognized empty closed database are covered by this patch.
SQLite runtime is 3.40.1 (PRAGMA table_list available).

Existing testbed has testbed:true and three registered sources. Production
last_root is `/Users/shin/shinywings/second_brain`; preserve it. Existing private
scenario is complex_math_backprop, whose historical plan includes retired EXH
semantics; do not reinitialize it or invoke its stale mutation commands.

## Validation results

Initial TDD baseline: 29 expected failures / 14 passes, ruff green. First
implementation: 41/43 pass; supported collection exposed mode=ro sidecar creation.
Private-copy revision independently reviewed, with source mutation regressions.
Current focused cache + prompt-cap + session suite: 67 passed in 2.14 seconds;
ruff green. Full checks, testbed smoke and actual review skill remain pending.
