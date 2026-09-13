# Producer Proposal: Own Every Prompt Until Its Last Possible Publication

Date: 2026-09-13 | Persona: Producer Lifecycle / Local Concurrency Reviewer

## 1. Core Logic & Implementation

### Scope and evidence

This is a design proposal, not an implemented guarantee. I read RELAY, the new
briefing, the saved fleet proposal, and the superseded backend proposal and its
defense before examining the current code. No application code or live data was
changed. I did not repeat the saved two-device reproduction.

The producer has ownership before there is an artifact. Its ownership continues
after validator completion. A retained artifact takes over only after its write
commits. In symbols, for a run \(r\), define \(P(r)\) as an active local producer
reservation and \(A(r)\) as a committed retained artifact reference. The local
deletion predicate must include \(\neg P(r)\land\neg A(r)\), evaluated with the
delete in one SQLite write transaction. Checking either validator status or an
ingest job state cannot establish \(\neg P(r)\).

There are nine actual `run_prompt` call sites, with materially different owners:

| Producer call site | Owner must outlive | Durable handoff, if any |
| --- | --- | --- |
| `pipeline/knowledge_units.py:280` | `_run_batch_with_retry` returning, all recursive sibling calls, and `_persist_units` committing | Every pending unit's own `prompt_run_id`; never just the returned last trace |
| `pipeline/graph_index.py:253` | All graph batches, staging failure fallback, `GraphData` return, and caller's publish or abandonment | `graph_batch_results.trace_id`, then the graph publish transaction |
| `pipeline/community_reports.py:187` | Result validation and `upsert_community_report` commit | Report's `prompt_run_id` |
| `pipeline/community_reports.py:284` | Same, including prose update of an existing skeleton | Updated report's `prompt_run_id` |
| `pipeline/synthesis.py:187` | Every synthesis-node write, or abandonment after an exception | Each created node's `prompt_run_id` |
| `retrieval/orchestrator.py:126` | Answer synthesis, provider-error trace lookup, QTR update | `query_traces.prompt_trace_ids`, including failed synthesis |
| `retrieval/orchestrator.py:220` | Explore candidate writes and final QTR update | Candidates and QTR reference array |
| `query.py:221` | Search-query derivation success/fallback handling | None currently; trace is ordinary cap-governed audit history afterward |
| `backprop_classifier.py:61` | The caller's action planning and possible candidate publication | MCP-created insight candidate; CLI response-only classifications currently have no DB owner |

`prompting/runner.py:205–285` and `db/_entities.py:2674–2737` implement the
creation/completion gap already described in the saved defense. `finish_prompt_run`
updates without verifying that the row exists. Merely wrapping `run_prompt` in
a context manager and releasing on its return repeats the bug.

### The easy-to-miss delayed states

**L2 recursive halves.** `_run_batch_with_retry` returns lists of
`_PendingKnowledgeUnit`, each containing its own trace ID. A valid left half can
wait through a slow right half and deeper recursion. The parent combines both
lists; the top-level `extract_knowledge_units` persists successful halves even
when another half fails (`knowledge_units.py:595` onward). `_BatchResult.trace_id`
is only the last trace and cannot represent this ownership set. The operation
must retain all runs it starts, including failed parent/sibling attempts until
their terminal disposition is known. Existing persisted generation-less units
already provide the correct durable resume owner. No new copy of their parsed
payload is necessary.

**Graph staging is optional and can fail.** The successful result is staged in
`graph_batch_results` before collection, but the write is deliberately caught as
nonfatal (`graph_index.py:300–321`). Without a resume source, there is no staging
at all. `GraphData.entities` and `.relations` then carry results in memory until
`compile_source_l2` publishes them. A lifetime ending at `extract_graph_data`
return, or unconditionally at the staging attempt, misses that real path. The
compile scope must survive through `persist_graph_data` and the generation
publish transaction (`compile.py:450–519`). Existing staged graph rows remain
the recovery owner on failure; their deletion already shares the successful
publish transaction. A staging failure followed by process death still requires
recomputation, as today; this proposal must not pretend to recover parsed output
that the process never persisted.

