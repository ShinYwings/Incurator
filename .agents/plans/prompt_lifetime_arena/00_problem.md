# Prompt-Run Lifetime and Retention Briefing
Date: 2026-09-12 | Baseline: v0.82.6, master d0171b47

## Problem and evidence

Continue B1/B2 after cache-preservation PR #207. The existing opt-in
gc.prompt_runs_keep deletes runs based on committed local references, but prompt
creation, provider completion and artifact publication use separate commits.
The finite cap may delete a slow pending or completed-but-unpublished result;
the later artifact stores a dangling trace. BEGIN IMMEDIATE on GC alone cannot
solve this. See retention_followup_arena proposals/critique/defense for the
already verified paths; do not rediscover them or implement the rejected lock fix.

The cap emits deletion tombstones through fleet sync. A peer may hold a live
reference not yet imported here. Determine exactly how that schedule behaves,
whether an equivalent ownership/provenance contract already exists, and what
smallest complete fix preserves useful reclamation and offline behavior.

## Locked constraints

- No production GC, vault edits, migration or reindex; isolated reproduction only.
- No implicit cap disabling, keep-all-successful replacement, grace period,
  holding SQLite write lock across provider calls, or truncating chat history.
- One stored-contract change per release; use existing schema/ownership only if
  it actually proves the required lifetime, not to avoid versioning.
- User delegated prompt-run policy, including a cap. Engineering choices with
  equal capability are autonomous. A choice that removes offline history or
  useful reclamation needs a concrete user decision; explain exact costs.
- User allowed available-agent review after expired Claude OAuth; do not claim
  a successful Claude skill execution. Full real independent review remains.

## Independent Arena work

1. Producer/reference owner audit and minimal local lifetime design.
2. Cross-device delayed-reference/tombstone schedule, isolated reproduction,
   feasible fleet-safe alternatives and any unavoidable product fork.
3. Retention capability and storage alternatives: exact prompt fields consumed,
   compact payload vs whole-row deletion, snapshots/history compatibility, and
   independently challenge tradeoffs. No invented default or code workaround.

Write proposal files, cross-critique, then synthesize a template-compliant plan
or concrete decision record if the product fork genuinely blocks implementation.

## User decision — saved chat owners (2026-09-13)

Question: "Should prompt-trace links saved in chat protect their full diagnostic
records from GC? Knowledge records and stored query traces will remain protected
either way."

Answer: "Protect saved chat links too; retain diagnostics while those chats exist".

This is a resolved capability requirement. Include saved chat link discovery,
durable ownership across save/delete/crash, delayed cross-device session sync,
historical unavailable diagnostics, and plugin/backend session writer
coordination in the design. Preserve offline saving and the full transcript.
Do not treat a local scan of today's file as proof that no offline peer owns a
trace. Do not fabricate a diagnostic row from a trace identifier. Actual
production migration remains a separate authorized action after private rehearsal.
