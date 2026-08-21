# v0.61.2 Master Implementation Plan — two latent defects

Date: 2026-08-18
Status: APPROVED — Arena concluded. Patch release; no new capability, no schema
change, no contract change.

Briefing: `.agents/plans/latent_defect_fixes_arena/00_problem.md`
Critique: `.agents/plans/latent_defect_fixes_arena/02_critique_redteam.md`
Evidence: `.agents/plans/07_latent_defect_fixes_evidence.md`

## 1. Objective

Two defects that reproduce on `master` at `0c0ebeb` with a clean worktree stop
reproducing, and stay stopped:

1. `db.claim_next_job` raises `OperationalError: cannot start a transaction
   within a transaction` on any state DB whose `schema_version` row is missing
   or stale, and the raise rolls that row back so the next call fails
   identically — an infinite failure loop, not a transient one.
2. `pipeline/knowledge_units.extract_knowledge_units` passes a **negative**
   `chunk_size` to `_chunk_text` whenever the active client reports
   `optimal_chunk_chars <= 500`, and `_chunk_text` answers by emitting one chunk
   per character POSITION, each holding nearly the whole remaining text (3,000
   chunks totalling 810,000 characters for a 3,000-character span — a 270x
   amplification, not a split). Measured: 8 sections x 3,000 chars at
   `optimal_chunk_chars = 200` produced 24,000 refined spans and **3,920
   batches** — 3,920 LLM calls.

**Definition of done.** A fresh temp DB whose first-ever operation is
`claim_next_job` returns `None` instead of raising, returns `None` again on a
second call, and carries a committed `schema_version` row afterwards; the same
holds for a DB carrying a stale version. A client reporting a tiny chunk budget
produces a batch count proportional to the document instead of to its character
count, and `_chunk_text` refuses a non-positive `chunk_size` outright.

## 2. Explicit Non-Goals

- **No `isolation_level` change.** See §4, decision D1. The repo's atomic-publish
  invariant depends on the implicit transaction that autocommit would remove.
- **No clamp inside `client_optimal_chunk_chars`.** See §4, decision D3. A small
  reported budget is legitimate input, not corruption.
- **No change to `ingest_raw.py:1833`'s `getattr(client, "optimal_chunk_chars",
  30000)`.** It is a third, inconsistent read of the same client attribute and
  it does not participate in either defect: it never subtracts, so it cannot go
  negative. Routing it through `client_optimal_chunk_chars` would silently move
  the L1 chunk default from 30,000 to 60,000, which is a behaviour change with
  no bug behind it. Noted for follow-up, not fixed here.
- **No resumability, progress, or job-event work.** That is v0.59.0 (plan 06) on
  `feature/v0.59.0-job-progress`, and it must not be entangled with this.
- **No new tests for the two shielded call paths beyond reading them.** See §6.

## 3. Strict Quality Conditions & Release Gates

- Each defect has a regression test that FAILS on `0c0ebeb` and passes after.
- `scripts/backend-check pytest` green across the whole backend suite — in
  particular the three existing tests that deliberately pass
  `optimal_chars=160` must still pass **unmodified**. If a candidate fix
  requires editing them, that fix is wrong (critique §1.5).
- `scripts/backend-check ruff` and `scripts/backend-check mypy` clean.
- `plugin/` untouched; `npx vitest run -c ./plugin/vitest.config.ts` unaffected
  and still green.
- All four build manifests agree on `0.61.2`. Spec titles stay on the `v0.58`
  line — a patch bump does not touch them (`test_spec_sync.py::_active_line`).
- `CHANGELOG.md` carries a `### Fixed` section and nothing else, which is what
  makes this a Patch under the 0.x SemVer criteria in `CLAUDE.md`.

## 4. Locked Design Decisions (Arena Consensus)

### D1 — `connect()` commits the schema write before `yield`; `isolation_level` is untouched

```python
        conn.executescript(SCHEMA_SQL)
        if _triggers_need_refresh(conn):
            _refresh_current_triggers(conn)
        _stamp_schema_version(conn)
        conn.commit()      # <- new
        yield conn
        conn.commit()
```

`_stamp_schema_version` runs DML (`INSERT` on a new DB, `UPDATE` on a stale
one). At `sqlite3`'s default `isolation_level=""` that opens an implicit
transaction which stays open across the `yield`, so the caller receives a
connection already inside a transaction and `BEGIN IMMEDIATE` is illegal.
Committing here closes it.