**Failed query publication is still publication.** `QueryOrchestrator.run`
catches `LLMError`, reconstructs prompt IDs by `prompt_runs.query_trace_id`, then
writes the QTR (`orchestrator.py:84–99`). Releasing failed runs when the runner
raises allows GC to erase the very rows that this recovery query needs. A scope
at `QueryOrchestrator.run`, surrounding this error branch and the QTR commit,
covers both failure and success. The current code catches only `LLMError`; an
unexpected exception may abort without final QTR update. The owner still needs
deterministic cleanup after the caller finishes unwinding. A new policy of
retaining every reverse `query_trace_id` link forever should not be slipped in
as an implementation convenience: establish whether that changes which failed
attempts are promised as retained history before broadening durable references.

**MCP feedback has a later publisher.**
`mcp/server.py:3331–3370` calls `classify_feedback`, closes the client, plans the
action, and only then may call `create_insight_from_classification`.
`insight_lifecycle.py:89–115` records its `prompt_run_id`. The lifetime belongs at
the MCP boundary and includes candidate creation, not merely the classifier.
`commands/plugin.py:1040–1087` is different: its CLI command returns classification
JSON containing `traceId`, with no DB candidate insertion. A response trace ID
does not create indefinite reference protection under today's cap. If the
plugin persists these IDs as a promised audit owner, the artifact audit must add
that real owner/closure; do not invent it or declare it disposable here.

### Existing storage does not already express active ownership

`prompt_runs.validator_status` records model validation, not whether a caller
can still publish. `query_trace_id` exists only for query synthesis.
`ingest_jobs` does not cover CLI/MCP query, correction, and other direct callers.
`graph_batch_results` and unpublished knowledge units are excellent durable
owners after their writes but absent before those writes. No current table
registers all active prompt producers. `prompt_runs` itself also lacks full raw
model output; it stores output hashes, so a stale reservation cannot imply a
recoverable completed parsed result.

The smallest complete local design I can defend therefore adds an explicit
local reservation relation, not a new status meaning or a timer heuristic.
This is a stored-contract release with a migration rehearsal. It is not a patch
that can be honestly sold as a SELECT/delete locking correction.

### Proposed local ownership and publication contract

1. **One scope belongs to an operation that can still publish.** Allocate a
   unique owner token at the outer boundary. For L2 compilation this is
   `compile_source_l2`; for queries it is `QueryOrchestrator.run`; for MCP
   correction it is the entire tool handler. Report and synthesis generation
   can own their own scopes. Search derivation may own a short scope through
   its fallback/result disposition. Nested helpers borrow the scope and never
   close their caller's scope. Direct use of extraction helpers must supply a
   scope that remains open through persistence; returning in-memory graph data
   is not a publication boundary.
2. **Reserve atomically with creation.** Add a local-only relation such as
   `prompt_run_owners(owner_id, trace_id)` with composite primary key and indexed
   `trace_id`. Insert the run and its reservation in the same connection and
   transaction before exposing the ID or calling the provider. Scope bookkeeping
   owns every started ID, including calls that later raise. Do not depend on
   reconstructing ownership from a returned `PromptRunResult` or its last ID.
3. **Completion changes audit fields, not ownership.** It checks that exactly
   one reserved run was updated. Missing rows/ownership are loud consistency
   failures, not successful UPDATEs. No main SQLite write transaction is held
   while a provider runs, while a sibling batch runs, or while a client closes.
4. **Publication checks closure in its transaction.** Reference-writing helpers
   join the caller's connection when supplied. For each new real PTR reference,
   they verify that the required row exists before committing the artifact.
   GC takes `BEGIN IMMEDIATE` before checking owners/references and deleting.
   Publishers likewise perform their row-existence check under a write
   transaction; a read outside it cannot prove that the row will survive until
   the artifact commits. Missing provenance is a recoverable, explicit error;
   inserting a fabricated record from an ID is forbidden. The fleet import path
   uses its validated provenance closure to restore when permitted instead.
5. **Close only after final commit or real abandonment.** Keep all scope pins
   until the outer operation has finished publishing or unwinding. Then remove
   only that owner's reservation rows in one short transaction. Durable
   artifact references independently protect successfully written rows, even
   when a later sibling write failed. Failed/unused runs become ordinary
   unreferenced history eligible for newest-N retention. An optimization to
   release each batch early is unnecessary and makes the initial proof harder.
6. **An ID alone cannot reacquire a deleted payload.** A later writer outside a
   valid scope must either find the retained prompt or present the validated
   owner-backed closure required by the fleet contract. This prevents silent
   dangling publication. Public responses retain existing ID shape; no promise
   is made that a bare previously returned unreferenced trace outlives the cap.
   If a real existing caller depends on that promise, audit and represent its
   durable ownership before implementation.

