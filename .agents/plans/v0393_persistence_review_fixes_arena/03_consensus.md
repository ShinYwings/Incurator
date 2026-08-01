# Defense and Consensus: Commit-Boundary Persistence
Date: 2026-08-01 | Agent Persona: System Synthesizer

## 1. Vulnerabilities Resolved

The lead and validator agree on the root cause: serialization is ineffective
when a merge is computed from state read before the primitive that owns the
commit. The red-team critique is accepted with these revisions:

1. `save_config()` deep-merges requested vault values into the freshly locked
   project mapping after removing `llm`, `search`, and `external`. This
   deliberately preserves unrelated current keys; omission from a full stale
   snapshot is not a deletion request. Same-key requested values remain local
   wins. Targeted deletion remains the responsibility of an explicit
   `update_config_file()` callback.
2. Existing session and Zotero-profile files use Obsidian
   `DataAdapter.process()`. Strict parse, merge, tombstone handling,
   sanitization, and serialization all occur synchronously from the callback's
   current bytes. The returned committed text is parsed before in-memory state
   is installed. The local queue remains and snapshots its operand when
   enqueued.
3. Official API history shows `DataAdapter.process()` was added in Obsidian
   1.1.0, not 1.7.2. The plugin currently declares 1.0.0. A racy compatibility
   fallback is rejected; `minAppVersion` becomes 1.1.0 and `versions.json`
   retains v0.39.2 as the compatible 1.0.x fallback. This compatibility
   contract change promotes the unreleased v0.39.3 work to v0.40.0 under the
   repository's mandatory 0.x SemVer policy.
4. The adapter exposes no portable create-if-absent/CAS operation. Initial
   creation may retain the sibling-temp path, with cleanup covering partial
   write failures. The release does not claim simultaneous first-creation
   exclusion. Ordinary writes after canonical creation use `process()`.
5. Only typed commit-time validation failures classify a store as blocked.
   Generic process failures reject the current save and preserve bytes without
   permanently marking a valid store corrupt or unreadable.
6. Backend temp files are created with a mode no more permissive than the
   selected final mode. Existing targets preserve `stat.S_IMODE`; explicit
   secrets use `0600` at `os.open()`; new ordinary files use `0666` and the
   kernel's umask. Mode is set before the final fsync and replacement.

## 2. Revised Implementation Contract

- Documentation must distinguish existing-file atomic processing from the
  first-create temp fallback and reconcile the current profile/session guide
  contradictions in English first, then Korean.
- Backend tests inject a nested peer config arrival under the same mapping as a
  local edit, verify all machine-local blocks are removed, exercise existing
  `0664`, subprocess-controlled new-file umask, explicit secret `0600`, and
  interrupted replacement byte/mode preservation.
- Plugin tests inject live peer records and deletion tombstones immediately
  before the `process()` callback, inject structural corruption at that same
  boundary, reject after callback without commit, verify queue recovery, and
  cover partial temp-write cleanup for initial creation.
- There is no schema migration. Static spec titles, all build manifests,
  changelog, branch/PR naming, `minAppVersion`, and `versions.json` must agree
  on the v0.40.0 release contract.