The rejected alternative, `isolation_level=None`, makes every statement
autocommit. That deletes the rollback-on-exception semantics of
`with connect(...) as conn`, which `_maybe_conn` documents depending on for
atomic multi-step publishes (SYSTEM_BEHAVIOR §26.3). Fixing one `BEGIN` by
breaking every compiler publish is not a trade; it converts a narrow loud
failure into a wide silent one.

Committing schema setup separately from caller work is not a new contract:
`init_db` already commits exactly these statements and nothing else. Schema DDL
plus a version stamp is idempotent and holds no user data, so there is no
caller for whom "my insert failed, therefore the schema should not exist" is
correct.

### D2 — the regression test asserts the loop and both DML branches

Calling once and asserting no raise would pass against a fix that commits
nothing. The defect's distinguishing property is that it repeats, so the test
calls twice and additionally asserts the `schema_version` row is present
afterwards — that row's rollback is what armed the second failure. The stale
version (`UPDATE` branch) is a separate case and gets its own test: it is the
one that would bite an existing vault after a `SCHEMA_VERSION` bump.

### D3 — floor the subtraction, not the reported budget

The disease is `max_chars - 500` used as a size with no positivity guarantee. It
is not "the client reported a small number": a small budget is legitimate — the
smallest production value is `OllamaClient`'s low-RAM tier at 13,107 chars, and
a client on a small local model may honestly report less. Substituting the
60,000-char default for a truthfully-small value hands that model a prompt many
times its context; clamping up to a floor does the same thing more quietly.

A small batch budget is harmless: it makes more, smaller batches, and the count
stays proportional to the document. So `client_optimal_chunk_chars` keeps
returning what the client reports, and both subtraction sites floor their own
arithmetic:

- `knowledge_units.py`: `chunk_size=max(_MIN_SUBDIVISION_CHARS, max_chars - 500)`
- `graph_index.py`:     `statement[:max(_MIN_SUBDIVISION_CHARS, max_chars - 500)]`

`_MIN_SUBDIVISION_CHARS = 1000`, chosen so it exceeds the 500-char overlap and
`_chunk_text` still advances 500 chars per chunk. It lives in
`pipeline/chunking.py` beside the helper it corrects, so the two sites cannot
drift.

`graph_index.py:91` is included deliberately even though the report named only
`knowledge_units.py:348`. It is the identical expression; as a slice bound a
negative value silently amputates the tail of every long statement and then
labels the result `... [TRUNCATED]`, a truthfulness defect that no cost metric
would ever surface. Fixing one site and leaving the other is the workaround
pattern `CLAUDE.md` prohibits.

### D4 — `_chunk_text` rejects a non-positive `chunk_size`

