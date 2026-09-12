# Critique on Backend / Schema Proposal
Date: 2026-09-11 | Agent Persona: Adversarial Synchronization / Data Preservation Reviewer

## 1. Vulnerabilities & Flaws

### The original transaction-only release recommendation is insufficient

The original `BEGIN IMMEDIATE` recommendation fixes a real inconsistency: a
reference committed after the eligibility read but before the delete can evade
the scan. It does not establish the lifetime property that the cap actually
needs. The proposal's final revision recognizes this; I independently agree
with that revision and reject shipping the original recommendation as the
resolution of prompt retention safety.

Concrete production ordering, independently traced:

1. `prompting/trace.py:55–80` calls `db.record_prompt_run`, which commits a
   `pending` row in its own connection (`db/_entities.py:2689–2707`).
2. The provider and validation run outside that transaction. The persisted
   prompt result is finished through another connection
   (`db/_entities.py:2722–2737`). That UPDATE does not verify an affected row.
3. `pipeline/graph_index.py:253–261` receives the prompt result. The validated
   batch obtains its durable `graph_batch_results.trace_id` reference only in
   another transaction at lines 300–312. Without a resume source, collected
   entities and relations remain in memory until source publication
   (lines 323–328).
4. The cap sorts all unreferenced runs without filtering an active lifetime
   (`gc.py:501–506`). A slow prompt can become older than the newest retained
   records while another call completes. A paused successful writer can remain
   unreferenced after validation for an arbitrarily long interval.
5. A GC writer reservation during either interval permits deletion to commit
   first. The subsequent publisher is then unblocked and inserts a reference to
   the deleted ID. No foreign key from `graph_batch_results.trace_id` to
   `prompt_runs` exists (`db/schema.py:524–532`). The deletion's tombstone can
   propagate fleet-wide.

This is not a speculative malicious writer or remote-only limit: it is the
ordinary split transaction layout. A test that merely observes SQLITE_BUSY on
an insertion attempted while GC owns the writer slot proves serialization,
not safe eventual publication. The test must let the publisher finish after
GC commits and then validate provenance. Excluding pending runs alone still
leaves the successful-but-not-staged interval.

### Related retained-reference error path is a distinct contract gap

Malformed `query_traces.prompt_trace_ids` values currently fall through to an
empty contribution (`gc.py:476–482`), unlike operational SQL failures, which
fail closed. An unreadable reference set is not a proof of non-reference. Do
not repair its bytes during GC or guess which run IDs it intended. Capture it
with a reproduction and either a small independently justified fail-closed
patch or the prompt-lifetime plan; do not smuggle it into a cache-only patch.

### Tombstone expiry still lacks its required fleet state

The backend correctly treats database deletion as fleet-wide. Local
`last_export_id` checkpoints (`db_sync.py:2785–2819`) only say what this device
imported. They cannot prove another device acknowledged our deletion, or that a
restored old snapshot will never rejoin. A timestamp menu, known device list,
or “no file seen recently” check cannot close this gap. Session tombstones have
the same problem. No expiry belongs in the next cache patch.

## 2. Suggested Alternatives

### Release the independent cache proof correction first

The safety proposal's two isolated reproductions establish source-independent
data loss eligibility and schema mutation during inspection. The cache repair
can preserve existing capability and require no new lifecycle contract:

- A normal initialized empty temporary-vault namespace remains collectible.
- Existing source-independent application data, unknown populated tables,
  partial schemas, symlinks, and inspection errors prevent collection.
- Inspect with SQLite read-only URI semantics and correct WAL awareness;
  never schema initialization or `immutable=1` that could overlook WAL data.
- Logical table discovery must distinguish initialized FTS shadow metadata
  from application records. The empirical empty-schema occupied tables are
  `schema_version` and both FTS data/config shadow tables. Ignoring arbitrary
  name prefixes is not a justified emptiness proof.
- Limit automatic deletion to namespaces whose files are exactly understood
  by this proof. Parent inspection reports existing namespaces with backups,
  logs, runtime directories and sync reports. Retain those rather than invent
  a new historical-data expiry or assert that unknown content is debris.
- Recheck marker, root absence, database contents, file set, and namespace
  identity immediately before removal. Preserve a replaced namespace or a
  root recreated during confirmation. Retain active SQLite sidecar states
  when their inactivity cannot be proved.

The final check is not an atomic lease against all possible writers. A process
that creates or writes files after the last check can still race deletion.
Define this patch honestly as correcting discovery and stale-plan authority;
do not assert that it solves general cross-process cache lifecycle locking.
A shared lock protocol would require writers to participate and should be
planned as such, rather than implied by one extra stat or one SQLite lock.

### Prompt lifetime needs an owner, not a timing heuristic

Audit every prompt consumer before choosing the durable representation.
Protection must span run creation, provider completion, deferred staging and
final artifact publication; interrupted owners need a recovery rule. Validate
both a slow pending run and a finished result paused before publication. Also
cover transferred results and references not yet imported from another device.
A reservation/owner record, or another existing durable ownership mechanism
proven equivalent, is a meaningful design candidate. A short grace period is
not a proof; holding a SQLite write lock across a provider call is unacceptable.

Do not silently keep all successful runs forever, turn off the cap, or reject
previously supported successful-run reclamation to make a safety test pass.
Those trade away the shipped capability and require a product decision. Keep
the item active until the actual ownership design, recovery semantics, tests
and compatible fleet behavior are established.

### Consensus

Accept the backend revision: next patch should address the independently
verified cache guard, and leave prompt lifecycle, malformed reference policy,
session concurrent persistence and remaining user-history windows as explicit
follow-ups. A finished cache patch must not be described as finishing B1/B2.
