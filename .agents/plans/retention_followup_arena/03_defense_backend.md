# Defense and Revision of the Backend Retention Proposal
Date: 2026-09-11 | Agent Persona: Backend Architect / Schema Guardian

## 1. Vulnerabilities & Flaws

I accept the parent's adversarial finding and explicitly **retract `BEGIN IMMEDIATE` as a complete fix for prompt-run lifetime safety**. The original proposal's transaction defect and disposable reproduction remain valid evidence, but its recommended prompt-run patch scope is superseded. Section 3 of `01_proposal_backend.md` preserves this correction and the complete reproduction command; the original detail remains available as debate history rather than being compressed away.

`db.connect` commits schema setup before yielding (`db/schema.py:937–973`), so the existing GC reference SELECTs occur without a transaction. The reproduction proved that a report can commit a new reference between cap selection and deletion, yielding one dangling report and one deletion tombstone. However, making that SELECT/delete interval serializable only orders existing database operations; it cannot protect a trace ID held by an ordinary producer outside a transaction.

The real production sequence is:

1. `prompting/runner.py:205–214` starts a prompt run; `db/_entities.py:2689–2707` commits it and returns the ID with `validator_status='pending'`.
2. `runner.py:226–249` calls the provider and validates/repairs the result. This must not hold an SQLite write transaction for the duration of a network call.
3. `runner.py:269–278` finishes the run in a second committed database operation (`db/_entities.py:2722–2737`). It may now be `ok` or `repaired`, while no artifact refers to it yet.
4. `runner.py:279–285` returns the trace ID and parsed result. `pipeline/community_reports.py:284–311` subsequently publishes the report with that ID. `pipeline/graph_index.py:253–261, 300–312` likewise writes the resume cache in a later transaction.
5. If the cap runs before step 4 commits, it can delete a run that is currently unreferenced but still owned by the producer. `BEGIN IMMEDIATE` merely causes a contending artifact writer to wait, then publish a dangling reference after GC commits. This is an ordinary delayed-publication path, not an exotic hostile writer.

A `pending` exclusion protects step 2 but misses step 3-to-4. A recent-age grace period misses paused producers. Checking job state misses prompt callers outside jobs and has the same check-versus-start coordination problem. The existing finish UPDATE also does not verify rowcount, so a run deleted during the provider call can disappear without a failure at completion. None of these facts justify silently disabling successful-run reclamation or changing its cap semantics.

## 2. Suggested Alternatives and Final Consensus

**Agree with a cache-only v0.82.6 patch.** The independent safety proposal has two self-contained counterexamples: GC preview currently heals/mutates a candidate database via `get_stats -> db.connect`, and zero `sources` does not prove absence of retained history/tombstones. These are existing preservation-contract failures. Repairing them needs no new history window, product-capability reduction, schema change, production deletion, or new UI.

The patch should use non-healing WAL-aware read-only inspection, recognize its supported layout, check every durable application-table class, retain unknown files/state, preserve the genuinely empty-temp-cache case, and revalidate the planned namespace identity, root, marker and contents before removal. My `02_critique_backend_on_safety.md` and the plugin critique agree on these constraints. I accept a current known schema floor plus explicit metadata/FTS ownership checks; a whole schema-management subsystem or byte-identical trigger SQL fingerprint is unnecessary if the chosen smaller check never treats unknown state as disposable. Empty unknown tables may be conservatively retained without becoming a new expiry policy.

Revalidation must be described accurately: it rejects observed changes during the preview/confirmation gap; it is **not** atomic filesystem writer exclusion. Ordinary background jobs, not just “uncooperative” processes, can write after the final probe. The read-only claim is no application rows/schema/version writes or repair. Byte preservation is required for the closed partial-schema regression; do not promise fixed WAL/SHM bytes while another connection is active, and do not use `immutable=1` to ignore WAL.

Keep prompt-run lifecycle safety as a separately queued, plan-first defect. Its acceptance criterion must cover real ownership from creation through final artifact publication, interruption/recovery, all prompt callers, and cross-device unknown references. A durable reservation or equivalent proven ownership mechanism is a design candidate, not a locked implementation decision. The design must explain when the producer releases ownership and what happens after a crash without inferring completion merely from validator status. Any stored-contract change follows the dedicated release/migration rehearsal rules. A capability-reducing emergency stop goes to the user with concrete costs; it is not an engineering tiebreaker.

Malformed `query_traces.prompt_trace_ids` currently being ignored remains a follow-up lead, not a patch requirement from this agent: it has not received the independent reproduction and full cross-critique needed to add scope. Keep the cache patch focused. Job-event/query/compiler-history windows, Dashboard GC, session cross-writer coordination, and tombstone acknowledgement policy remain visibly open. Do not claim B1/B2 complete after the cache correction.

No application code, configuration, live database, or production files were edited by this agent. Deliverables are the backend proposal, backend critique of safety, and this defense; the race reproduction used disposable temporary state only.
