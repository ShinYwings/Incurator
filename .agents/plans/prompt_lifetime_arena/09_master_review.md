# Final independent review of master09

Date: 2026-09-14. Read-only review of master09, B implementation domains,
05 consensus records and 08 native/AGY evidence. No application or user data
was changed. The chosen local lifetime and recoverable-retention architecture
is implementable. The following exact amendments close remaining contradictions;
they do not call for another exploratory Arena.

## 1. Required: refuse implicit schema15 adoption before setup

Master09's compatibility paragraph says adoption is separately authorized, but
does not specify how normal startup avoids adopting a schema14 database.
`db/schema.py:_check_schema_version` currently rejects only newer/malformed
stamps. Both `connect` and `init_db` then execute schema DDL and stamp any lower
version as current. Merely changing SCHEMA_VERSION to 15 therefore silently
changes an old database on ordinary service startup, violating the plan's
explicit adoption boundary; CREATE TABLE IF NOT EXISTS also cannot populate
the new provenance column on existing rows.

Add to master P1/P2 and B backend domain:

> Normal schema15 init/connect accepts an actually new/empty database or an
> already-adopted schema15 database. A populated older database, or a nonempty
> database lacking an unambiguous stamp, raises MigrationRequired before
> journal-mode changes, schema DDL, trigger refresh or version stamping. The
> explicit migration entry point uses a separate raw connection and validates
> the recognized source schema, coherent backup and session adoption input;
> it does not call ordinary connect as a prerequisite. Set version15 only after
> all transformed rows and provenance validate. Private rehearsal exercises
> interruption/rollback. Ordinary startup is never permission to migrate.

Tests must cover both open paths against schema14 and nonempty unstamped DBs,
asserting preserved logical content/schema/stamp and no new application objects.
Keep the shipped future-version refusal. Distinguish harmless creation of a
truly empty new DB from recovery of existing unstamped data.

## 2. Required: give receipts one explicit turn-disposition rule

05_session says only the winning complete revision owns capsules and losing
revisions must not union evidence into it. 05_handoff instead permits receipt
compaction only if attachments remain monotonic for the session lifetime or
the independent receipt remains authoritative. It delegates an accepted
revision lacking the original turn to session consensus, which has no exact
rule for that case. Implementers cannot decide whether a deleted/replaced turn
still owns receipts, or when its last payload is reclaimable.

Use this concrete refinement of the existing whole-session policy:

> Receipts remain independent durable evidence; do not compact them merely
> because a session capsule presently contains their bytes. A receipt grants
> ownership only when the accepted revision witness contains its exact saved
> session/assistant/turn identity. An accepted replacement that removes that
> identity deactivates its owner mirror; a stale/unreadable/missing file never
> constitutes that replacement. Preserve inactive receipt bytes for a later
> accepted revision that legitimately reintroduces that same identity. A
> terminal session tombstone suppresses late receipts permanently and permits
> physical receipt cleanup. Receipt storage is thus bounded by diagnostics
> produced within retained session lifetimes, including displaced turns, rather
> than by transient save revisions. Do not invent a new turn to attach a receipt.

This selects the already-reviewed independent-receipt option, preserves winning
revision semantics and avoids a new message-level tombstone contract. State the
storage implication explicitly in master and docs. If implementation instead
requires physical reclamation on turn removal, it needs an explicit terminal
turn-deletion witness; snapshot absence is insufficient for that stronger rule.

Backend receipt publication must acquire the shared session lock, reread and
validate accepted session/turn state, atomically publish the full receipt, then
release the local producer scope. Do not rely on validation performed before
the provider call: session prune may have committed meanwhile. Maintain session
lock-before-DB order. Delayed remote arrivals are evaluated against the latest
accepted witness/tombstones; known missing inputs retain recoverable bytes and
surface incomplete reconciliation.

Tests: receipt before/after prune; accepted turn removal; later accepted
reintroduction; losing old snapshot; receipt arriving before its session;
missing/corrupt canonical file; two sessions sharing a PTR; final session
tombstone followed by delayed receipt. Assert both DB ownership and last-copy
evidence bytes, not only link rendering.

## 3. Required: separate local liveness from exported durable ownership

The lifetime record correctly says prompt_run_owners is never synced, but its
single reference decoder and final-owner language combine pins and accepted
durable owners. This is a foreseeable implementation ambiguity: exporting a
pin as an owner witness, or trusting a peer's bare mirror index, would turn
local process liveness into unbounded remote retention.

Add to master/B import-export contract:

> Decode ownership into explicit categories. Local pins protect existing rows
> against local GC and imported retention marks only; they never enter exported
> owner closure or a peer's durable owner set. DB knowledge/query owners follow
> canonical accepted artifact revisions. Session mirror rows are derived local
> indexes, not independent synced authority. If session evidence travels in a
> DB bundle, export its complete accepted revision witness and evidence, apply
> the same winner/tombstone validator on import, and rebuild the mirror. Never
> accept a session_id-to-trace_id row alone. Independent sessions/receipts may
> arrive through their file channel and restore evidence under that validator.

Use the last sentence as the minimal implementation if the release does not
need session witnesses in DB JSON. Restricted DB exports then carry closure
for their selected DB artifact owners; they do not pretend to transport chats.
Reconcile accepted local saved evidence before destructive prompt GC and before
reporting trace absence, under the shared session-lock-before-DB ordering.

Tests must prove a live pin is absent from exports, a pin still protects an
import target from retention marks, and a stale bare session mirror cannot
restore a row or defeat a terminal session deletion.

## 4. Mechanical synchronization and gates

- Replace 05_session's Linux flock specification with the exact per-platform
  1.4.0 contract in 08_native_lock_feasibility. Keep producer-only locks separate.
- Replace 05_lifetime section6's prohibition on backend rewriting/pruning with
  the selected shared-local-lock commit protocol. Deferred prune is rejected.
- Current macOS arm64 real-process load/contention/death recovery is proven.
  Other supported platforms, minimum runtime, installed packaging/update and
  session integration remain release qualification gates. They need not block
  writing the implementation that those tests must exercise.
- AGY remains the actual architecture gate: the latest 08 evidence records
  two authenticated attempts returning tool unavailable and no sentinel process
  startup. This proves neither environment forwarding nor its impossibility.
  Do not label the route covered until an actual supported isolated launch
  reaches the sentinel and passes context-isolation checks.

## Re-review of incorporated master amendments

Read the amended master09 compatibility and final-owner clarification sections.
They incorporate items1–3: explicit pre-setup adoption refusal, inactive
receipt preservation until terminal session deletion, and local-only producer/
session-mirror state with complete evidence on the actual session channel.
The explicit master precedence also resolves the older prune/Linux statements.
No contradiction blocks independent schema/codec/local lifetime/fleet TDD.

Approve those architectural core phases now. The master status/P0 wording must
distinguish implementation dependencies from release qualification: native
platform testing and actual AGY coverage remain mandatory release gates, while
independent core work can proceed in parallel. Do not claim the AGY adapter is
specified or complete solely by reclassifying its test: its supported context
mechanism still needs an actual successful probe before that adapter's design
can be closed. If the root establishes an equivalent feasible per-launch route,
record it and its exact isolation evidence in08; no new broad Arena is needed.

Carry the receipt-publication revalidation/lock ordering into implementation
tests and domain detail. No additional source/provenance storage audit is
needed for this final review.
