# Backend / Schema Proposal: Repair the Existing Retention Guard Before Adding Policy
Date: 2026-09-11 | Agent Persona: Backend Architect / Schema Guardian

## 1. Core Logic & Implementation

### Current state and what is already shipped

The baseline is v0.82.5. This proposal inspected code and historical records; it did not run GC against a real vault or change application code/configuration. A disposable temporary database was used for the race reproduction below and automatically removed afterward.

- `gc.sessions_retention_days`, default zero, and `wiki gc plan/run` shipped in v0.70.0. `gc.py:319–399` computes a session cutoff, keeps sessions without a usable timestamp, and writes deletion IDs for removed sessions. The session window belongs to the user.
- `gc.prompt_runs_keep`, default zero, shipped in v0.71.0, not an outstanding feature. `CHANGELOG.md:950–980`, `docs/guides/USER_GUIDE.md:1077–1080`, and `gc.py:486–536` agree on newest N **unreferenced** runs with a tombstone for each deletion. The roadmap's old open-table and final escalation paragraphs (`ROADMAP.md:304–308, 375–378`) have not been reconciled with this shipment and the delegation of prompt policy (`ROADMAP.md:325–329`). Do not implement a second cap or ask the user again whether a cap is allowed.
- The reference set is already semantic rather than merely named `prompt_run_id`: `gc.py:415–436` includes `graph_batch_results.trace_id` and `claim_supports.validator_trace_id`, and `gc.py:467–482` scans the JSON array `query_traces.prompt_trace_ids`. `backend/tests/test_prompt_run_cap.py` covers the ordinary cap, report references, JSON query references, tombstones, disabled defaults, and operational SQL failures.
- `db_sync.py:47–72` transports prompt runs, query traces, compiler generations, and tombstones. `db_sync.py:76–82` excludes `ingest_jobs` and `job_events`. The claim in the `db/job_events.py:10–11` module comment that job events are transported is stale; the actual registry is authoritative.
- `query_traces` are not merely diagnostic logs. `context_service.py:1332–1349` resolves a live ContextService root by trace ID or pack ID; `db/_entities.py:3345–3385` searches its embedded `retrieval_trace_json.context_service.pack_id`. Deletion can break continuing context operations even when the query is old. `prompt_runs.query_trace_id` (`db/schema.py:658`) is also a reverse relationship to audit.
- A discarded compiler generation is not proven garbage. Publishing changes the prior authoritative row to discarded (`db/_entities.py:765–775`), and historical `knowledge_units.generation_id` and `graph_relations.generation_id` remain semantic links (`db/schema.py:425, 501`). `audit_json` stores published provenance (`pipeline/compile.py:974–983`). A status-only purge would erase lineage rather than merely temporary failures.
- Job history is deliberately exposed by `wiki jobs events` (`docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:1412–1429`; `db/job_events.py:128–144`). Locality means no sync resurrection trap, but does not make deleting diagnostic history a product-neutral operation.

### Confirmed defect: the reference check and deletion are not one transaction

`apply_prompt_run_cap` says it computes the doomed set "inside this transaction" (`gc.py:521–530`). That is false under the actual connection helper: `db/schema.py:937–973` commits setup before yielding the connection, and SQLite's default deferred transaction begins on the first DML, not on SELECT. All reference reads can therefore finish before another writer commits a reference, then GC deletes the now-referenced prompt run and writes a tombstone.

A deterministic disposable-DB reproduction inserted two runs, scanned the cap with keep=1, inserted a `community_reports.prompt_run_id='PTR-old'` reference through a second connection immediately after `_prompt_runs_over_cap` returned, then let `apply_prompt_run_cap` continue. Observed output:

```text
scan_transaction_open: False
deleted: 1
dangling_report_references: 1
tombstones: 1
```

The test altered the Python function binding in memory only to control the interleaving, restored it in `finally`, and operated entirely under `TemporaryDirectory`. It did not edit implementation or touch production state. The defect is not hypothetical and directly violates the shipped cap's safety claim. Its consequence is fleet-wide because the emitted tombstone propagates.

### Recommended smallest next release

Recommend a **patch** from v0.82.5 to v0.82.6 that fixes the existing prompt-run cap's transaction boundary. It adds no setting, table, deletion window, or public API. If the independent cache-safety review proves another deletion guard defect, it may join this narrowly defined existing-GC-correctness patch after cross-critique; do not bundle the missing GC dashboard or a new per-table policy.

