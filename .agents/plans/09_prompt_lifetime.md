# v0.83.0 Master Implementation Plan

Date: 2026-09-14
Status: APPROVED — independent master review accepted schema/codec/local/fleet
implementation. Native packaging qualification and actual provider handoff are
mandatory integration/release gates; unresolved adapter behavior cannot ship.

## 1. Objective

Retain every recorded prompt diagnostic while a live operation can still publish
it or a retained knowledge record, query trace or saved chat owns it. Preserve
the existing newest-N unreferenced history cap and offline peer recovery. A
delayed accepted owner must restore its complete evidence across retention-only
eviction. User decision: "Protect saved chat links too; retain diagnostics while
those chats exist". Ship one coherent lifetime contract as schema 15/v0.83.0.

## 2. Explicit Non-Goals

No raw prompt/output archive, source-text reconstruction, loss of full chat
replay or thumbnails, arbitrary history windows, lossless span-list deduplication,
message-level CRDT, membership/acknowledgement-dependent final erasure, or 1.0.
Dashboard controls remain subsequent. Actual production DB/session adoption is
a separately authorized operation after a complete private rehearsal.

## 3. Strict Quality Conditions & Release Gates

- Protect pending and completed-unpublished producers, recursive successful
  siblings, optional graph-stage failure and failed-query trace publication.
- A paused live process remains protected; true process death permits pin
  recovery without heartbeat expiry. Verify separate processes, not thread mocks.
- Both import orders protect delayed owners and suppress stale ownerless rows.
  Ordinary deletion is never relabelled or cleared by retention recovery.
- Every accepted exported owner carries complete prompt closure even for
  restricted tables and --since. Import commits only final accepted owners.
- Preserve all recorded provenance, including unresolved historical source
  integers and span tokens. No fabricated original device or source resurrection.
- Saved reply diagnostics survive unavailable backend, crash between JSON and
  DB indexing, hidden CLI tool results and delayed session/DB transport.
- Immediate CLI session GC, offline plugin saving and minimum supported desktop
  runtime remain functional. Actual shipped lock payloads must interoperate
  with Python on supported platforms; no unlocked fallback.
- Actual AGY process must convey the exact launch context without shared
  per-turn registry mutation. A mock that merely accepts env is insufficient.
- Full required tests, documentation EN then KR, type checks, adversarial review,
  CI, version agreement, private migration rehearsal, merge and cleanup.

## 4. Locked Design Decisions (Arena Consensus)

### Local prompt ownership

Use the explicit PromptLifetime operation scope in
`prompt_lifetime_arena/05_lifetime_consensus.md`. Add local-only
prompt_run_owners(owner_id, trace_id, db_binding); reserve with run creation,
retain through caller publication and release after commit/unwinding. Per-owner
kernel locks prove process liveness without a main DB writer lease during model
calls. Protect all nine actual producer sites through their real outer owners.
Missing token or DB binding mismatch fails closed. Public artifact writers check
prompt closure in the same write transaction as publication.

### Recoverable fleet retention

Synced prompt_retention_marks(trace_id, evicted_at) is distinct from ordinary
deleted_records. Derive the final owner set after canonical merge/reconciliation;
defer prompt eviction/restoration until that set exists. Retain markers after
owner-backed restoration. Reject newly accepted owner bundles missing their
diagnostics atomically, while reporting pre-existing damage separately.
Completed compatible prompts outrank pending records; incompatible completed
records fail explicitly. Partial export includes owner evidence in one snapshot.

### Full evidence and historical provenance

Add versioned provenance_json capture observations alongside existing prompt
columns. Preserve original ordered arrays and source identity/unresolved status;
operational local IDs may remap separately. Legacy adoption observations name
their capture namespace, not an invented origin. Union distinct honest legacy
observations; reject conflicting bytes under one capture ID. Do not capture
anew on every sync hop. All APIs and session capsules use one complete codec.

### Saved chat publication

The selected existing-store design is `05_session_consensus.md`: retain
sessions.json with complete per-session capsules and actual message/turn links.
Use a shared local kernel lock for plugin/backend read-merge-write, preserving
immediate CLI prune and offline saves. Python/Node must use the same primitive
on each platform. Pin fs-native-extensions 1.4.0 (Node-API 8) and use Python
flock on macOS, OFD fcntl on Linux, and LockFileEx on Windows with identical
ranges; package a self-contained versioned runtime directory through build,
setup, wiki init and plugin update. See 08_native_lock_feasibility.md. Local
interprocess/runtime qualification is still being verified;
the agent must not label that gate complete from a source-level proposal.

The immutable snapshot alternative in `07_session_files_critique.md` remains an
evaluated alternative, not the selected implementation. Its conditional prune
admits future offline turns and therefore cannot immediately discard last-copy
diagnostic receipts. Do not silently adopt that extra retained storage while
claiming existing complete reclamation semantics.

Pre-save exact session/assistant/turn identity before a provider launch. Backend
publishes an immutable complete diagnostic receipt while the producer scope
still protects it. The receipt is an inspectable diagnostic attachment of that
saved turn, not an indefinite unacknowledged execution pin. Apply the explicit
route matrix in `05_handoff_consensus.md`; context is transport metadata or
per-launch configuration, never LLM-invented arguments or global current-session
state. Explicit session deletion suppresses late receipts. Preserve unresolved
legacy/manual links and report missing evidence; do not fabricate a record.

