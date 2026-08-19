# v0.60.0 Master Implementation Plan — ask the CLI for a value, not for prose

Date: 2026-08-19
Status: AWAITING USER APPROVAL — Arena concluded, viability measured, no code written.

Arena: `.agents/plans/structured_output_arena/`
(`00_problem.md`, `01_proposal_lead_architect.md`, `02_critique_redteam.md`,
`03_defense_measured.md`)

## 1. Objective

Make a structured-output prompt on the Antigravity CLI backend return a
validated object instead of prose the model may decide to *compute* with a
shell.

Definition of done, all required:

1. `curator.knowledge_unit_extract` runs through `--json-schema` +
   `--output-format json`, and the CLI's `structured_output` validates against
   the contract's own pydantic model with no repair step.
2. A run reports `num_turns: 1` — one turn means no tool call, so there is
   nothing for the permission layer to deny. This is the property that fixes the
   incident, and it is asserted, not assumed.
3. An empty `structured_output` beside a non-empty `response` never passes as a
   result. It falls back to today's scraping and says so.
4. Hartley (`sources.id=45`, 277 batches) ingests end to end.

## 2. Explicit Non-Goals

- **Not granting `python3` or any new permission.** The model needs no tool
  here; widening the sandbox to accommodate a JSON serialiser is the wrong
  trade in the wrong direction.
- **Not `claude` or `codex`.** They share the shape but not the flags. They stay
  `supports_structured_output = False` until each is measured. The briefing
  forbids assuming, and this plan obeys that.
- **Not resumable L2** (ROADMAP 6). Hartley losing 29 minutes on failure is a
  separate defect and stays separate.
- **Not a prompt rewrite.** Telling a model with tools not to use tools is
  advice, not a mechanism.
- No schema change, no migration.

## 3. Strict Quality Conditions & Release Gates

- **G1.** The contract's real schema (with `$defs`/`$ref` inlined) round-trips:
  `model_json_schema()` → flatten → `--json-schema` → `structured_output` →
  `model_validate()` yields the expected units. **Live-gated**
  (`INCURATOR_LIVE_AGY=1`), following the v0.56.1 precedent.
- **G2.** The flattener is tested offline against the real contract model and
  against a nested/enum fixture: no `$ref` survives, and a model referenced from
  two places is copied to both.
- **G3.** An empty `structured_output` with a non-empty `response` falls back to
  scraping and logs at WARNING. Tested offline with a canned envelope.
  **This gate exists because the unflattened schema produced exactly that
  shape and would otherwise have ingested a book to nothing.**
- **G4.** `num_turns` is read from the envelope and recorded; a run reporting
  `> 1` on a structured contract logs a warning (it means the model took a
  detour, which is the early sign of the incident recurring).
- **G5.** Envelope handling covers success, model error, and capacity
  exhaustion, each captured from a real run first (F2). `_raise_capacity_error`
  still fires under `--output-format json`.
- **G6.** `scripts/backend-check pytest | ruff | mypy` green; plugin vitest
  green. The three clients that already handle `json_mode` are unmodified.
- **G7.** Hartley ingests. Its `wiki jobs events` history is pasted into the
  evidence ledger — v0.59.0 exists to make this checkable.

## 4. Locked Design Decisions (Arena Consensus)

**D1 — A capability, not a special case.** `supports_structured_output` on the
client. `AntigravityCliClient` True; every other client False until measured.
Four releases (v0.48.4, v0.55.0, v0.56.1, and this) have failed at the seam
between "agentic CLI" and "LLM that returns text"; the seam gets a name.

**D2 — `chat()` gains ONE optional keyword**, `json_schema: dict | None = None`.
Optional with a `None` default so the three clients that already handle
`json_mode` need no edit — the same discipline that left `compile_source_l2`'s
28 call sites untouched in v0.59.0.

**D3 — The runner supplies the schema it already owns.** `contract.output_model`
is a pydantic model and `runner.py:191` already passes
`json_mode=contract.supports_json_mode`. Nothing new is computed.

**D4 — The schema is FLATTENED before it reaches the CLI.** Measured: the real
schema with `$defs`/`$ref` returns `SUCCESS`, `num_turns: 2`, and
`structured_output: {"units": []}` — silently empty, with the real answer left
in `response` under invented field names. The flattened schema returns
`num_turns: 1` and 2 units that validate against the contract model unchanged.
This step is not incidental; it is the difference between working and quietly
producing nothing.

**D5 — Empty structure beside non-empty prose is a defect signal.** Fall back to
scraping `response`, log at WARNING, never report an empty result as success.

