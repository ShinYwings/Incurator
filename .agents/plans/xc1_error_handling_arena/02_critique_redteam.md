# Critique on "Classify-Then-Resolve" + Resolution

Date: 2026-06-28 | Agent Persona: red_teamer / source_pair_analyst

## 1. Vulnerabilities & Flaws

1. **Turning silent degradation into hard aborts (RAG pipeline risk).** The
   source_pair_analyst's core fear: `ingest_*` and `pipeline/compile.py` run the
   L1→L4 DAG build. A swallow that today lets a single bad page/section be
   skipped keeps the rest of the source ingesting. If we SURFACE+re-raise it, one
   malformed page could abort an entire 277-batch source — exactly the kind of
   failure v0.27.2 just hardened against. **This is the highest risk.**

2. **"Read the try body" is not always decidable.** Some bodies call deep into
   third-party libs (pdfminer, sqlite, the LLM clients) whose exception surface is
   undocumented and version-dependent. NARROW based on an incomplete enumeration
   will let a real exception type slip through and crash where the broad catch
   used to cope.

3. **Test-triggering the error path can be hard.** Forcing `OSError` from a real
   file read or a provider timeout often needs monkeypatching; risk of tests that
   assert on log strings (brittle) rather than behavior.

4. **Scope creep into the god-files.** `llm.py` (9) borders the LLM/prompts group;
   touching it risks colliding with the pending prompt-v2 deep pass.

5. **Version classification.** Is this Patch or Minor? Behavioral failure-mode
   change argues Minor; "just bug fixes" argues Patch. Ambiguity will trip the
   version-consistency gate if mis-set.

## 2. Suggested Alternatives (accepted into the Master Plan)

- **R1 — Default to NARROW, not SURFACE, inside the DAG build.** For
  `ingest_raw.py` / `ingest_worker.py` / `pipeline/compile.py`, the disposition
  bias is: KEEP the documented best-effort guards; NARROW the rest so *unexpected*
  exceptions propagate while *expected* per-item failures still degrade. Only
  SURFACE (force-raise) where the swallow hides a *whole-operation* bug AND there
  is no valid fallback. **Counter-example: `ingest_raw.py:155` is NOT a SURFACE** —
  its `try` resolves an external path and deliberately falls back to
  `return source`; re-raising would crash the caller on a transient
  `sqlite3.OperationalError`/`OSError`. It is **NARROW+log** (catch the expected
  resolution exceptions, log, fall through to the fallback). Every SURFACE
  decision must be validated in testbed `wiki add` on a multi-page source to
  confirm it does not abort the run.

- **R2 — When the exception surface is undecidable, KEEP+log, do not NARROW.**
  Better an honest logged broad-catch than a NARROW that misses a type. NARROW
  only when the raisable set is knowable from stdlib/our own code.

- **R3 — Behavioral tests over log-string asserts.** Prefer asserting the
  observable outcome (re-raise propagates / fallback value returned / item
  skipped but run completes). Log assertions only as a secondary signal.

- **R4 — Hard scope boundary.** `llm.py` IS in scope for swallow-narrowing but
  NOT for any prompt/identity logic change (that is prompt-v2). `cli.py`,
  `mcp_server.py`, `plugin_api.py` are OUT (CM-1). `model_setup.py` (11) is OUT of
  the first slice — borderline setup/UX, deferred to a second error-handling PR.

- **R5 — Patch (0.27.5).** Per AGENTS.md 0.x SemVer, a Minor requires a new
  user-facing capability or a schema/contract change; this slice has neither
  (internal error-handling only). It is a **Patch** off the current 0.27.4 state.
  The spec-line sync mandate does NOT apply — the `0.27` minor line is unchanged,
  so the four spec titles stay as-is.

## 3. Consensus

Adopt R1–R5. The plan's disposition bias inside the DAG build is **KEEP/NARROW
first, SURFACE only with testbed proof**. First slice excludes `model_setup.py`
and all god-files. Stop-condition: if any SURFACE change causes a testbed
`wiki add/sync` regression that can't be resolved by re-classifying to KEEP/NARROW,
stop and report.
