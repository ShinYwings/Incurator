# Producer Cross-Critique and Revision

Date: 2026-09-13 | Reviewer: Producer Lifecycle / Local Concurrency

Reviewed `02_fleet_design_extension.md` and `01_proposal_retention.md` against
the caller and DB code already audited in `01_proposal_producers.md`. This
document makes no application or production changes.

## 1. Agreement with the surviving design

Both proposals correctly distinguish a count cap on eligible unreferenced runs
from permanent fleet erasure. A separate retention marker avoids weakening an
ordinary tombstone, and retaining that marker after owner-backed restoration
prevents subsequent ownerless snapshots from undoing reclamation. No clock
ordering can replace accepted-owner resolution. I support one versioned
prompt-lifetime invariant combining producer protection and fleet restoration;
shipping the local half alone would leave the saved fleet counterexample live.

The retention audit also correctly rejects raw-response compaction as an
imaginary target: prompt rows contain hashes, not raw responses. Exact span-list
deduplication has a measured target but remains a separate optimization. It does
not solve ownership, deletion or count semantics.

The retention proposal's external-link qualification resolves an ambiguity in
my producer wording. For this release, say **registered durable DB owners and
active producer scopes**, not "every artifact" or "every textual link."
Plugin transcripts can preserve complete replay and trace-ID text without
registering permanent ownership of response-only diagnostics. Query answer
traces normally acquire QTR ownership; plugin correction responses do not
necessarily do so. Do not parse arbitrary transcript strings during GC or
truncate them to reconcile those different contracts.

## 2. Blocking completeness findings for synthesis

### A. Historical missing source identities cannot be fixed by closure expansion

The fleet extension correctly identifies this problem but leaves its exact
representation for the master plan. That representation must be decided before
implementation, not deferred until failing tests. `_translate_source_id_arrays`
at `db_sync.py:2215–2263` explicitly drops unknown IDs, because `sources.id` is
replica-local. `sources.sync_key` is the portable identity. Loading every live
source into a full snapshot still cannot resolve an old prompt's integer if
that source has already been deleted. A span ID can similarly be a historical
identifier whose row legitimately no longer exists.

The invariant must distinguish three cases:

1. An omitted but still-existing source/span dependency: export its identity
   closure independent of `tables` and `since`; remap to the recipient's real
   source, preserving logical provenance.
2. A known deliberately deleted source/span: preserve its historical identity
   and deletion status without resurrecting the source row.
3. A legacy unresolved integer with no surviving identity witness: preserve the
   known original value as explicitly unresolved origin-local provenance. Do
   not assign the recipient's coincidentally equal integer, guess a sync key,
   claim it was deliberately deleted, or reject every unrelated import forever.

Cases 2 and 3 require a stored historical identity representation or an explicit
diagnosed legacy exception; "include the full prompt row" is insufficient.
The existing integer-array API cannot simultaneously mean recipient-local live
IDs and faithfully carry an unresolved foreign integer without another field
or typed representation. This is a real schema/API detail within the planned
contract, not a reason to discard evidence. An additive typed provenance field
can preserve known values and mark unresolved ones while keeping resolvable
`source_ids` compatible; exact round-trip assertions then compare logical
identity plus preserved unresolved evidence, not foreign/local integer equality.
The final plan must specify whether that additive representation is selected
and how old trace APIs surface it. Merely adding a warning while dropping the
value would fall short of the proposed lossless restoration guarantee.

Do not enlarge the promise from retaining prompt **identifiers/metadata** to
retaining every source's deleted text. Existing prompt records never store
those texts. Historical source deletion semantics remain intact.

### B. Completion merge must respect producer authority

The extension correctly catches `created_at` LWW ignoring completion. A
`pending` row on one peer and its valid finished form on another need monotonic
completion merge, but "pick the latest finished_at" alone also accepts two
conflicting terminal records for one trace ID. Define immutable creation
identity and exactly which one-time completion fields may change. A completed
record outranks its compatible pending form; two equal compatible completed
forms are idempotent; incompatible terminal results are an explicit conflict.

Provider attribution legitimately changes at finish because a retry/failover
may select another provider; do not accidentally label `model_provider` and
`model_name` immutable creation fields. Likewise validator fields, output hash,
latency, retries and finished timestamp belong to completion. Input prompt ID,
version, family/role, rendered input hash, curate spec hash and source/query
provenance define the original call; source-ID normalization must compare
portable logical identity rather than raw local integer arrays.

An imported complete row must not let a stale local pending finish overwrite
incompatible terminal evidence. `finish_prompt_run` requires both a live owner
and a valid lifecycle transition, not only a positive rowcount. Keeping pending
rows unchanged on peers until a later full export is not a substitute: it would
break the inspection and resume guarantees the restoration release is fixing.

### C. Ordinary deletion cannot silently destroy active producer evidence

The fleet algorithm says apply ordinary prompt deletion under existing conflict
semantics and then surface owner conflict. Make the transaction consequence
explicit: if an accepted retained owner or active producer requires that run,
ordinary deletion must yield a recoverable conflict and roll back the affected
import, rather than committing the deletion and merely logging the conflict.
Otherwise the old normal-tombstone path still destroys a live producer and the
new finish guard only reports the damage later.

This does not redefine ordinary deletion as retention. It refuses an internally
inconsistent import until an authorized owner deletion or recovery resolves it.
Validation must include the final local reservations while holding the write
transaction. Reservations cannot be interpreted solely from a prescan outside
the transaction, because a producer can start after that prescan.

### D. Rollout is operationally gated, not solved by version headers

Agree with the extension: exact transport-version checks protect snapshot
exchange but not a shared writable DB opened by an already installed old
binary. The old `connect` executes DDL and stamps its own version. A future-
version refusal in new code is necessary hygiene, not retroactive enforcement.

