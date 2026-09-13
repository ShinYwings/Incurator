# Retention Proposal: Preserve the Actual Trace Contract, Separate Space From Finality
Date: 2026-09-13 | Persona: Retention Capability / Storage Reviewer

## 1. Core Logic & Implementation

### What a prompt run actually contains

`backend/src/curator/db/schema.py:642–664` defines a small metadata record with
two potentially variable collections. There is **no raw rendered prompt, raw
model response, parsed response, chat message or thumbnail payload** in this
table. The exact persisted columns are `trace_id`, `prompt_id`,
`prompt_version`, `family`, `role`, `model_provider`, `model_name`, `input_hash`,
`output_hash`, `validator_status`, `validator_errors`, `retry_count`,
`source_ids`, `source_span_ids`, `curate_spec_hash`, `query_trace_id`,
`latency_ms`, `created_at`, and `finished_at`.

`prompting/trace.py:105` hashes the output before persisting it. A proposal to
drop or archive raw prompt/output blobs from `prompt_runs` therefore has no
implementation target and no defensible storage estimate. Prompt metadata
already cannot replay the exact historical response. Chat replay is a separate
contract and must not be silently substituted for prompt inspection.

### Field consumers and exact loss if discarded

| Consumer | Required fields and actual consequence |
|---|---|
| L2 unpublished-unit adoption and batch resume, `pipeline/knowledge_units.py:149–185,360–412` | SQL joins require a surviving trace row. Contract ID/version, curate spec hash, validation status and rendered input hash determine whether existing units may be reused. A missing row or reduced record with absent values causes existing work to be rejected/repeated. |
| L3 prose resume, `pipeline/community_reports.py:252–286` | A report with content compares the run's `input_hash` and `curate_spec_hash`. A missing run makes valid existing prose incur another model call. |
| Graph staging resume, `gc.py:507–513` and `graph_batch_results.trace_id` | A staged result retains its trace identity before final entities/relations are published. The staged response is elsewhere; pruning the run would produce dangling provenance during adoption. |
| Query error recovery, `retrieval/orchestrator.py:83–94` | Lists runs by `query_trace_id` to attach their `trace_id` values to a failed query. A run can be useful before that forward JSON reference has been committed. |
| `wiki prompt trace`, `commands/prompts.py:44–55`, and `curator_get_prompt_trace`, `mcp/server.py:3301–3307` | Both expose the complete decoded row. Source ID/span lists, validator errors, retry count and timing are inspectable even when a narrower UI omits them. Removing them is an observable reduction. |
| Plugin prompt trace, `commands/plugin.py:849–866` | Presents prompt identity/version/family, model, validation status and errors. This narrower projection is not the entire public trace contract. |
| Answer/synthesis audit, `inspection/synthesis_audit.py:102–121,313–326` | Collects referenced runs and reports missing traces. Its projection includes hashes, role, model, timing and query ID; missing runs degrade diagnosis and provenance. |
| Sync and source identity repair, `db_sync.py:2001,2210`; `source_identity.py:212–228` | Span arrays participate in ID remapping; source arrays participate in numeric source remapping. These are active integrity fields, not inert log strings. Any new representation must preserve those remaps and decoded API values. |

A report's own cited spans do not reconstruct the exact prompt input span list:
the model can select only some offered evidence. Neither a later current source
nor a current prompt template reconstructs its historical metadata. A proposed
“minimal record” that retains only resume hashes may preserve billing behavior
but sacrifices currently available audit data. That requires a product decision.

### External trace links are a separate ownership boundary

`commands/plugin.py:1038–1075` returns a correction classification `traceId`
without recording an insight candidate. The MCP correction route may record a
candidate, but that cannot be assumed for the plugin command. Returning a trace
ID is not proof of a durable database owner, nor proof the recipient discarded
it. General CLI/MCP consumers can save the ID outside the database.

