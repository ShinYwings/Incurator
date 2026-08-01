# Critique on Persistence Review-Fix Proposals
Date: 2026-08-01 | Agent Persona: Persistence Red Teamer

## 1. Vulnerabilities & Flaws

### A. The proposed config merge fixes additions by silently changing deletion semantics

Merging `requested` into the locked `existing` mapping is the right fix for an
unrelated peer addition, but it is not equivalent to the current full-snapshot
`save_config()` contract. If a stale snapshot still contains a key that a peer
deleted, `_merge_dict()` resurrects it. Conversely, if the caller deliberately
removed a non-machine-local key from its full snapshot, the key survives from
`existing`. The repository has no revision vector, base snapshot, deletion
tombstone, or `config unset` operation that could distinguish those cases.

This ambiguity must not be hidden behind the word "merge." The validator
proposal correctly makes omission non-deleting; that narrower policy must be
carried into the master plan and implementation. The patch must lock
the following narrower policy: full `save_config()` calls preserve unrelated
current keys and cannot express deletion of ordinary project keys; an actual
deletion must use a targeted `update_config_file()` callback. Machine-local
top-level keys are the explicit exception and must always be popped from the
locked current mapping. Tests must place the peer key under the same top-level
mapping as a local change, otherwise a shallow top-level implementation can
pass while still losing nested peer data.

### B. `DataAdapter.process()` has a compatibility and guarantee boundary

The installed Obsidian declaration calls `DataAdapter.process()` an atomic
read/modify/save primitive, which is the correct existing-file commit boundary.
However, that same declaration marks the adapter method `@since 1.7.2`, while
`plugin/manifest.json` declares `minAppVersion: "1.0.0"`. Making `process()` a
required runtime call can therefore crash versions the plugin claims to
support. Feature-detecting it and falling back to read/rename preserves startup
compatibility but also preserves the data-loss race on that fallback. The
master plan must resolve this honestly: prove the method exists on every
supported runtime, raise the declared minimum version, or document a stop
condition rather than claiming the invariant is universal.

The public contract says atomic read/modify/save; it does not explicitly promise
that an unrelated external Syncthing process participates in an Obsidian mutex.
The defensible guarantee is that a peer value visible when `process()` obtains
its callback input is merged. The implementation must parse, validate, merge,
sanitize, and serialize that callback argument itself. A preflight read followed
by `process(() => precomputedJson)` is still stale and is not a fix. Tests should
model the peer arrival by changing canonical bytes immediately before invoking
the callback, not merely by changing bytes before an ordinary `read()`.

### C. The missing-store path remains an irreducible TOCTOU race

The proposal's "re-check, then create" sequence does not close first-write
races. A peer can create the canonical file after the last `exists()`/`process()`
rejection and before the local temp rename. The rename then overwrites the peer
file. `DataAdapter` exposes neither exclusive create nor compare-and-swap, and
the proposal does not establish whether `process()` can create a missing hidden
file. An `exists()` re-check cannot be presented as atomic.

Before implementation, the actual supported adapter behavior for `process()`
on a missing `.curator/...json` path must be established. If it creates the
file atomically, use that single primitive. If it does not, first creation has
a residual race that the public adapter cannot fully solve; the plan should
state that limitation and ensure the adversarial test covers missing -> peer
creation, rather than proving only the easier existing-file case.

### D. Callback error handling can turn transient write failures into permanent read-only state

The lead proposal says an arbitrary `process()` I/O rejection marks the store
read-only. A disk-full error, adapter cancellation, or failed commit is not
evidence that canonical JSON is corrupt or unreadable. Permanently disabling
saves for the plugin run after such a transient error is a new behavior and can
discard subsequent in-memory edits. Only a typed validation failure from the
callback, or a follow-up typed read proving `corrupt`/`unreadable`, should trip
the read-only guard. Other process failures should reject the current save,
surface the error, and leave the canonical file intact without reclassifying
its contents. The validator proposal correctly draws this boundary; consensus
must select that behavior rather than the lead behavior.

The callback result should also not be returned through a `committed!` closure.
Use the string returned by `process()` as the committed source of truth and
parse it. That remains correct if an adapter invokes the callback more than
once internally. Session and profile load-time parsing and commit-time parsing
must share one strict parser so structurally invalid data cannot be accepted on
load but rejected on save, or normalized to an empty store and overwritten.

### E. Tombstones must be tested at the commit boundary, not just peer additions

A peer-only live session/profile is the weakest race test. The damaging case is
a tombstone arriving after preflight classification. The `process()` callback
must merge a peer `deletedSessionIds` tombstone without resurrecting the stale
local session, and a peer `deletedProfiles` timestamp without unioning the stale
profile back. For Zotero profiles, the test must also pin the current
`lastUsedAt > deletedAt` recreation rule; otherwise a refactor can preserve the
profile name but silently break delete/recreate semantics.

The existing per-adapter/per-path queues remain necessary even with
`process()`: the disk primitive does not define ordering for mutable in-memory
snapshots. Snapshot or clone the local operand when enqueueing so later UI
mutation cannot change an earlier queued operation by reference.