Explicit scope passing is preferable to an invisible global registry because
the cross-function ownership boundary is the defect. A context-local convenience
may be considered only if it cannot silently fall back to an unowned run when
called from another thread or standalone API. No weak-reference finalizer or
garbage-collector timing can establish final publication.

### Crash recovery without a grace period or a main-DB writer lease

Durable rows alone leak pins after crashes. A PID, heartbeat age, or job status
cannot prove abandonment by a paused process. Add an **OS-held exclusive token
lock for each local owner**, in a local, non-synced namespace associated with
the database. This lock is an exact lifetime witness; it does not serialize
unrelated producers or block SQLite writers during network calls.

The token is unique, created and locked before any reservation is inserted.
The process retains its handle until owner cleanup commits. A reaper tries to
acquire that token nonblocking only for owner IDs already present in the DB.
Failure to acquire means the owner remains live and every reservation survives.
Successful acquisition proves that the old scope cannot still be operating
under its lock. While holding that lock, the reaper takes the DB write
transaction, removes only that owner's reservation rows, and then applies the
ordinary reference-aware cap. The token is never reused and a completed scope
may never resume publication with it.

This covers process termination, cancelled operations, reboot, and arbitrary
pauses without selecting a time limit. A process dying before creation commits
leaves no pin; after commit it leaves a reclaimable owner record; after artifact
commit the artifact survives pin removal. If the owner cleanup DB write fails,
release of the OS handle leaves a stale reservation for the same exact reaper
path. No destructive recovery action is required merely because a heartbeat is
old. User history, staged units, and staged graph payload are never deleted by
owner cleanup.

Implementation obligations are real, not optional footnotes:

- `durable_io.locked_path` is **not sufficient as currently written**. It lacks
  a nonblocking probe, and its Windows branch is only a thread lock
  (`durable_io.py:28,66–74`). Use an actual interprocess primitive on every
  supported platform and test it with separate processes. If a platform cannot
  establish ownership, report inability and preserve pins; do not pretend a
  thread lock proves process death. A platform limitation is not an acceptable
  permanent substitute for implementing the supported platform's primitive.
- Token files cannot live in a normally cleaned temp directory or sync across
  devices. An active token path must not be unlinked/replaced: otherwise a new
  inode could be locked while the producer holds the old inode. Cache cleanup
  must recognize and preserve active ownership state. Token namespace loss or
  unreadable metadata fails closed and is reported; it is not proof of death.
- Reapers must not recreate an absent token and infer abandonment. With no
  reservations the uniquely named token is no longer needed; cleanup must be
  coordinated with the final DB check, and active tokens cannot be renamed.
  A small never-reused owner token file after an interrupted cleanup is not a
  reason to delete prompt evidence.
- Handles need close-on-exec and explicit fork behavior. A child must not
  publish under a borrowed parent scope after the parent releases it. Tests
  must prove no inherited handle accidentally keeps crashed owners live.
- Local owner state is not a transported peer lease. It must be excluded from
  export/import; arbitrary copied cache DBs must not be interpreted as a new
  authoritative running producer. Migration/recovery must explicitly classify
  local owner metadata rather than guessing from its presence.

These requirements make this more than a simplistic lock fix: the ownership
set, outer publication boundary, durable reservation transaction, crash proof,
and fleet integration are all essential. A lock around `run_prompt` alone still
fails every completed-but-unpublished schedule above.

### Fleet integration and API/count consequences

The local design is necessary but insufficient. Accept the saved fleet
proposal's restoration candidate as the best capability-preserving next design:
local active ownership and already committed owners block incoming retention
deletion; valid delayed artifact owners can restore full prompt provenance
after local GC. Export must include complete prompt closure for every exported
owner, including table-restricted snapshots and JSON references. If an owner is
still only in a producer's memory, the origin's local reservation protects its
prompt until publication and the next complete export. A remote tombstone
cannot cancel that local reservation. No distributed heartbeat or temporary
local lock is misrepresented as a peer acknowledgement.

