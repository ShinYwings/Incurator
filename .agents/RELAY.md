# Active Relay State

**STATUS: ACTIVE HOTFIX - v0.27.2 follow-up for large PDF L2 extraction.**

**Branch**: `hotfix/v0.27.2-l2-terminal-pending-traces`
**PR**: https://github.com/ShinYwings/Incurator/pull/60
**Previous PR**: #59 (`v0.27.1`) was merged but did not fully resolve the
production PDF.

---

## Goal

Finish the production fix for source id `27`:
`04_Resources/References/Multiple_View_Geometry_in_Computer_Vision-EN.md`,
the Zotero-backed PDF referenced from
`/Users/shin/shinywings/second_brain/03_Notes/Vision/MultipleViewGeometry.md`.

## Analysis & Reasoning

- v0.27.1 fixed partial L2 persistence and recursive batch-split retry, but the
  production retry still failed.
- The first retry used the installed `/Users/shin/anaconda3/bin/wiki` path and
  ran for ~2 hours. It recovered many parse-validation failures but ended with
  five `prompt_runs` rows stuck in `pending` and a generic
  `knowledge unit extraction failed` source/job error.
- Root cause found in current source: `extract_knowledge_units()` and graph
  extraction called `client.optimal_chunk_chars()` as a method. Real CLI clients
  expose `optimal_chunk_chars` as a property, so the call raised `TypeError` and
  silently fell back to 60,000-character batches. The failing production run
  therefore used 83 huge batches instead of the Antigravity-safe ~18k budget
  that would produce 277 smaller batches.
- `run_prompt()` opened a `prompt_runs` row before `client.chat()`, but if the
  provider call raised, the row was never closed. This caused stale active
  `pending` traces.
- The top-level L2 batch loop kept running after a fatal batch error, wasting
  calls that could never be published.
- A patched local production run using
  `VAULT_ROOT=/Users/shin/shinywings/second_brain PYTHONPATH=backend/src .venv-dev/bin/python -m curator.cli jobs run --limit 1`
  confirmed the new behavior: exactly one new prompt trace opened and closed as
  `failed` with `AntigravityCliError: Antigravity capacity exhausted (429)`;
  job #37 requeued with retry_count=1 and detailed source/job error. No active
  generation-less units were written.
- Production vault has no fallback LLM configured; remaining build completion is
  blocked on Antigravity `gemini-3.5-flash` capacity or configuring a fallback.

## Progress Status

- Implemented shared `client_optimal_chunk_chars()` helper supporting both
  property and method clients.
- Wired helper into L2 knowledge-unit extraction and graph extraction.
- `run_prompt()` now closes prompt traces as `failed` if the initial provider
  call or repair call raises.
- L2 top-level batch loop now fails fast after first unrecoverable batch.
- `compile_source_l2()` now returns the detailed extraction error instead of
  collapsing it to `knowledge unit extraction failed`.
- Updated tests, docs, changelog, versions, and roadmap for `v0.27.2`.
- Pushed branch and opened draft PR #60.

## Validation So Far

- `scripts/backend-check ruff`: passed.
- `scripts/backend-check mypy`: passed, 98 source files.
- `scripts/backend-check pytest`: 1079 passed, 6 skipped, 5 xfailed, 7 warnings.
- `npx vitest run -c ./vitest.config.ts` from `plugin/`: 60 files / 598 tests passed.
- `VAULT_ROOT=testbed PYTHONPATH=backend/src .venv-dev/bin/python -m curator.cli status`: passed.
- Production diagnostic retry with patched local code:
  - source id 27 remains L2 error due external Antigravity 429 capacity.
  - job #37 is queued for retry with retry_count=1 and detailed error.
  - new prompt trace `PTR-67fc39de` closed as `failed`.

## Critical Context / Blockers

- Do not run the installed `/Users/shin/anaconda3/bin/wiki` for this source until
  v0.27.2 is installed; the installed backend still reports `backend_version`
  `0.17.0` and the previous production retry used the unsafe 60k fallback path.
- The production source files were not edited.
- `job #37` is currently queued after a transient 429. It should only be retried
  with the patched backend and either available Antigravity capacity or a
  configured fallback provider.
- Separate stash still exists: `wip-v0.27.1-g13-cli-path-parity`; if resumed,
  it must be renumbered after v0.27.2.

## Immediate Next Action

Human review/merge PR #60. After v0.27.2 is installed and Antigravity capacity
is available or a fallback LLM is configured, retry production job #37/source
#27 with the patched backend.
