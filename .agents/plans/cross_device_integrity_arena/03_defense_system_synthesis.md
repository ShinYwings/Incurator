# Defense: Locked Cross-Device Contract
Date: 2026-07-05 | Agent Persona: system_synthesizer / source_pair_analyst

## 1. Resolved Design

The critique is accepted.

- `sync_key` is a dedicated portable key. Absolute-path-derived logical IDs are
  never used as transport keys.
- Sources are merged through explicit local-ID-preserving SQL. A frozen
  `SOURCE_ID_TABLES` contract remaps every synchronized `source_id`.
- Source tombstones address `sync_key`; all other single-column tombstones use
  stable record IDs.
- Mutable source and generation rows receive monotonic revisions. Equal-revision
  conflicts converge through a deterministic serialized-row tie-break.
- Storage relocation is automatic only when the cache target is absent. Dual
  DB presence is a hard error.
- Collections remain shared `.curator` projections because they are portable
  and required by Obsidian links. Device-specific singleton outputs move to
  cache; shared deterministic writes are atomic and content-idempotent.
- Plugin temporary paths have no vault fallback.
- Session reset and profile deletion contracts preserve shared durable state.

## 2. Verification

The release must prove:

- two empty replicas can each create source id 1 and converge to two sources;
- source delete converges without resurrection;
- stale staged generation cannot replace authoritative;
- malformed/non-allowlisted JSONL cannot execute dynamic SQL;
- same-mtime replacement imports by `export_id`;
- no machine-local artifact is created under a test vault;
- plugin caches require repo `.cache`;
- reset preserves sessions and profile tombstones suppress resurrection.