### Compatibility

Normal schema15 `init_db`/`connect` must reject a pre-existing lower-version DB
before journal/schema setup, including an unstamped nonempty DB. Empty/new DBs
may initialize. Adoption is an explicit command with backup/private rehearsal;
the version must be set only after schema, provenance and session ownership
validation succeeds. v0.82.7's future-only guard does not implement this upgrade
boundary. Never let CREATE IF NOT EXISTS plus a stamp pretend migration ran.

v0.82.7 / PR #208 shipped the pre-setup future-schema guard. Old binaries still
require upgrade/quiescence before schema15 adoption. New transport rejects old
versions; old peers may upgrade and re-export later. Preserve old snapshots for
explicit private conversion, never edit headers to bypass validation. Rollback
before new writes uses the coherent backup; after new writes it is recovery,
not blind replacement with the old database.

### Final-owner and receipt clarification

Only committed transportable artifact/session owners cause exported prompt
closure. Local live producer pins protect the local row but are never exported
or advertised as a peer's durable owner. Local-only graph staging has the same
local retention role until final published graph artifacts exist.

A receipt's effective DB owner exists only when its exact session and turn are
accepted and not terminally deleted. A newer whole-session winner lacking the
turn removes that effective owner. Retain its independent receipt bytes until
terminal session deletion, because another accepted offline revision can later
include that turn without its capsule. Such retained recovery bytes are not
automatically active owners. Do not compact away the last independent receipt
merely because one session snapshot incorporated it. Explicit deletion and
immediate age-GC deletion both create the existing terminal session tombstone,
after which its receipts can be removed; other surviving sessions/artifacts
continue to protect shared prompts. Report logical deletion and physical bytes
separately. This does not retain past full transcript revisions.

Receipt publication reacquires the session lock and revalidates the accepted
turn immediately before atomically publishing evidence. Validation before the
provider call is insufficient if pruning committed meanwhile. Session lock is
always acquired before DB transactions. DB exports carry DB artifact closure;
the session file/receipt channel carries chats and their complete evidence.

The rebuildable local mirror uses prompt_session_owners(session_id, turn_id,
trace_id, PRIMARY KEY(session_id, turn_id, trace_id)) and
prompt_session_witnesses(session_id PRIMARY KEY, revision_json, deleted).
Witnesses encode the shared deterministic session-order tuple, not a second
wall-clock merge algorithm. They are local-only: synced session capsules and
receipts carry complete evidence. Missing/unreadable session files preserve
known mirror owners and block destructive prompt GC until reconciled. New local
DBs reconstruct from accepted session state; ordinary absence never means delete.

This master supersedes older 05 statements that prohibit backend session prune,
use Linux flock with the selected Node addon, or export a live pin as closure.
Backend prune uses the same local session lock and remains immediate.

## 5. Scope Exclusions & Stop Conditions

No silent platform/provider support reduction. If actual probes disprove the
selected mechanism, resolve with independently reviewed equivalent engineering;
ask the user only for a real capability trade that remains unavoidable. The
approved independent core can proceed while adapter qualification runs. Stop before production
data migration/deletion/reindex. Build/test/review/release work itself is already
authorized. Never rerun the consumed D2 holdout; record provable non-impact or
use a new evaluation if retrieval changes.

## 6. Evidence Ledger

Baseline: master 1d614e06, v0.82.7; bookkeeping 81e94616. Live measured baseline
is recorded in A_measured_baseline.md: 5060 prompt rows, 176 pending, 1676 known
DB-referenced, no local prompt tombstones or scalar dangling prompt owners.
48 referenced rows contain missing spans and four contain missing source IDs.
The local cap is unset. Prior session scan found 18 sessions/65 deletion IDs
and no message-content tokens matching generated PTR format; peers unknown.
No live data changed. All current uncommitted work is planning/probe evidence.
Create the execution evidence ledger immediately before application code and
record coherent private-copy rollback/rehearsal details there.

## 7. Execution Phases (Follow TDD and CI at each phase)

- P0 — Native lock mechanics and current-platform process checks passed; master
  cross-review resolved migration, receipt and owner-category contradictions.
  Continue AGY runtime and cross-platform packaging qualification in parallel;
  do not claim adapter coverage or merge until their gates pass.
- P1 — Specify schema15 lifetime, session/API and transport contracts in the
  schema/system/plugin specs and paired guides. Define migration stop/recovery.
- P2 — Failing local lifetime/reaper tests, schema and portable evidence codec,
  private adoption. Pass focused pytest/Ruff before next phase.
- P3 — Scope actual producers and publishers, transactional GC and canonical
  import/export closure. Reproduce original two-peer failures as passing tests.
- P4 — Package shared lock, session commit/view reconciliation, saved-turn
  receipts and actual direct/CLI metadata propagation. Test offline and crash
  boundaries and shipped plugin artifacts on supported systems.
- P5 — Private migration/evidence integrity and full pipeline testbed rehearsal,
  full local checks and independent adversarial review. Version/changelog,
  green CI/merge, cleanup. Production migration remains a concrete final request.