The plugin can also persist visible trace IDs in transcript text:
`agent/llm/messageUtils.ts:241–263` retains `prompt_trace_ids` and query trace
data in the displayed query-tool result; `agent/llm/LLMClient.ts:1966–1986`
streams that display into chat content. `utils/sessionData.ts:110–136` preserves
message `content` when sanitizing the persisted transcript. Its durable store
is distinct from the DB (`utils/sessionStore.ts`). The GC reference registry
does not read session files, arbitrary Markdown or external consumers.

Therefore the implementable existing exemption is **registered DB owners**,
not an omniscient guarantee that every textual trace link anywhere survives.
Do not silently broaden or narrow that boundary by saying “any artifact.” A
complete lifetime contract should define when a caller publishes to a durable
owner versus returns an unowned diagnostic eligible for the delegated cap.
Supporting independently retained chat links as protective owners would need
explicit registration/closure and writer coordination across that file store;
regex-scanning message strings during GC would not solve the publication race
or offline ownership. This is a distinct design boundary, not permission to
truncate the transcript. The trace ID text and full chat replay can survive
even when an intentionally unowned diagnostic record expires under the cap.

### Read-only measurements of the actual workload

Measured with Python `sqlite3` URI `mode=ro` plus `PRAGMA query_only=ON` against
the supplied production database. No application `db.connect`, mutations,
provider calls, schema changes or production GC were used. Only aggregate
counts and byte totals were emitted. Values count UTF-8 bytes of column
contents, not SQLite page/index overhead, filesystem savings or export sizes.

| Measurement | Result |
|---|---:|
| Prompt rows | 5,060 |
| All `source_span_ids` values | 17,075,336 bytes |
| Other column values combined | 1,016,157 bytes |
| Distinct exact span-list strings | 1,171 |
| Distinct exact span-list strings, stored once | 843,916 bytes |
| Each current row compressed independently with zlib level 9 | 4,346,590 bytes |
| Distinct exact span-list strings compressed independently | 273,487 bytes |
| Whole concatenated span-list stream compressed | 3,901,416 bytes |

Exact list deduplication removes approximately 95.1% of this column's repeated
value bytes before adding per-row references and storage overhead. It preserves
list order, duplicate elements and every ID; treating lists as unordered sets
would not establish exact preservation. Whole-stream compression is only a
measurement bound, not a proposed random-access database layout.

Using the existing committed-reference scan on the same read-only connection:

| Current local classification | Rows | Span-list value bytes | Distinct list bytes | Pending rows |
|---|---:|---:|---:|---:|
| Referenced | 1,676 | 1,492,708 | 538,239 | 0 |
| Unreferenced | 3,384 | 15,582,628 | 543,254 | 176 |

These labels describe the present local scan only. They do not establish that
the 3,384 runs lack active producers or offline peer references. The 176 pending
rows cannot be classified as crashed producers merely from their age/status.
No particular nonzero cap value has been inferred or applied.

### Distinguish three separate capabilities

1. **Exact trace access:** preserve each decoded field while changing physical
   representation. Lossless deduplication can preserve this capability.
2. **Finite unreferenced call history:** a count cap intentionally removes older
   ownerless rows; it already exempts referenced rows without a global size
   bound. Keeping every row forever, even compactly, does not implement it.
3. **Permanent fleet deletion:** an old retention tombstone currently prevents
   a delayed peer from restoring required evidence. This is a conflict policy,
   not a necessary consequence of enforcing a local unreferenced count cap.

The documented cap says removal applies to all synced devices, so changing
retention into owner-aware revocable removal requires explicit documentation
and compatibility validation. It does not automatically reduce user capability:
the same documentation promises that referenced records survive. Protecting an
offline owner fulfills that preservation promise while continuing to cap truly
unreferenced history. Fleet-wide immediate permanent finality must not be
invented as a separate user demand when evaluating that engineering option.

### Feasible alternatives and their boundaries