Implementation decision: acquire `BEGIN IMMEDIATE` on the existing `db.connect` connection **before** collecting references and run IDs, then perform all deletions and tombstones under that same transaction. This serializes against SQLite writers before any eligibility observation; readers remain possible under WAL. The context manager already commits on success and closes/rolls back on exceptions. Do not catch a lock failure and proceed; an unreadable or contested retention set must not become permission to delete.

The code comment must explain why a context-managed connection alone is insufficient. Avoid `BEGIN DEFERRED`: reading a snapshot before acquiring write authority can cause lock-upgrade failures and does not offer the straightforward exclusion needed here. Do not add a second best-effort reference scan after the doomed list; without a transaction it merely moves the race.

This fix guarantees atomic eligibility under the local DB writer serialization order. It does **not** claim to coordinate future references from another device or artifacts published after the GC transaction has already committed. Those are wider lifecycle/sync questions; do not market the patch as proof of global referential integrity.

### Tests, documentation, and release gates

1. First add a failing deterministic concurrency regression in `backend/tests/test_prompt_run_cap.py`: a second SQLite connection attempts a reference insertion after eligibility collection but before deletion. Assert the GC transaction is already active before scanning, the competing writer cannot commit until it ends, and a reference committed before GC obtains its writer transaction is protected. Avoid a sleep-only race test; use controlled hooks/events or a bounded competing connection timeout.
2. Cover rollback: force tombstone insertion to fail after a deletion; assert both run rows and the tombstone set remain unchanged after rollback. The existing code relies on close-induced rollback, so verify the entire atomic operation, not just a SQL token.
3. Preserve existing newest-N ordering, default-off, every scalar/JSON reference, missing-old-table tolerance, and operational SQL failure tests. No new retention semantics are needed.
4. Document transaction safety in the English user guide first, then the Korean counterpart, and the closest retention/system behavior specification. The user-visible effect is that concurrent artifact publication cannot slip between reference inspection and deletion.
5. Use the repo-required focused/backend/plugin/typecheck gates, actual code-review skill, patch version alignment in all manifests, changelog, and testbed-only CLI smoke. No real-vault `gc run`, migration, or reindex.

### Remaining product decisions: keep them separate and explicit

The user has authorized the agent to choose prompt-run policy, but has not authorized silent new expiry of query context roots, compile lineage, or job history. The smallest concrete next policy choice is local job-event retention: keep all operational history (current behavior), or offer opt-in deletion for terminal jobs older than a chosen window while retaining all events for queued/running/interrupted jobs. Even the latter needs exact state semantics: `interrupted` remains resumable and must not be treated as a completed log simply because it is old.

Query traces require a model of which context packs remain live and what historical continue/feedback/audit operations may lose. Discarded generations require an orphan/lineage audit, including historical units, relations, JSON audit references, source deletion, and cross-device import behavior. A tombstone expiration policy still lacks a proven offline-peer acknowledgement floor and cannot be selected from a time menu.

No measurement in this proposal establishes disk pressure severe enough to choose those losses. Historic numbers in the roadmap are dated, not current baselines. Parent-reported read-only production counts on this run are 5,059 prompt runs, 123 query traces, 184 generations, 6,615 job events, and 54,274 tombstones, with no GC settings; these were not independently remeasured by this agent. A row count is not a reclaimed-byte estimate, and SQLite file size does not automatically shrink when rows are deleted.

### Additional evidence for adversarial follow-up, not yet the release decision

`referenced_prompt_runs` fails closed for operational SQL errors (`gc.py:454–475`) but silently ignores malformed or non-array `prompt_trace_ids` JSON (`gc.py:476–482`). On a damaged/imported row, this makes unreadable references indistinguishable from none. The schema has no `json_valid` CHECK on that column (`db/schema.py:818`), so this deserves a separate adversarial reproduction and decision whether GC should stop loudly on malformed reference-bearing data. Do not silently broaden deletion or invent a repair during GC.

## 2. Pros & Cons

**Pros.** Fixes an observed violation of an already promised safety property. No capability reduction, schema change, default change, or production-data operation is needed. The test gives reproducible evidence rather than a hand-waved race claim. Smaller scope makes it possible to review the synchronization boundary directly. Separating existing safety defects from new policy avoids exposing a dangerous GC button before the guard is sound.

