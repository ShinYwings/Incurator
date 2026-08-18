# Critique on the two fixes proposed in the briefing

Date: 2026-08-18 | Agent Persona: red_teamer (with schema_guardian on defect 1)

The briefing carried two suggested fixes forward from the report. Both have a
cheaper-looking variant that must be rejected explicitly, or someone will
"simplify" the fix back into the bug later.

## 1. Vulnerabilities & Flaws

### 1.1 `isolation_level=None` is the wrong fix for defect 1 — reject it

The report offered two options: commit inside `connect()` before the `yield`, or
set `isolation_level=None` on the connection so DDL/DML autocommit and
`BEGIN IMMEDIATE` owns its own transaction explicitly. The second is a
repository-wide semantic change disguised as a one-word edit.

At `isolation_level=None` **every** statement autocommits. The connection never
holds an implicit transaction, so `conn.commit()` after the `yield` becomes a
no-op and the rollback-on-exception behaviour of the `with connect(...) as conn`
block disappears entirely. That behaviour is not incidental — `_maybe_conn`
documents relying on it verbatim:

> Lets compiler helpers run inside ONE caller-controlled transaction so a
> multi-step publish is atomic (SYSTEM_BEHAVIOR §26.3): any exception rolls the
> whole transaction back.

Turning on autocommit therefore breaks the atomic-publish invariant for every
compiler path in the repo, in order to fix one `BEGIN IMMEDIATE`. It converts a
loud, narrow, reproducible failure into a silent, wide one: a publish that
crashes halfway would leave half its rows committed. **Rejected.**

### 1.2 Committing before `yield` must be justified, not just performed

The surviving option is not free either, and the justification belongs in the
code. After the fix, schema setup is committed independently of the caller's
work, so a caller whose body raises leaves the schema *installed* while its own
writes roll back.

That is correct, and it is already the established contract: `init_db` commits
exactly this set of statements and nothing else. Schema DDL plus a version stamp
is idempotent and carries no user data; there is no scenario in which a caller
wants the schema uncreated because its own insert failed. But state it in the
comment, because the next reader will otherwise see two `commit()` calls in one
function and delete the first one.

### 1.3 The regression test must assert the loop, not just the first call

A test that calls `claim_next_job` once on a fresh DB and asserts no raise would
pass against a fix that commits but leaves the schema row missing. The defect's
distinguishing property is that it *repeats*, so the test must call twice and
must additionally assert that the `schema_version` row survives — that is the
row whose rollback armed the second failure. Test the mechanism, not the
symptom.

Also cover the `UPDATE` branch: a DB carrying a stale `schema_version` value
takes different DML in `_stamp_schema_version` and reproduces the same failure
on the first claim after a version bump. A fix verified only against the INSERT
branch is verified against half the defect.

### 1.4 `wiki jobs run` should be checked end to end, not only the DB helper

`claim_next_job` is reached through `wiki jobs run`. If the CLI happens to call
`init_db` (or anything that commits) before draining, the unit-level fix is
still right but the user-facing claim "`wiki jobs run` against an uninitialised
repo-cache DB now works" would be unverified. Read the command path and say
which it is instead of asserting the end-to-end story from the unit test.

### 1.5 Clamping `client_optimal_chunk_chars` to a floor is the wrong fix for defect 2 — reject it

The report's second suggestion was to validate inside
`client_optimal_chunk_chars` and fall back to the default when the reported
value is below a sane minimum. This is worse than it looks, on three counts.

**It can overflow the very context it is protecting.** A client that honestly
reports a small window is not misconfigured — it is small. `OllamaClient`
computes its budget from measured host RAM and returns as little as 13,107
chars on a low-RAM machine. Substituting the 60,000-char default for a
truthfully-small value hands that model a prompt 4.6x its context. The failure
mode swaps a quota bomb for silent truncation by the provider.

**A clamp-to-minimum variant is no better, only quieter.** Raising 200 to a
4,000-char floor keeps the prompt oversized for whatever client reported 200; it
just moves the overflow from the subdivision arithmetic to the provider.

**It breaks the batching tests for the wrong reason.**
`test_property_chunk_budget_is_respected`,
`test_failed_late_batch_leaves_no_partial_units` and
`test_provider_exception_leaves_no_partial_units` all pass
`optimal_chars=160` deliberately, to force multi-batch behaviour on short
fixture spans. Any floor above 160 collapses them to one batch and the
assertions (`client.calls == 2`) fail. Rewriting three passing tests to
accommodate a clamp is a signal that the clamp is fighting a legitimate input,
not rejecting an illegitimate one.

A small batch budget is **harmless**: it produces more, smaller batches, and the
count stays proportional to the document. Nothing about it is a bug.

### 1.6 The actual disease is the unchecked subtraction, and it has two sites

`max_chars - 500` is used as a *size* (`knowledge_units.py:348`) and as a
*slice bound* (`graph_index.py:91`) with no positivity guarantee at either. That
expression is the defect. Fixing only the site named in the report leaves the
identical arithmetic live one module over, where its negative value silently
amputates the tail of every knowledge-unit statement and then labels the result
`... [TRUNCATED]` — a truthfulness failure that no cost metric would ever
surface.

### 1.7 `_chunk_text`'s forward-progress guard is where the explosion is manufactured

Flooring both call sites fixes today's callers and nothing else. `_chunk_text`
is module-private but has three callers, and it will accept a non-positive
`chunk_size` from any future one and answer with a one-character-per-chunk walk.
A size argument that is zero or negative is a programming error. The guard that
converts it into 24,000 chunks is exactly what let this defect stay invisible:
it never hangs, never raises, and never logs — it just spends.

## 2. Suggested Alternatives

1. **Defect 1**: commit inside `connect()` after `_stamp_schema_version` and
   before `yield`. Keep the post-`yield` commit. Comment both. Do not touch
   `isolation_level`.
2. **Defect 1 test**: fresh DB, `claim_next_job` twice, assert no raise on
   either and assert the `schema_version` row is present afterwards. Add the
   stale-version (`UPDATE` branch) case. Add an enqueue-then-claim case so the
   fix is shown to claim a real job, not merely to return `None` quietly.
3. **Defect 2**: floor the subdivision at its two sites —
   `max(_MIN_SUBDIVISION_CHARS, max_chars - 500)` — and leave
   `client_optimal_chunk_chars` returning what the client reports. Pick the
   floor above the 500-char overlap so `_chunk_text` still makes real forward
   progress (the report's suggested 1,000 satisfies this: advance = 500/chunk).
4. **Defect 2, root**: make `_chunk_text` raise `ValueError` on a non-positive
   `chunk_size`. With (3) in place no production path can reach it, which is the
   point — it converts a class of future quota bombs into an immediate, local
   failure.
5. **Defect 2 test**: assert the batch count is proportional to the document for
   a tiny reported budget, and assert `_chunk_text` raises rather than walking.
   Assert a concrete number, not just "fewer than before".