The importer must not discard incoming tombstones merely to avoid deletion and
then let stale ownerless snapshots restore everything. Preserve the distinction
between retention intent and an owner-restoration exception. Only genuine
retained owners justify restoration; raw prompt rows and local-only owner tokens
do not. Exact conflict representation, old-client rejection, source/span ID
remapping, and retention-only versus deliberate deletion semantics belong to
the fleet synthesis and cannot be omitted from this release.

`prompt_runs_keep` remains the newest-N count of **eligible unreferenced runs**.
Active reservations add a temporary exemption just as committed owners already
exempt arbitrarily many runs. This preserves useful reclamation without making
a false fixed total-row bound. A paused live producer can exceed N; that is
necessary to preserve its output. A dead producer is reclaimed after exact
ownership reconciliation. A delayed valid owner can increase retained count by
restoring its required row; that is the existing referenced exemption made
correct across import order.

Preview must use the same eligibility model and report reservations separately
from durable references. Read-only preview must not mutate owner state merely
to improve its projected deletion count. It may conservatively count stale
reservations as protected and identify them for run-time reconciliation; the
run result must report actual deletions. If preview promises exact candidates,
it instead needs read-only nonblocking liveness inspection with the same
fail-closed uncertainty handling, followed by transactional recomputation at
apply time. Do not report the initial plan count as performed deletions.

This design does not claim SQL deletion shrinks the SQLite file. Owner token
and table metadata are small but real local storage and must appear in cache
classification. No new arbitrary file-retention policy is introduced. Prompt
trace APIs continue returning complete current prompt rows; they may temporarily
show pending status while the live producer runs. No compact substitute record
or audit-field removal is needed for the local fix.

### Migration and focused acceptance schedules

The new ownership relation begins empty only when upgrading a quiescent local
runtime: old in-flight producers cannot retroactively register their scopes.
The rollout must stop/drain old writers before migration/restart and rehearse
that boundary without touching production. Existing pending runs must not all
be declared abandoned merely because they predate the table. On a private copy,
inventory legacy pending runs and known dangling references, preserve original
rows, and distinguish lack of a recoverable payload from a safely reconstructable
owner closure. Already erased prompt records cannot be fabricated by migration.

Required failing tests before application changes:

1. Pause a fake provider after run/pin commit; run local GC and import a retention
   deletion; finish and publish. Assert the complete prompt survives both.
2. Pause after successful validator completion, before report commit. Repeat
   GC/import and publish; assert there is no zero-row finish or dangling report.
3. Force L2 recursive left success, then hold the right sibling provider. GC
   must protect the left child's own trace. Exercise right failure and confirm
   persisted left units and prompt support a real resume.
4. Force graph staging to fail, keep the validated `GraphData` in memory, then
   GC/import before the generation transaction. Assert publication retains
   every entity/relation trace. Separately test interruption with successful
   staging and the existing no-repayment resume.
5. Raise `LLMError` after the query run has been recorded; interleave GC before
   `list_prompt_runs_for_query` and QTR write. Assert failed synthesis QTR still
   carries its prompt trace and its evidence, and the row can be inspected.
6. Pause MCP correction after classifier return and client close, before
   candidate creation. Assert its eventual candidate owns the trace. Test CLI
   response-only and derivation paths release reservations after disposition.
7. Use real separate processes to prove a paused owner is protected, process
   death allows stale-pin cleanup, unrelated producers continue, provider work
   does not hold the main DB writer lock, and malformed/missing token state
   never turns into permission to delete.
8. Inject publication/owner-release/tombstone failures and prove rollback or
   durable-reference handoff, not just a SQL keyword or rowcount expectation.
9. Run the saved fleet two-direction schedules with the local reservation and
   restored-owner rules; cover restricted snapshots, stale ownerless snapshots,
   old clients, ID remapping, and interrupted restoration.

## 2. Pros & Cons

The proposal preserves full prompt rows, existing durable batch staging, the
newest-N unreferenced cap, and offline publication. It explicitly handles the
producer states omitted by a validator-status or last-trace shortcut. Exact
process-lifetime evidence makes crash cleanup possible without a guessed grace
period, while ordinary writes remain available during provider latency.

It is a nontrivial stored-contract change across runner, callers, DB publication,
GC, local ownership storage, and fleet transport. Portability and migration are
part of correctness, not follow-up polish. A smaller local-only patch cannot
claim the same guarantee. Final synthesis should test whether a simpler proven
ownership witness exists, but should not replace these obligations with a
timer, an unbounded permanent pin, or a blanket exception for successful runs.
