# v0.37.1 Query Provider Failure UX Master Implementation Plan

Date: 2026-07-30
Status: APPROVED — implementation started 2026-07-30.

## 1. Objective

Make every backend query provider fail in one observable, auditable way. A
provider/timeout/quota/blank-output/repair failure must retain its QTR, terminal
PTR, and retrieved evidence; use the configured fallback consistently; render a
concise actionable message on CLI/MCP/plugin surfaces; and never become a Rich
traceback, silent answer, or exit-0 false success.

Definition of done:

- initial and repair-call provider failures return a failed query result with
  QTR/PTR and ContextService provenance;
- the failed QTR has a `synthesis_status="failed"` child action;
- blank output and Codex non-zero partial output can never validate as success;
- every `LLMError` subtype participates in configured fallback, including Codex;
- all-provider failure preserves bounded attempt-order diagnostics;
- CLI prints successful answers, exits 1 on failures, and shows no traceback;
- MCP and hidden plugin query share the same existing-field envelope;
- the hidden plugin command remains JSON-parseable on exit 1;
- docs, tests, release manifests, changelog, full CI, and testbed smoke pass.

## 2. Explicit Non-Goals

- New `error_type`, `retryable`, provider-attempt JSON fields, DB columns, or
  schema migration.
- Changing the one-repair prompt policy or adding query-level retries.
- General broad-exception cleanup or a generic plugin backend-command redesign.
- Cancellation handling, trace-storage outage recovery, provider-wire malformed
  payloads, failover-time PTR provider attribution, or provider temp-file
  cleanup; these remain separately triaged.
- Changing normal Obsidian sidechat from ContextService packs to backend
  synthesis.
- Authored-wikilink topology validation.

## 3. Strict Quality Conditions & Release Gates

- Only `LLMError` becomes a provider-failure result; an injected `RuntimeError`
  or DB error still propagates.
- No successful query field is removed. No DDL/schema-version change occurs.
- Failed PTR status, retry count, first invalid output hash, QTR child action,
  and retrieved provenance are all asserted together.
- All five provider families obey non-empty output; configured fallback handles
  every `LLMError` subtype.
- Codex return code is checked before last-message output is accepted.
- CLI tests assert answer text on success and exit 1/no `Traceback` on failure.
- MCP and plugin API parity is asserted against one shared query service.
- Hidden plugin failure emits exactly one parseable JSON object before exit 1.
- Plugin display retains parseable error, QTR, PTR, and warnings.
- `scripts/backend-check pytest`, `ruff`, `mypy`, plugin Vitest/build,
  version/spec parity, and active testbed smoke pass.

## 4. Locked Design Decisions (Arena Consensus)

- Keep the existing `LLMError` hierarchy as the typed expected-provider
  boundary; do not add a second exception hierarchy.
- Normalize blank non-streaming provider output at the provider contract so
  failover can run before the prompt/query boundary sees the failure.
- Make failover catch `LLMError` + `OSError`, retain bounded provider-labelled
  failures in attempt order, and chain the terminal error from the final cause.
- Reject Codex output whenever its process exit is non-zero, even if a
  valid-looking last-message file exists.
- Catch `LLMError` only after ContextService has produced a result/QTR. Recover
  PTRs through `list_prompt_runs_for_query`, preserve provenance, and reuse the
  existing QTR updater.
- Use only existing public `error`, QTR, PTR, provenance, warning, and nested
  trace fields.
- Use one backend-local query serializer/service; MCP delegates to it with an
  explicit English output default. Plugin API remains independent of MCP.
- CLI REPL returns session failure state; the command exits after cleanup.
- Existing plugin stdout-first JSON parsing is preserved and characterized.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: generic backend JSON errors, cancellation, DB/trace-storage
  recovery, malformed provider protocols, prompt attribution after failover,
  streaming-provider behavior, and unrelated query/result legacy cleanup.
- **Stop Conditions**:
  - stop if preserving the MCP success contract requires a new public field or
    removal/change of an existing field; reclassify as a minor release;
  - stop if a DB schema or migration is required;
  - stop if a provider needs an extra retry above configured fallback;
  - stop if a real active testbed would need reinitialization or external
    resources copied into the vault;
  - stop if an expected provider failure cannot leave either a recoverable PTR
    or an explicit trace-persistence failure.

## 6. Evidence Ledger

- Merge-base / rollback anchor:
  `d539f67604d4d6e2d25b82f946d156d5ad9224cd`.
- Starting release manifests: `0.37.0`; DB schema remains v13.
- Deterministic repair-failure reproduction:
  `AntigravityCliError` escaped; one QTR existed with no prompt ids; one failed
  PTR existed with `retry_count=1`; the QTR had zero synthesis actions.
- Existing prompt-run tests already prove terminal failed PTR, original
  exception survival, and first-response hash preservation.
- Current testbed is ResNet Dynamics. No checked-in Gaussian Splatting scenario
  exists; production/cache Gaussian data will not be mutated.
- Detailed evidence: `.agents/plans/02_query_provider_failure_evidence.md`.

## 7. Execution Phases (Follow TDD and CI at each phase)

- **P0 — Research & Characterization**
  - Freeze successful CLI answer visibility, current non-zero JSON parsing, MCP
    success shape, provider blank output, Codex non-zero partial output, and
    configured fallback behavior before changing logic.
  - Preserve the deterministic repair-failure baseline in a regression test.
- **P1 — Contract Specification**
  - Update System Behavior, Curator Schema (trace relationship only; no DDL),
    Plugin Schema, and all describing EN guides first, then their KR pairs.
  - Specify existing-field failure envelopes, CLI exit, QTR/PTR/provenance, and
    provider non-empty/non-zero behavior.
- **P2 — Provider And Prompt TDD**
  - Add failing tests for blank output across providers/failover, Codex
    non-zero last-message output, Codex fallback, all-provider diagnostics,
    initial failure, and repair failure.
  - Implement the provider success/failover normalization.
  - Verify focused provider/prompt pytest + ruff.
- **P3 — Query Trace Boundary**
  - Add orchestrator tests for initial and repair failure, failed PTR recovery,
    first-output hash, failed synthesis action, retained evidence, validation
    failure, and unexpected-exception propagation.
  - Implement the narrow `LLMError` catch and existing-field failure result.
  - Verify query/prompt tests + ruff.
- **P4 — Surface Consolidation**
  - Characterize current success output, then centralize result serialization
    and make MCP query delegate to the backend-local service.
  - Add CLI success/failure exit tests and hidden plugin JSON+exit tests.
  - Preserve language/workspace/L3-incomplete behavior.
  - Verify focused backend tests + ruff/mypy.
- **P5 — Plugin Display**
  - Add failed-result normalization, MCP compaction, trace-panel error, and
    stdout-first non-zero JSON characterization tests.
  - Preserve ordinary ContextService-first sidechat behavior.
  - Verify focused Vitest + production build.
- **P6 — Full Validation And Testbed Smoke**
  - Run full backend pytest/ruff/mypy and plugin Vitest/build.
  - Run version/spec/docs parity tests.
  - Without reinitializing the active ResNet testbed, run status/lint and a real
    query smoke when the configured provider is available; deterministic failure
    tests remain the release gate if external provider capacity is unavailable.
- **P7 — Patch Release**
  - Bump all three manifests to `0.37.1`; do not change static spec titles because
    the `v0.37` minor line is unchanged.
  - Update `CHANGELOG.md`, ROADMAP, RELAY, and umbrella evidence; delete completed
    v0.37.1 plan artifacts; create `chore(release): v0.37.1`; push, open the PR,
    and monitor CI/review.