**A. Producer lifetime plus owner-backed restoration.** Preserve complete prompt
rows while a producer may still publish. Treat retention deletion as revocable
when a valid retained artifact arrives with the complete required trace. Keep
ordinary stale unreferenced rows subject to deletion. This preserves the useful
count cap and existing audit/resume capability; the fleet proposal's closure,
arrival-order and old-client obligations are mandatory. An ID or two hashes is
not a complete restoration record. Missing closure must be a visible recoverable
condition rather than fabricated trace data. This is the preferred direction
to prove before escalating a product fork.

**B. Cooperative global reclamation.** Membership plus durable acknowledgements
can establish that no disconnected participant owns a candidate before permanent
deletion. This preserves trace history but may defer reclamation indefinitely
for an offline peer. Membership retirement and stale snapshot rejoin are part
of the contract, not housekeeping. This adds more fleet machinery than A and
may materially reduce the useful reclamation capability.

**C. Lossless span-list deduplication as a separate storage release.** Normalize
exact list values into a content-addressed/shared representation and retain a
reference from every prompt row. Decode to the identical public list. Equality
must be verified on bytes when interning; a hash is an index, not evidence that
two different payloads may be conflated. Garbage-collect shared payloads only
when no live trace references them. Update raw SQL remappers, migration,
restricted/full sync closure, snapshot import/export and integrity checks.
Compression can additionally reduce distinct-list bytes, but increases codec
and migration obligations. A minimal dedup-only layout already captures most
measured savings, so compression is not justified merely by the table's size.

This alternative preserves every present trace value and offers meaningful
space reduction. It **does not repair any deletion race**, does not enforce a
row cap and must not replace A/B under the name of a fix. A shared payload can
also disappear under a delayed-reference schedule unless its trace reference
closure has been made safe first. The stored-contract change warrants its own
release and isolated migration rehearsal. Production migration still needs
authorization. SQL deletion or smaller logical values alone do not promise an
immediate reduction in the physical SQLite file; free pages and compaction must
be measured separately before promising disk savings.

**D. Compact trace skeleton or preserve-all policy.** Keeping only resume fields
would remove source/span and diagnostic inspection. Keeping all successful rows
would remove useful call-history retention. Neither is an engineering equivalent
to the requested cap and neither can be silently selected. Complete trace
archives could preserve inspection if reliably available offline, but introduce
archive retrieval, transport closure, retention and cache-loss guarantees; merely
moving the same bytes to an unbounded archive is not permanent reclamation.

### Required verification before implementation can be considered complete

- Exercise every audited API against an original and reconstructed run; compare
  all decoded fields, including ordering, duplicate span IDs, error strings and
  null timestamps. Verify source/span remapping after cross-device import.
- Assert that L2 adoption, L3 skip and graph resume still reuse actual persisted
  work, rather than only asserting that a trace ID exists.
- Execute provider-in-flight and completed-unpublished schedules against local
  GC and imported retention deletion. Classify crash recovery from durable owner
  state, not an arbitrary time grace period.
- Exercise the fleet proposal's owner-first, deletion-first, restricted snapshot,
  stale unreferenced snapshot and old-client schedules with complete trace
  equality. Successful import counts alone cannot establish preservation.
- If deduplication is later selected, measure complete resulting database and
  export sizes on a private copy with migration round-trip checks. Value-byte
  estimates above are not a substitute for that evidence.

## 2. Pros & Cons

The audit identifies a real, large, lossless storage opportunity without
inventing payloads or discarding trace fields. It independently supports
owner-backed restoration as the first candidate for preserving both useful
retention and offline provenance. It does not yet claim that the producer and
transport protocols have been proven complete; that belongs to the combined
Arena synthesis and adversarial schedule tests.

There is a genuine product fork only if complete useful reclamation cannot
coexist with required offline trace availability under the selected protocol:
defer permanent reclamation while peers are absent, or deliberately expire some
offline evidence. The present measurements and field audit do **not** establish
that this fork is unavoidable. First exhaust A, while treating C as a separate
optimization and rejecting D as an unauthorized capability reduction.
