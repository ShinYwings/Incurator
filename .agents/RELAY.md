# RELAY — v0.50.0 shipped; B2 sync integrity is the live goal

## Goal

Make the knowledge system actually serve real questions. The jetski bug — a
question about an equation that returned no answer at all — is now half closed:
the system says which region it could not read and why. It still cannot read it.
That half is ROADMAP item 1, and it is blocked on three concrete prerequisites,
not on a plan.

## Plan Reference

- Live queue: `.agents/ROADMAP.md`
- **Formula Arena** (4 proposals, red-team critique, 2 convener amendments):
  `.agents/plans/formula_recovery_arena/` — the three recovery blockers are
  established there with file:line evidence. Read `02_critique_redteam.md`
  before planning recovery.
- Knowledge-value Arena: `.agents/plans/knowledge_value_arena/`
- `.curator` state Arena: `.agents/plans/curator_state_arena/`
- System integrity milestone: `.agents/plans/03_system_integrity_consolidation.md`

## Analysis And Reasoning

**Measure the artifact, not the code against the spec.** Every high-value
finding this run came that way, and in each case the code conformed.

**The jetski bug, root-caused.** Two hotfixes coded from the symptom shipped
no-ops before measuring the stored spans found it in one pass. Source 37
renders every displayed equation as a rasterized image: 158 discarded picture
blocks across 27 pages, 95 spans that are nothing but the placeholder, and
**zero** spans containing `(24)`, `(25)`, or `(26)`. v0.48.1's page locator
could not have worked — it searched more of the same emptiness.

**Two separable defects, and only one is closed.**

1. *The answer disappeared* — the prompt named neither the target nor the
   failure, so the model reached for a file-read tool headless auto-denies.
   Shipped v0.48.4.
2. *The equation is still missing* — v0.49.0/.1 made the loss visible
   (130 regions across 4 sources on the reporting vault). Recovery remains
   unbuilt, deliberately: the Arena measured it at 0–2 of ~48 regions today.

**The Arena overturned its own briefing twice, and the red team then killed the
route the briefing was built around.** That is the process working. Two
corrections worth keeping:

- The two formula-loss populations are disjoint by *citation* but adjacent by
  *document order* — 159/480 vault-wide. The owning claim already exists; what
  `recover_formula` lacks is a `span_id`, not a `unit_id`.
- `ingest_raw.py:1094` was not a preview-only helper. For a
  `source_text_policy: on_demand` source that preview IS the CTX body the
  plugin reads, so the placeholder was being erased from the one surface a
  reader sees.

**Review caught defects in both shipped PRs.** v0.48.4's first cut declared a
page absent while quoting it (a single state carrying two meanings, safe only
while one was never observed). v0.49.0's sync fix was applied at two sites and
missed four, two of them on the default `wiki db import` path. Both were fixed
by removing the ambiguity rather than patching the symptom — `consumedBySibling`
and `row_revision()` respectively.

## Progress Status

Shipped this run: **v0.43.0 → v0.50.0**, 24 merged PRs.

- Local gates at HEAD: backend pytest 1504 passed / 6 skipped / 4 xfailed,
  Ruff clean, mypy clean (127 files), plugin Vitest 923/923 across 86 files,
  `tsc --noEmit` clean, spec/version sync at v0.50.0.
- Acceptance test on the real vault, the user's own question
  ("2D GS가 3D보다 …여러 논문을 종합해서 설명해줘"): route `local → global`,
  L4 `0 → 4`, L3 `0 → 10`.
- Search index: knowledge units `1,098 → 2,215` (+1,117).
- `wiki lint` now reports 130 unreadable regions across 4 sources that were
  previously invisible.

## Critical Context / Blockers

- **The D2 frozen holdout is CONSUMED (`run_count: 3`). Never rerun it.** Its
  tripwire fires on any change to a fingerprinted file; the documented response
  is a written non-impact proof plus a hash re-arm. `procedure`, `queries`, and
  `frozen_inputs` must stay byte-identical; verify with a YAML comparison, do
  not assert it.
- **The plugin CAN compute the vault cache key.** `vaultMachineCacheDir()` in
  `plugin/src/utils/machineCache.ts` mirrors the backend's
  `get_vault_cache_dir`. An earlier relay entry claimed the opposite.
- **`row_revision()` is the ONLY way to rank two versions of a row.** Reading
  `_UPDATED_AT_COL` directly is how v0.49.0 shipped four unfixed sites, two on
  the default import path. `source_spans` has no `updated_at` and its
  `created_at` is immutable, so its clock is derived from `metadata`.
- **There are zero `ALTER TABLE` statements in the backend** (removed in
  `f8b40be`). Editing `SCHEMA_SQL` never reaches an existing vault, so any
  schema idea must work without a new column or accept a full re-ingest.
- **An import must separate three outcomes**: stored, already present under
  another identity, refused. Classification asks the schema which UNIQUE index
  collided and must mirror SQLite — NULLs are DISTINCT, a partial index applies
  only to matching rows. When undecidable, report refused: over-reporting a loss
  is recoverable, under-reporting one is silence.
- **Do not reach for `wiki add --force` to retrofit data.** It sets
  `l2_status='pending'`, which the next default `wiki build` picks up as a full
  L2/L3 rebuild of every source.
- Retrieval costs one model call up front to derive the English search query.
  If it bites, cache by message hash; do not revert the boundary.
- Runtime venv is `<repo>/.venv`; dev/validation is `<repo>/.venv-dev` via
  `scripts/backend-check`.
- `curate.yml` exists ONLY in `01_Workspaces/<project>/`. Vault-scoped config is
  `.curator/settings.yml`.

## Immediate Next Action

**B2 is three-fifths done; finish it.** Remaining: **sync_db-2**
(`sources_set_sync_key` no-op trigger) and **sync_db-4** (locked device-state
RMW). Then B2 — the milestone's last P1 — closes.

Landed: CAND-03 conflict-archive EXDEV (v0.49.2), sync_db-3 export-stamp race
(v0.49.3), sync_db-1 truthful import outcome (v0.50.0).

**Method that keeps working, stated plainly because it keeps being re-proven:**
the plan names the item; measuring the running code finds what is actually wrong
with it. All three B2 items shipped that way, and in each case the defect was
not what the plan's one-line description implied.

**Method that keeps failing:** shipping a fix without a test verified to fail
without it. Every review round on #139 found a real hole in the previous round's
fix, and each hole failed toward silence — a lost row reported as skipped. The
rounds only became productive once every new behavior had a revert-verified
test. Do that first, not after review asks.

After B2: B3 P5–P7, then the `.curator` state items (ROADMAP item 4). B5/B7 each
need their own Arena. ROADMAP item 1 (formula recovery) stays blocked on three
prerequisites — do not plan it as if `recover_formula()` can be called today.
