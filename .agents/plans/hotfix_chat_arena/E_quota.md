# Runtime diagnosis: terminal quota retries masquerade as generation
Date: 2026-09-10 | Agent Persona: Runtime maintainer

## 1. Core Logic & Implementation

The exact user question `4.2. 절부터 4.6절까지 ... 내 노트들로` appears in
local agy conversations e2352bc9-f633-4596-842b-993889c236c3 and
dcf99d94-e5b7-48bd-aac7-4ddc3ac4da90. Their final error payloads contain
`RESOURCE_EXHAUSTED` / `Individual quota reached`. CLI log runs on 2026-09-10
show retries at 4s, approximately 7s, 15s, 25s, 50s, 90s and longer until
the five-minute print timeout. Native error steps initially hide the cause.

Add a unique per-invocation log under the existing plugin CLI cache, passed
through the supported `--log-file`. Observe append-only diagnostics with a
nonpersistent watcher; read newly appended bytes in bounded chunks and preserve
partial lines. Match only actual runtime `Run: attempt ... failed` log records
with `RESOURCE_EXHAUSTED` and `Individual quota reached`. Generic 429, quota
discussion in answers, tool output and temporary capacity errors are not enough.
On terminal quota, stop this invocation and surface its diagnostic immediately.
The same rule applies to stream and completion calls. Close watchers and remove
the ephemeral file on every termination path; no provider switch or automatic retry.

## 2. Pros & Cons

This corrects false generation status and removes measured futile waiting.
It cannot restore an exhausted provider quota. Log matching deliberately
prefers a false negative over killing a valid answer if upstream formatting
changes; normal timeout diagnostics remain available. Do not watch global logs
or kill another invocation. Do not generalize to transient rate limiting.

## 3. Validation

Test real incremental log bytes, split records, unrelated 429/answer content,
terminal quota, disposal and separate concurrent paths. Integration fake child
must stop before a five-minute timeout and report quota, including completion.
Live invocation with exhausted selected provider must fail promptly and disclose
the cause; a successful earlier 1.61s equation stream remains separate evidence.
