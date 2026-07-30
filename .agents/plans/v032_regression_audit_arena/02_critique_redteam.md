# Critique On The Integrity-Boundary Patch Chain

Date: 2026-07-30 | Agent Persona: Red Team / Failure Injection

## 1. Vulnerabilities & Flaws

1. Grouping by subsystem can miss cross-release causal chains, especially
   v0.32.1 session serialization followed by v0.36.0 file moves.
2. A passing full suite can still hide a false-success path because most tests
   exercise completed operations, not interrupted transitions.
3. Source-deletion cleanup can over-delete shared graph rows if ownership is
   inferred only from `source_id`.
4. Clock repair can create artificial future drift if it blindly adds time to
   malformed/unbounded remote revisions.
5. Blocking session saves on corruption can strand users without a recovery
   path.
6. Generic backend timeouts can kill legitimate build/sync commands.
7. One umbrella approval can become a disguised mega-PR unless release
   boundaries are enforced in the plan and Git history.
8. The existing active ResNet scenario is historically stale in sections that
   still mention retired Exhibition behavior; blindly running it is not valid
   evidence.

## 2. Suggested Alternatives

- Maintain a release-to-current-symbol map so moved code is reviewed in both its
  historical and current owner.
- Require explicit fault oracles for pre-commit, in-transaction, post-commit,
  cancellation, timeout, and replay.
- Use artifact dependencies and independent support ownership before deleting
  shared graph state.
- Validate timestamps and derive a bounded logical successor, rejecting
  malformed values.
- Preserve corrupt files byte-for-byte and expose a deliberate backup/restore
  recovery operation.
- Use command-class timeout policies rather than one global timeout.
- Commit and release each integrity boundary separately.
- Use temporary DB/vault fixtures and the current testbed-template G9 contract;
  do not claim outdated EXH scenario phases as validation.

