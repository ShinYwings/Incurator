# Consensus Defense — Bounded Historical Audit With Fault-Transition Gates

Date: 2026-07-30 | Agent Persona: System Synthesizer

## 1. Accepted Corrections

- Add a release-to-current-symbol ledger and audit moved facades at both ends.
- Every implementation phase must cover six transition points:
  before mutation, inside transaction, after authoritative commit, concurrent
  mutation, cancellation/timeout, and stale replay.
- Source deletion computes a dependency closure and distinguishes shared
  canonical retirement from device-local hard deletion.
- Timestamp successors accept only valid UTC revisions and are strictly greater
  than observed clocks.
- Corrupt durable state is preserved; recovery is explicit and reversible.
- Backend timeout/output limits are command-class policies.
- The active testbed remains untouched; validation uses temporary copies and
  current contracts only.

## 2. Rejected Alternatives

- One v0.39.0 mega-fix: rejected because it makes PR #101 unreviewable and
  violates the existing stability delivery model.
- Schema-v14 ownership migration: rejected until existing dependency data proves
  insufficient.
- Happy-path-only full-suite validation: rejected as incapable of detecting the
  confirmed failures.
- Historical commit environment replay for every release: rejected as expensive
  and insufficient without fault tests.

## 3. Consensus

Approve the lead architecture with the red-team corrections. PR #101 receives
only authored-topology follow-up fixes. Cross-system work ships as sequential
v0.39.x patches. The umbrella audit remains active until every v0.32.0+ release
has two dry passes and every P0/P1 finding is closed.

