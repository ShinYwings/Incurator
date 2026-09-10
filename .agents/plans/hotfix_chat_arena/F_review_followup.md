# Native stream and preparation boundary review
Date: 2026-09-11

Provider reviewer independently identified raw auth-substring cancellation,
caller-abort/diagnostic precedence, and partial agy success without a result.
Latency reviewer independently reproduced auth failure using the actual
callback and verified cancellation ordering. Latency reviewer found the
deadline/readiness evidence loss; provider reviewer confirmed it and rejected
unconditional cache peeking because a gated `again` turn must remain gated.

Consensus: reuse the same permitted fetch's ready result at assembly, with no
new wait. Native JSON failures are diagnosed structurally, not from answer
substrings. Caller cancellation takes precedence before unsettled diagnostic
handling, disposing its watcher. agy requires an explicit SUCCESS result for
normal completion; missing result preserves visible text but rejects completion.
Inline and JSON caller formats remain authoritative in the shared agy prompt.
Final provider cross-review (confidence 95) found the same substring mistake
for `returning partial output`: ordinary stderr prose rejected a SUCCESS answer,
even for Codex. Root confirmed the unscoped regex. Limit matching to complete
anchored native agy timeout lines and agy invocations, with quoted-prose and real
timeout regression cases. Prior-PR/history/comment review found no other blocker.

Validation: deferred-clock t4/t5/t10 and gated follow-up tests; fake child native
auth quotation, abort/log races, EOF without result, malformed result and
non-streaming partial replacement tests. Existing SDK/tool/permission policies
are unchanged. User explicitly waived Claude verification on 2026-09-11 after
the mandatory skill invocation failed authentication; Codex adversarial review
and CI still apply. No Claude login or additional credits required.