A complete release can implement/rehearse the new contract without running
production migration. The live rollout needs user authorization under the
repository's explicit data-migration rule, with a concrete drained-writer
inventory and restorable backup. Stop old workers and any CLI/MCP consumers of
the same file, migrate, then restart matching runtime versions. Offline peers
may keep working in their old separate DB and defer exchange until they upgrade.
Do not claim invisible peers acknowledged or assume `pending` equals crashed.

Historic unresolved provenance must be inventoried in that rehearsal in
addition to dangling PTR references. Zero dangling PTR references does not
prove complete source identity closure, and an unset cap does not prove clean
historical source metadata. Read-only diagnostics should distinguish unresolved
legacy evidence from newly generated contract violations.

## 3. Revisions to my producer proposal

### Exact terminal behavior

Owner scopes are entered before the first run and closed after the last possible
publication by the outer operation. Normal return, validation failure, provider
exception, cancellation, `KeyboardInterrupt`, and `SystemExit` all leave via the
same `finally`/context-manager cleanup. This cleanup is deliberately outside
`run_prompt`'s narrower `except Exception`: that handler cannot see all process
terminal paths, and query provider errors still need the owner while the outer
QTR error record is being committed.

Hard termination uses kernel-lock recovery. A missing completion write can leave
a `pending` audit record after the scope dies; once exact owner reconciliation
proves no producer exists and no durable artifact references it, the row is
ordinary eligible unreferenced history. This is not a fabricated validation
failure and does not make every historical pending row immediately deletable.

If cleanup fails, the operation must report its primary error without masking
it, record a diagnostic for failed owner cleanup, and release the OS handle so
the next exact reaper can remove the stale reservation. If cleanup fails after
success, report the retained cleanup state rather than pretending it was
removed. Neither failure authorizes deleting a persisted artifact or trace.

An operation that intentionally hands a result to a background task must hand
off ownership before releasing the current token: under one write transaction,
add the new owner's pin while both owner tokens are live, then drop the old
pin. None of the audited synchronous callers requires this extra mechanism
today. Do not add an asynchronous framework for speculation, but fail loudly
if a standalone caller attempts publication after its borrowed scope closes.

### Portable token mechanics and lock order

`durable_io.locked_path` remains an unsuitable direct reuse because of its
Windows thread-only fallback and blocking-only API. The implementation must
use kernel interprocess locking on supported hosts: for example POSIX `flock`
with `LOCK_EX | LOCK_NB`, and Windows a nonblocking exclusive lock on one fixed
byte of the owner file through a supported byte-range locking primitive.
Windows token creation must initialize that byte before publishing a DB pin,
and every contender must target the same byte. This is an implementation
candidate requiring native separate-process tests, not a claim those tests
have already passed in the macOS workspace.

Always acquire/hold an owner token before the short DB transaction that creates
or reconciles its pins. GC probes tokens **nonblocking**, so it must not hold a
DB writer lock while waiting for a live producer token. A failed probe means
protected; operational probe failures mean uncertainty and protection with an
error, not absence. Reapers retain successful probes until their DB decision
commits, then release them. This avoids the deadlock cycle of producer token →
DB while GC DB → blocking token.

Scope tokens are never reused. Store them in a managed local directory attached
to the cache namespace, outside synced vault files and ordinary temp cleanup.
Validate file identity while operating, never recreate a missing token as
death evidence, and do not unlink a file with a live pin. Cache-copy/restore
metadata must explicitly identify that the owner records belong to a different
runtime namespace; a copied database cannot inherit running authority merely
by including the local table. Quiescent migration/recovery is the only route
for classifying such metadata as abandoned.

This is a bounded lifetime mechanism but still requires its own cache-preservation
classification, fork/exec handling, release-failure tests, and native Windows
verification. If those cannot be proven, keep the implementation plan open;
do not downgrade supported-platform safety to a thread lock or silently retain
every run forever as the shipped answer.

### Preview and publication clarifications

Read-only GC preview conservatively protects any durable reservation without
reaping it. This is the smaller exact contract: preview is an estimate based
on committed state; run reconciles provably dead owners and recomputes under
the transaction. Display protected active/unreconciled reservations and actual
run counts distinctly. No promise of exact freed filesystem bytes follows.

Every local writer introducing a real PTR reference verifies the required row
within its write transaction; synthetic empty trace IDs used for non-model
artifacts remain distinct from a missing genuine PTR. This validation applies
to all registered reference columns, not just currently called prompt families.
Existing legacy dangling owners should receive a diagnostic instead of making
unrelated reads fail, while GC remains fail-closed where it cannot establish
ownership. The import path may restore only from validated complete evidence
and surviving owners, never from a fabricated row or a stale rejected owner.

## 4. Final position

Proceed toward a combined owner-backed restoration plan, with the historical
source-identity representation resolved before coding. The evidence does not
force a capability-reducing product decision: complete typed historical
provenance is a plausible additive engineering solution. It does force honest
scope accounting; a plan that omits it, native lifetime semantics, terminal
producer paths, accepted-owner ordering, or rollout coordination is incomplete.

No source code, production files, retention settings, or live data were edited.

### Parent clarification: chat-only ownership remains a user decision

The user has now resolved this choice: **"Protect saved chat links too; retain
diagnostics while those chats exist"**. The DB-owner wording above describes
previous registration mechanics only. Chat-only links require real session-owner
registration, complete evidence closure and writer coordination. Keeping only
transcript text is insufficient. Existing QTR and other DB owners stay protected.
`04_session_producer_design.md` extends the same prompt-lifetime contract with
that now-required session publication boundary; it is not a subsequent optional
session feature.
