# Fleet Proposal: A Retention Tombstone Must Not Erase a Delayed Live Reference
Date: 2026-09-12 | Agent Persona: Distributed State / Data Preservation Reviewer

## 1. Core Logic & Implementation

### Verified current behavior

The current protocol does not preserve a referenced prompt run when that
reference exists only on an offline peer. A local transaction or local producer
reservation cannot repair that cross-device schedule.

- `db_sync.py:47–74` places deletion records first and includes reports and
  prompt runs in full exports. `export_knowledge` also supports a restricted
  `tables` list (`db_sync.py:969–986`); not every API-produced snapshot contains
  the reference closure of each artifact.
- Prompt runs rank by immutable `created_at` (`db_sync.py:110`). Finishing a
  prompt or creating a newer report does not make its prompt row outrank a later
  tombstone.
- Import applies tombstones before upserts (`db_sync.py:1185–1203`).
  `_apply_tombstone` checks row revision, then deletes the target row without
  checking retained references (`db_sync.py:1551–1599`).
- `_row_is_blocked_by_tombstone` rejects an incoming prompt whose creation time
  is older than deletion (`db_sync.py:1632–1675`). A later imported report does
  not lift that prompt tombstone.
- Reports store `prompt_run_id` without a foreign-key constraint to prompt runs
  (`db/schema.py:536–563`), so the import can succeed with dangling provenance.
- Local imported-export checkpoints (`db_sync.py:2785–2819`) are not outgoing
  acknowledgements. There is no proof of peer quiescence, no complete active
  membership floor, and no retained reference closure in tombstones.

### Independent two-device reproduction

Executed entirely inside one TemporaryDirectory using real `db.init_db`,
`gc.apply_prompt_run_cap`, `db_sync.export_knowledge`, and
`db_sync.import_knowledge`. No monkeypatching of application logic, no production
paths and no provider calls were involved.

1. Initialize devices A and B with identical `PTR-old` and `PTR-new` completed
   runs, created in 2020 and 2026 respectively.
2. B creates a community report referencing `PTR-old`. Keep B's new report
   offline from A, and export B's full snapshot to a disposable file.
3. A runs keep=1. It knows no references to the old run, deletes it, and exports
   the resulting tombstone.
4. Import B's pre-deletion snapshot into A. Import A's deletion snapshot into B.

Observed output:

```text
A_cap_deletes 1
A_after_peer_import {'prompt_present': 0, 'report_present': 1,
                     'tombstone_present': 1, 'dangling_reports': 1}
B_after_tombstone_import {'prompt_present': 0, 'report_present': 1,
                         'tombstone_present': 1, 'dangling_reports': 1}
```

Both paths fail. A refuses the available prompt row while importing its owner;
B deletes a prompt that it already knows has an owner. Reordering these two
imports does not supply a missing reference check or restoration rule. Re-export
will carry the damage forward. This is a confirmed fleet-wide correctness
failure, not just a hypothetical future publisher.

### Exact impossibility boundary

Let A observe the same local database and received snapshots in two executions.
In execution E0, disconnected B has no owner for run R. In execution E1, B has a
live report referencing R that A has not received. Until a B message arrives,
A's observations are identical. Therefore no local-only algorithm can both
prove R globally unreferenced and permanently delete its last recoverable
information during that interval.

This rules out claiming safety from a local lock, local lease, age grace period,
recent-sync timestamp, or local reference scan. It does **not** prove every
finite local reclamation design impossible. Reclamation with deferred global
finality, restoration from a valid owner, or retaining a minimal required
provenance representation changes the information available and must be
considered explicitly.

The existing cap already exempts arbitrarily many referenced rows. It is not a
strict total-database row or byte bound. Do not argue that preserving a delayed
owner necessarily violates an advertised fixed total bound that does not exist.

### Feasible alternatives and exact capability costs

| Alternative | What it preserves | What it costs or requires |
|---|---|---|
| Cooperative distributed ownership and deletion acknowledgement | Permanent deletion of globally ownerless runs; full offline history survives | GC finalization waits for all participating peers, durable membership and retirement rules, protection for old snapshots/rejoin, and local producer lifetime. An offline peer can delay reclaiming its potential evidence indefinitely. |
| Reference-aware retention with recoverable prompt provenance | Local cap can reclaim currently unreferenced rows while delayed valid owners restore/protect required runs; offline work remains useful | New merge semantics where a live owner outranks a retention-only deletion, plus durable provenance accompanying owners and full reference-closure validation. Old peers must not re-delete restored rows; needs fleet compatibility gating. Permanent erasure is not immediate finality. |
| Preserve minimal prompt record and compact optional heavy payload | Required trace identity/resume hashes can survive indefinitely without peer acknowledgements; potentially large byte savings | Does not satisfy a whole-row/count cap. Removing source/span audit payload changes trace-inspection capability unless it is losslessly retained elsewhere. Field consumers and archival recovery must be audited before selecting this. |
| Enforce current tombstone finality despite delayed references | Immediate fleet propagation and simple deletion semantics | Loses valid offline audit/resume provenance; disproves the promised referenced-run preservation. This is a product loss, not an engineering fix, and cannot be silently selected. |
| Never reclaim successful runs | Simple survival of completed provenance | Removes the existing ability to cap unreferenced successful history and still needs pending-run lifetime handling. Not an autonomous substitute for the user's delegated cap. |