**Cons and limits.** A writer reservation briefly blocks other writes for the reference scan and deletion loop; retention on a large database can therefore contend with ingestion. This is preferable to deleting concurrently referenced evidence, but lock failures must remain visible. The patch reclaims no new classes of data and leaves B1/B2's policy/UI remainder open. SQLite serialization cannot protect references that a remote device has not yet exported, nor guarantee that a later local publisher will never reference a previously deleted run; those require a separate lifecycle contract, not a stronger comment.

## 3. Parent Adversarial Review and Revision

The parent challenged whether `BEGIN IMMEDIATE` solves the underlying lifetime problem, rather than only changing the interleaving. The challenge is correct. The original narrow recommendation above is **superseded** as a complete root-cause fix; it remains evidence of a genuine transaction defect, not an implementation authorization.

A production writer records a run in a committed transaction (`prompting/runner.py:205–214`, `db/_entities.py:2689–2707`), then calls the provider (`runner.py:226–249`), then commits its validator result (`runner.py:269–278`, `db/_entities.py:2722–2737`), and only afterward returns the trace ID to an artifact writer. `pipeline/community_reports.py:284–311` subsequently writes the report with that ID. `pipeline/graph_index.py:253–261, 300–312` similarly stages a graph batch in a later transaction. Therefore a cap can reclaim an unreferenced run while the provider is active, or while a finished `ok`/`repaired` result has not yet been published. Serializing the GC scan/deletion merely postpones the later writer until after deletion; it does not protect the run's lifetime.

Excluding `validator_status='pending'` fixes only the provider-call interval. Excluding recent rows is an arbitrary grace period and still fails for a paused writer. Neither establishes the promised invariant. The later writer's `finish_prompt_run` UPDATE does not check rowcount, so a deleted in-flight trace can also disappear silently before artifact publication.

Revised smallest-release recommendation: use the independently proven cache/read-only safety defects for the next patch, if the safety proposal survives review. A malformed reference-bearing JSON guard can join only after reproduction and cross-critique. Do **not** claim that a transaction-only prompt change resolves the retention issue or closes B2. Carry the prompt lifetime problem into a separate bounded design: define a durable reservation (or equivalent real owner lifetime) covering run creation through every artifact writer's final publication, recovery after interruption, and peer import. Audit all `run_prompt` callers before deciding whether existing state can represent it without a schema/API change. Do not hold an SQLite writer transaction across a provider call. Do not disable successful-run reclamation silently: that trades away the already shipped capability and requires the user's product decision.

### Exact disposable reproduction of the scan race

This is the complete command previously executed from the repo root. It changes no tracked files or production configuration and its temporary database is automatically removed:

```sh
.venv-dev/bin/python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from curator import db, gc
with TemporaryDirectory(prefix='incurator-retention-arena-') as d:
    p = Path(d) / 'state.sqlite'
    db.init_db(p)
    with db.connect(p) as c:
        for ident, stamp in [('PTR-old', '2020-01-01T00:00:00Z'), ('PTR-new', '2026-09-11T00:00:00Z')]:
            c.execute("INSERT INTO prompt_runs(trace_id,prompt_id,prompt_version,family,role,model_provider,input_hash,created_at) VALUES (?,'test','v1','query','writer','fake','h',?)", (ident,stamp))
    original = gc._prompt_runs_over_cap
    def add_reference_after_scan(c, keep):
        doomed = original(c, keep)
        print('scan_transaction_open:', c.in_transaction)
        with db.connect(p) as writer:
            writer.execute("INSERT INTO community_reports(id,community_key,title,summary,full_content,dependency_hash,prompt_run_id,created_at,updated_at) VALUES ('REP-test','c','t','s','p','h','PTR-old','2026-09-11','2026-09-11')")
        return doomed
    gc._prompt_runs_over_cap = add_reference_after_scan
    try:
        print('deleted:', gc.apply_prompt_run_cap(p, 1))
    finally:
        gc._prompt_runs_over_cap = original
    with db.connect(p) as c:
        print('dangling_report_references:', c.execute('SELECT count(*) FROM community_reports r LEFT JOIN prompt_runs p ON p.trace_id=r.prompt_run_id WHERE p.trace_id IS NULL').fetchone()[0])
        print('tombstones:', c.execute('SELECT count(*) FROM deleted_records').fetchone()[0])
PY
```
