# Lifetime implementation domain analysis

Date: 2026-09-14. This is the concrete implementation index for master09;
the independent proposals and their counterexamples remain the rationale.

## Backend lifetime, evidence and sync

Constraints: every run starts in its own DB transaction; runner completion is
not the last publisher. `db.connect` commits setup before yielding and callers
must explicitly begin their write transaction. Graph staging can fail without
failing extraction. Query error recovery reads failed runs before writing QTR.
Local-only producer state cannot be exported as a peer's live lease.

Specs: SCHEMA §11.7 records full diagnostic metadata/hashes, not bodies;
SYSTEM_BEHAVIOR §15.2 requires generated artifacts to name their originating PTR.
Current source/span remapping changes operational IDs, so preserve immutable
capture observations separately. D2 fingerprint records must be re-armed only
with demonstrated non-impact, never a rerun of the consumed holdout.

Decision: schema15 local owners + separate synced retention marks + capture
provenance. Code in dedicated `prompt_lifetime.py` and `prompt_evidence.py`,
with explicit owner passing to the runner and outer production boundaries.
The canonical DB module keeps creation/finish transactions; reserve on the
same connection as INSERT and make a missing completion row visible. Publishers
validate closure under their write connection. GC resolves owners before cap.

```text
with PromptLifetime(db) as owner:
    result = run_prompt(..., owner=owner)
    # Provider work occurs with no SQLite writer transaction.
    with db.connect(db) as conn:
        BEGIN IMMEDIATE
        require_prompt_rows(conn, published_ids)
        write_artifact(conn, result)
    # Context exit removes local pins; committed artifact owns evidence.
```

Rejected: runner-only scope, pending-status exemption, job-state ownership,
heartbeat timeout, main-DB lock during provider calls. Each misses a reproduced
publication/liveness boundary. Durable source closure is not a source archive.

Import/export: reuse canonical merge and generation reconciliation. Defer
retention decisions until accepted owners are known. Required incoming prompt
rows use the shared codec, not a lossy remapper-only projection. Existing
ordinary tombstones retain precedence. Read snapshots encompass owner selection
and evidence closure. Preserve prior snapshot on validation/write failure.

## Saved sessions, backend GC and plugin state

Constraints: plugin adapter queue and Python are currently independent writers;
atomic rename alone cannot serialize their read-modify-write. View message clones
can outlive active-session selection changes. Coalesced saves can finish after
newer local edits. Offline plugin saving and immediate CLI pruning are existing
capabilities. Old whole-session LWW/deletion-ID union must remain explicit.

Specs: PLUGIN_SCHEMA §2.2 and PLUGIN_GUIDE session history require session-level
merge and terminal deletion propagation. Full transcript and thumbnails remain
the user-selected product behavior. Session diagnostic metadata never enters
provider replay as instruction or model text.

Decision: existing session file plus full per-session evidence and immutable
saved-turn diagnostic receipts. Use same local kernel lock in Python and Node,
with platform semantics/packaging fixed in08_native_lock_feasibility. Read fresh
canonical/conflict state after acquiring; merge; apply save/delete/prune; atomically
replace. Explicit view session ID and mutation epoch protect UI identity and
pending edits. Native install validation is part of actual build/update flow.

```text
await sessionLock(vaultIdentity):
    current = readAndValidateCanonicalAndConflicts()
    merged = mergeAcceptedRevisions(current, capturedEdit)
    # Validate pruning eligibility here, never from the dashboard preview.
    committed = applyRequestedMutation(merged)
    atomicReplace(committed)
rebaseNewerLocalEdits(committed, capturedEpoch, explicitViewSessionId)
```

Cross-language order: session lock before any DB transaction. DB owner mirror
may lag file commit because full capsule/receipt already preserves its payload.
Syncthing is not a lock participant; conflict recovery and final-owner acceptance
remain necessary. Missing/corrupt state does not release known ownership.

Rejected: backend-only save broker removes offline saving; queued-only prune
removes immediate CLI behavior; immutable full transcripts add history/compaction
semantics and conditional-prune last-copy issues. Native packaging is additional
work but preserves the selected current capability with one file authority.

## Provider handoff

Constraints: reachable direct API, Claude CLI and Codex/AGY CLI routes expose
different tool-output detail. A trace ID after producer release is too late to
fetch evidence safely. Shared per-turn MCP config would cross-wire concurrent
sessions/vaults. A pre-saved assistant placeholder is already in the send flow.

Decision: trusted session/turn/launch context, complete receipt published before
returning trace ID, direct transport _meta where possible and per-launch MCP
context elsewhere. AGY project-plugin probe verifies supported context passage.
Receipt is an inspectable diagnostic attachment of the saved turn and does not
wait on an arbitrary ACK timeout. Validate explicit vault/turn binding, accept
only surviving owners, terminal deletion rejects late receipts.

Failure rule: preserve unavailable historical/manual link text with explicit
unresolved state. New scoped generated diagnostics missing the expected receipt
are a visible integration failure, not claimed success. No API secretly pins
every unrelated background prompt to the foreground chat.