The second alternative deserves investigation before declaring an unavoidable
product escalation. The user's intended behavior is preservation of referenced
runs, and the cap already excludes them. A delayed owner restoring its required
row could implement that intention with equal useful capability. Whether it is
feasible with a small stored-contract change depends on the independent producer
and payload audit, not just changing `_apply_tombstone` to return early.

### Required design obligations for reference-aware retention

A naive import guard alone is insufficient:

1. On B, a tombstone must not destroy a run referenced by B's current artifacts
   or active producer owners. On A, an incoming owner may arrive after R was
   already deleted; restoring R requires its complete required record, not just
   the ID embedded in the report.
2. An incoming snapshot must carry or safely recover the required prompt closure
   for owners it contains. Default full snapshots often do, but arbitrary table
   subsets, a previously damaged peer, or an old export may not. Missing payload
   must be a loud, recoverable state; do not invent a prompt record from an ID.
3. Retention deletion must have a distinct conflict meaning if deliberate
   non-retention deletion is also possible. Existing `deleted_records` has no
   reason field. Verify all deletion writers before repurposing every prompt
   tombstone as revocable garbage collection.
4. Reference arrival order cannot matter. The importer must consider the
   complete incoming owner set or stage the required closure before applying
   prompt deletion, including JSON IDs and nonstandard scalar columns.
5. Peer versions must agree. An old importer blindly applies the tombstone and
   recreates this failure; shipping a new local ownership table alone does not
   upgrade that fleet behavior. Schema-version rejection/rejoin rules need a
   rehearsal with old snapshots and delayed exports.
6. Restoration must not become unlimited resurrection of genuinely unreferenced
   prompt history from every stale snapshot. Only a valid retained owner may
   require resurrection; unreferenced stale rows remain subject to the cap.
7. Full local lifecycle protection remains necessary: start, provider completion,
   deferred staging and final artifact publication cannot leave a vulnerable
   interval. Do not hold SQLite's writer lock over provider latency.

### Reproduction and future verification matrix

- Reproduce the exact E1 schedule above for a scalar report reference and JSON
  query references. Assert prompt existence and successful artifact/resume
  lookup after both import directions, not merely import counts.
- Import a deletion onto a peer with an already committed owner. The owner and
  its evidence must survive, or import must fail explicitly without damage.
- Import an owner and its prompt after a local retention deletion, in both file
  orders and through full/restricted snapshot paths. Verify no fabricated row.
- Reimport a stale unreferenced prompt after GC. Ensure the intended cap still
  works and that the owner restoration exception cannot restore everything.
- Cover pending and completed-unpublished producer states with GC and peer
  deletion during the interval; verify final publication after GC returns.
- Test old-client/new-client import compatibility, cache-loss recovery, stale
  snapshots, interrupted GC and failed restoration as separate state schedules.

### Measurements and immediate recommendation

Parent's read-only measurements report 5,060 runs and 17,075,336 bytes in
`source_span_ids`, with other prompt columns around 1.1 MB. This agent did not
independently query production. Those figures argue for considering lossless
payload placement, but cannot establish that span IDs are disposable or that
compaction satisfies the configured count cap. No production GC setting is
active and no urgent pressure requires selecting a destructive shortcut.

Do not implement a local-only fix as a complete solution. Use the other Arena
proposals to determine whether reference-aware recoverability plus producer
ownership preserves the existing contract. If its required finality/availability
trade is unavoidable, present a concrete choice between deferred reclamation
while peers are offline and revisable retention with owner-backed restoration.
Do not ask the user merely whether a schema change is permitted; that is already
an autonomous planning responsibility.

## 2. Pros & Cons

This proposal establishes the actual failure through the real sync API and
separates permanent global deletion from finite local reclamation. It avoids
prematurely declaring a product fork when reference-aware restoration might
preserve the user-visible capability.

A complete solution spans more than GC: prompt producer ownership, transport
closure, deletion merge semantics and compatibility all matter. The alternatives
are intentionally not implemented here, because choosing one before the other
independent audits would repeat the transaction-only blind spot. Existing
unreferenced cap behavior, delayed offline evidence, and trace-inspection value
must all be accounted for in the final synthesis.