`_chunk_text`'s forward-progress guard (`if next_start <= start: next_start =
start + 1`) is what manufactures the explosion: it converts an illegal size into
a one-character-per-chunk walk that never hangs, never raises and never logs —
it just spends. D3 stops today's callers from reaching it; D4 stops every future
one. A size argument that is zero or negative is a programming error and now
raises `ValueError` at the boundary instead of being absorbed.

This is the root-cause half of the fix. D3 alone would leave the trap armed for
the next caller.

## 5. Scope Exclusions & Stop Conditions

**Exclusions**

- `ingest_raw.py:1833`'s independent `getattr` read (see §2).
- Any behaviour change to `client_optimal_chunk_chars`'s return value.
- v0.59.0 job-progress work.

**Stop Conditions**

- **Stop** if the D1 commit turns any existing test red. That would mean some
  caller relies on schema setup rolling back with its own work, contradicting
  the `init_db` precedent, and the design needs re-deriving before proceeding.
- **Stop** if flooring the subdivision changes the outcome of any test that does
  not deliberately pass a tiny `optimal_chunk_chars`. That would mean the floor
  is engaging on production-sized budgets, i.e. the constant is wrong.
- **Stop** if `_chunk_text`'s new `ValueError` is reachable from any production
  path. It must be unreachable by construction after D3; if a real call site can
  trip it, that site has an unfixed instance of the same defect.

## 6. Evidence Ledger

Full ledger: `.agents/plans/07_latent_defect_fixes_evidence.md`. Summary of what
planning established:

- **Rollback anchor**: `0c0ebeb` (`master` tip). Worktree clean at branch
  creation; branch `fix/db-connect-commit-and-chunk-floor`.
- **Both defects reproduce on that commit** with the transcripts recorded in the
  briefing. The DB one reproduces on *both* `_stamp_schema_version` branches.
- **Neither user-facing entry point is currently broken, and that is an
  accident.** `wiki jobs run` (`commands/jobs.py:65`) and `IngestWorker.run`
  (`ingest_worker.py:516`) both call `db.recover_stale_jobs` *before*
  `claim_next_job`. `recover_stale_jobs` runs plain DML with no explicit
  `BEGIN`, so it joins the open implicit transaction harmlessly and commits the
  `schema_version` stamp at `yield`-exit. Verified: on a fresh DB
  `recover_stale_jobs` returns 0, leaves `schema_version = [(13,)]` committed,
  and the following `claim_next_job` succeeds. So the honest claim is that
  `db.claim_next_job` — a member of the public DB API surface asserted by
  `test_db_public_api.py` — is broken standalone, and the two in-repo callers
  are shielded by an incidental line ordering that nothing documents or
  enforces. Do **not** write a changelog entry claiming `wiki jobs run` was
  broken.
- **No schema change**, so no migration and no `SCHEMA_VERSION` bump.
- **Version reality**: all four manifests at `0.58.0`; spec titles on `v0.58.0`,
  which satisfies the `v0.61` line for `0.61.2`.
- **Concurrent work**: `feature/v0.59.0-job-progress` exists locally, unpushed,
  and touches the job path. It will need a rebase; `0.59.0 > 0.58.1`, so merge
  order does not create a version regression as long as v0.59.0 lands second.

## 7. Execution Phases (TDD and CI at each phase)

- **P0 — Measured baseline.** Reproduce both defects on `0c0ebeb` and record the
  exact transcripts, including the never-heals evidence
  (`schema_version rows: []`) and the 3,920-batch measurement. Read
  `commands/jobs.py` and `ingest_worker.py` to establish whether the user-facing
  paths are actually broken. *Done during planning; recorded in §6 and the
  evidence ledger.*
- **P1 — Contract specification.** SYSTEM_BEHAVIOR §6 gains the chunk-budget
  positivity rule beside the existing `optimal_chunk_chars` sentence, and §6 (or
  the nearest job-queue paragraph) gains the "a connection is handed to its
  caller outside any transaction" rule. Docs before code. No schema change, so
  no approval stop here.
- **P2 — Failing tests.** `test_db_schema.py`: fresh-DB double claim, stale
  version claim, enqueue-then-claim. `test_knowledge_unit_extraction.py`: tiny
  budget produces a proportional batch count. `test_v021_background_jobs.py` or
  the KU test file: `_chunk_text` raises on a non-positive size. All must fail
  against unmodified source. Verify: `scripts/backend-check pytest` shows the
  expected failures for the expected reasons.
- **P3 — Core logic.** D1 in `db/schema.py`; D3 in `pipeline/chunking.py`,
  `pipeline/knowledge_units.py`, `pipeline/graph_index.py`; D4 in
  `ingest_raw.py`. Verify: new tests pass, `ruff` and `mypy` clean, and the
  three `optimal_chars=160` tests pass unmodified.
- **P4 — Full suite.** `scripts/backend-check all`. Verify: no regressions
  anywhere, especially `test_db_public_api.py`, `test_compile_pipeline.py`,
  `test_entity_relation_extraction.py`, and `test_workspace_hygiene.py`.
  **Unplanned outcome, recorded here because it changes the phase's work:**
  `db/schema.py` is pinned by content hash in
  `docs/specs/failure_atlas/D2_HOLDOUT_RESULT.yml`, so the commit tripped the D2
  drift tripwire in two tests. Resolved by the re-arm procedure that file
  already establishes (eleven prior `*_rearm` records): record the prior hash,
  the date, and a mechanical non-impact argument, then update the hash. The
  holdout is NOT re-run and no new result is claimed — `run_count` stays 3 and
  every metric and frozen input is untouched. See evidence ledger §7.3a.
- **P5 — Testbed smoke.** `VAULT_ROOT=testbed wiki status` and
  `VAULT_ROOT=testbed wiki jobs list/run` against a testbed vault, exercising the
  claim path end to end. Verify: no `cannot start a transaction` anywhere and the
  queue drains or reports empty.
- **P6 — Release.** Bump all four manifests to `0.61.2`, write the `### Fixed`
  changelog entry, remove ROADMAP item 12, delete this plan and its evidence
  ledger, `chore(release): v0.61.2`, push, PR.