### F. The proposed mode algorithm briefly exposes an explicitly private temp file

The lead proposal always creates the temporary file with `0o666`, writes and
fsyncs, and only then applies an explicit mode with `fchmod`. That is unsafe for
`secret.key`: under a normal `0022` umask the sibling containing the encryption
key is `0644` for the duration of the write. Explicit `0o600` must be supplied
to `os.open()` at creation, not repaired later. Existing-target writes should
also start no more permissive than their selected final mode. The validator's
`requested_mode` formulation is acceptable only if consensus explicitly makes
that initial `os.open()` mode `0o600` for secret callers, rather than merely
calling `fchmod(0o600)` after bytes have been written.

For a new non-secret config, `os.open(O_CREAT | O_EXCL, 0o666)` correctly lets
the kernel apply umask without mutating the process-global umask. For an
existing target, `stat.S_IMODE()` must be restored with `fchmod` because the
current umask could otherwise remove bits from an existing `0664` mode. Apply
the selected mode before the final `fsync`; changing metadata after `fsync`
weakens the durability claim. Use one `stat()` attempt with
`FileNotFoundError` handling instead of `exists()` followed by `stat()`.

Mode-bit preservation is not full metadata preservation: atomic replacement
creates a new inode and may change ownership, ACLs, or extended attributes.
Tests and docs should claim POSIX mode preservation only unless those additional
properties are deliberately copied and verified. A controlled-umask test must
run in a subprocess; temporarily calling `os.umask()` in the concurrent pytest
process is itself a process-wide race.

### G. Existing plugin temp cleanup is incomplete on write failure

`atomicWriteVaultText()` starts its `try` block only after
`adapter.write(tempPath, data)` succeeds. An adapter that creates a partial temp
and then rejects leaks that sibling forever. Retaining this helper for missing
stores therefore requires a `try/finally` that covers both temp write and
rename, with cleanup errors suppressed only after preserving the primary
failure. The existing rename-failure test does not exercise this path.

The adapter declaration also documents `rename()` only as rename/move; it does
not promise atomic replacement of an existing destination on every platform.
It must not remain the existing-file concurrency primitive after `process()` is
introduced. If the backend claims crash durability, file `fsync` before rename
is also insufficient without a best-effort parent-directory `fsync`; otherwise
the contract should remain interruption-atomic rather than power-loss durable.

### H. Current authoritative docs already contradict the proposed behavior

`PLUGIN_SCHEMA.md` currently says valid session writes must use a sibling temp
plus rename, while the proposal moves existing-file writes to `process()`.
Earlier in the same spec, Zotero-profile text says "missing/unreadable" triggers
legacy migration even though the later shared typed-read rule and current code
fail closed on unreadable state. `PLUGIN_GUIDE.md` also says concurrent profile
edits need "no merge machinery," contradicting both current implementation and
the commit-time merge proposal. These are source-of-truth conflicts, not wording
nits. The English spec/guide and their Korean counterparts must be reconciled
before code, with temp cleanup promised only for whichever creation fallback
actually remains.

## 2. Suggested Alternatives

1. **Define config operations by intent.** Implement a pure
   `merge_project_config(existing, requested)` that deep-copies the locked
   current mapping, removes every machine-local top-level key, and deep-merges
   requested vault values. Document that full saves are additive for unrelated
   keys and route any future deletion through an explicit locked updater. Test
   nested peer additions, all three machine-local keys, and the deletion-policy
   boundary.

2. **Use one strict commit-time processor for existing JSON.** Add a required or
   explicitly version-gated `process()` adapter capability. Inside its
   synchronous callback, run the same strict parser used at load, merge the
   local snapshot with callback bytes, apply sanitization/tombstones, and return
   JSON. Parse the `process()` return value to update memory. Preserve the local
   queue, and classify only typed parse failures as blocked state.

3. **Make missing-file behavior a measured design decision.** Add an adapter
   contract test for missing-path `process()`. If supported, use it for first
   creation too. If unsupported, retain the sanitized temp creation helper but
   explicitly record the unavoidable missing -> peer-create race; do not claim
   that an `exists()` re-check closes it. Resolve the Obsidian 1.7.2 versus
   `minAppVersion` mismatch before shipping.

4. **Create backend temps with their security mode from byte zero.** Use a
   cryptographically random same-directory name plus `os.open` with
   `O_CREAT | O_EXCL | O_WRONLY`. Pass explicit `0o600` at creation for secret
   files; use `0o666` only for a genuinely new default config so umask applies;
   and restore an existing target's exact `stat.S_IMODE()` before the final
   flush/replace. Close descriptors and unlink the sibling on every failure.

5. **Strengthen adversarial proofs.** In addition to the briefing's tests, inject
   peer tombstones, structurally invalid callback input, a process failure after
   callback but before commit, missing -> peer creation, and a temp-write failure
   that leaves partial bytes. Assert canonical byte equality on every blocked or
   interrupted path, no temp leaks, queue recovery after rejection, session and
   profile tombstone behavior, existing `0664`, new subprocess-controlled umask
   mode, and both secret key/store `0600` modes.
