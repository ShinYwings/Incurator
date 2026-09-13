# Prompt Retention Baseline
Date: 2026-09-13 | Read-only inspection, no production mutation

## Current implementation and confirmed counterexamples

Baseline v0.82.6 on master. Finite prompt cap is opt-in and currently unset in
the measured vault. Producer/ref publication and fleet delayed-reference failure
are confirmed in disposable fixtures (see original fleet proposal and prior
retention Arena). No production GC was run to investigate either defect.

## Read-only live aggregate measurements

Database: `.cache/vaults/13ed51f8b06cb88e/state.sqlite`, opened only with SQLite
URI mode=ro. Aggregate counts/lengths inspected; prompt or source text not copied
into planning documents.

| Measurement | Result |
|---|---:|
| prompt rows | 5,060 |
| referenced prompt IDs at preceding snapshot | 1,676 |
| pending / ok / repaired / failed | 176 / 4,211 / 73 / 600 |
| all source_span_ids strings, bytes | 17,075,336 |
| distinct exact source_span_ids strings | 1,171 |
| distinct exact source_span_ids strings, bytes | 843,916 |
| largest repeated array | 224,400 bytes, repeated 63 times |
| prompt_runs deletion tombstones | 0 |
| dangling scalar references across all nine known holder columns | 0 |
| malformed query_traces.prompt_trace_ids JSON | 0 |

The schema stores no raw prompt or response body. Required fields include
identity, contract/version, hashes, validator result, model/timing and provenance.
Lossless exact-array dedup could reduce repeated span-list storage, but does not
implement the current unreferenced-row cap or repair lifetime/deletion races.
No observed local damage or urgent disk pressure justifies a destructive shortcut.
Other/offline peer state has not been inspected, so local zero tombstones is not
proof that no legacy deletion exists anywhere.

## Compatibility facts requiring final plan resolution

Sync transport rejects unequal schema versions. Existing local schema initialization
nevertheless stamps a mismatched DB version to the running version without a
future-version guard. A new ownership/retention schema cannot claim fleet safety
until old-runtime reopening and mixed-version rollout are rehearsed. Generic
prompt tombstone APIs exist beyond the cap even though the cap is the only
concrete local whole-row deletion callsite; do not relabel historical tombstones
as reversible cleanup by inference.