**D6 — Schema as a string if the CLI accepts one** (the help text says "schema
string or path"). Measure first; it removes the per-call temp file entirely. If
only a path works, write once per contract per process, never per batch — 277
batches would otherwise litter the temp dir that `test_workspace_hygiene.py`
polices.

**D7 — `FailoverClient` re-evaluates the capability per delegate** and reports
the active delegate's value, not a fixed one.

## 5. Scope Exclusions & Stop Conditions

**Exclusions.** ROADMAP 6 (resumable L2), ROADMAP 1 (formula recovery),
ROADMAP 11 (backend agy sandbox), the `claude`/`codex` equivalents.

**Stop conditions — halt and ask:**

- The flattener cannot produce a `$ref`-free schema for any registered contract
  (e.g. a recursive model). Structured output is then not universally available
  and the capability needs a per-contract dimension.
- `num_turns > 1` persists on the flattened schema for the real extraction
  prompt. The mechanism is not doing what the measurement promised.
- Hartley fails again for a *different* reason. Fix one thing per release.
- Any change would touch a file hash-pinned in `D2_HOLDOUT_RESULT.yml`.

## 6. Evidence Ledger

To be written as `.agents/plans/07_structured_output_evidence.md` before coding.
Pre-recorded:

- **Rollback anchor**: `master` after v0.59.0 (`372c23d`).
- **Incident**: jobs 76 (Hartley, batch 37/277, 29 min) and 66 (Nicholson, 9/15)
  failed with `permission check failed for command "python3 -c ..."`; the model
  wrote a Python program to build (76) and to `jsonschema`-validate (66) its own
  answer. 34 of 36 jobs never took that route — the choice is non-deterministic.
- **Real schema**: 1286 bytes, `$defs` + `$ref`, 4 enums, 1
  `additionalProperties`.
- **Measured, same prompt, schema is the only variable**:

  | schema | status | num_turns | units |
  |---|---|---|---|
  | real (`$ref`) | SUCCESS | 2 | **0** |
  | flattened | SUCCESS | **1** | **2** |

- **Round-trip**: `KnowledgeUnitExtractOutput.model_validate(structured_output)`
  → 2 units, fields `canonical_name, confidence, formula_centrality,
  source_span_ids, statement, truth_status, unit_type`.
- **Dirty worktree**: clean. A separate session holds
  `fix/db-connect-commit-and-chunk-floor`; do not touch `db/schema.py` or
  `pipeline/knowledge_units.py`'s chunking without checking that branch first.

## 7. Execution Phases

Each phase passes `pytest` + `ruff` + `mypy` before the next.

- **P0 — Envelope reality (F2, D6).** Capture the `--output-format json`
  envelope for success, model error, and capacity exhaustion from real runs.
  Determine whether `--json-schema` accepts a string. Record all of it before
  touching `_run`'s return path.
- **P1 — Contract.** `SYSTEM_BEHAVIOR.md` gains the structured-output contract:
  the capability flag, schema flattening, the `structured_output` precedence
  rule, and the empty-structure fallback. **STOP for approval** if the client
  interface widens beyond D2's single keyword.
- **P2 — Failing tests first.** G2 (flattener), G3 (empty-structure fallback),
  G5 (envelope). Run against `master`; record which fail.
- **P3 — The flattener.** `$defs`/`$ref` inlining, with a recursion guard.
- **P4 — The client.** `supports_structured_output`, the `json_schema` keyword,
  argv construction, envelope parsing, the D5 fallback, `num_turns` warning.
- **P5 — The runner.** Pass `contract.output_model.model_json_schema()` through.
- **P6 — Live gate (G1).** `INCURATOR_LIVE_AGY=1` test with the real contract
  schema against the real CLI.
- **P7 — Hartley (G7).** Ingest the book. Paste `wiki jobs events` into the
  ledger. **This is the acceptance criterion**; a fixture proves nothing here,
  because the failure being fixed was a model's non-deterministic choice on
  dense real pages.
- **P8 — Docs, version bump (Minor → v0.60.0; new client capability and a
  changed LLM invocation contract), all four spec titles, CHANGELOG, PR.**

## 8. Why this plan exists in this shape

The first proposal was measured against a hand-written flat schema, concluded
the CLI mode "just works", and would have shipped a change that returns
`SUCCESS` with zero units for every batch of every book. The red team's refusal
to accept a toy sample is the only reason that was caught before code. The
lesson is recorded here rather than in a commit message: **measure the thing
that will actually run, not a convenient stand-in for it.**
