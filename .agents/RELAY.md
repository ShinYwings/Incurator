# RELAY — v0.48.4 shipped; formula recovery is the live goal

## Goal

Make the knowledge system actually serve real questions. The v0.43.0–v0.48.4
run closed the structural reasons it could not. What remains is the half of the
formula problem nothing has touched yet: ROADMAP item 1.

## Plan Reference

- Live queue: `.agents/ROADMAP.md`
- Knowledge-value Arena (4 inspectors, 2 critiques, synthesis, 4 raw evidence
  packs): `.agents/plans/knowledge_value_arena/`
- `.curator` state Arena: `.agents/plans/curator_state_arena/`
- System integrity milestone: `.agents/plans/03_system_integrity_consolidation.md`
  and its evidence ledger `03_b3_roadmap_evidence.md`

## Analysis And Reasoning

**Measure the artifact, not the code against the spec.** Every high-value
finding this run came that way, and in each case the code conformed:

- the ≥2 corroboration gate quarantining 99.3% of the graph (v0.43.0)
- `support_status='verified'` gating the search index, hiding 61% of live
  knowledge units (v0.47.0)
- ASCII-only route signals making L3/L4 unreachable in Korean (v0.47.0)
- a `runtime/jobs.json` frozen since 2026-07-04 that the sidebar still polled

**The jetski error, root-caused (2026-08-07).** Two hotfixes coded from the
symptom shipped no-ops before measuring the stored spans found it in one pass.
On source 37 — a 27-page paper added through Reference Mode, 643 spans,
ingested correctly:

- Every displayed equation is a **rasterized image**. The parser emits
  `**==> picture [W x H] intentionally omitted <==**` — 158 blocks across all
  27 pages; 95 spans are nothing but the placeholder.
- Spans containing `(24)`: 0. `(25)`: 0. `(26)`: 0. Page 4, which visibly
  renders equations (3) and (4), stores only the placeholder.
- `wiki plugin pdf search --source-id 37 --query "(26)"` → 0 hits. Not a
  window-width problem; the string was never ingested. That is why v0.48.1's
  distant-page locator could not have worked — it searched more of the same
  emptiness.

**Two separable defects. Do not conflate them.**

1. *The answer disappeared.* `buildResolvedReferencesBlock` returned `""` when
   nothing resolved, so the prompt named neither the target nor the failure and
   the model reached for a file-read tool headless auto-denies. **Shipped in
   v0.48.4.** PLUGIN_SCHEMA already required this; the implementation never did
   it.
2. *The equation is still missing.* Nothing repairs image-only formula loss.
   **This is the live goal.**

**Review caught a defect that made the v0.48.4 fix net-negative**, before
release. `resolveWithNearbyPageHints` relabels a *resolved* page reference
`method: "unresolved"` purely to suppress a duplicate render. Naming unresolved
references sent that flag into the prompt, so `(Section 11.1.2, p281)` quoted
page 281 verbatim *and* declared it absent, in one prompt. Fixed by splitting
the two meanings (`consumedBySibling`) rather than filtering downstream. Two
lessons worth keeping: a single state carrying two meanings is safe only while
one of them is never observed, and the trap was already documented in
`pdfReferenceContext.ts` — the comment was read after the bug, not before.

## Progress Status

Shipped this run: **v0.43.0 → v0.48.4**, 18 merged PRs.

- v0.43.0 corroboration gate · v0.44.0 B4 · v0.44.1 lint truthfulness ·
  v0.45.0 B3 P1–P4 · v0.46.0 vault move/delete tracking · v0.47.0 support gate
  + routing + lens + entity prompt · v0.48.0 English-internal boundary ·
  v0.48.1 distant-equation locator (a no-op; see above) · v0.48.2 sidechat job
  indicator · v0.48.3 add-source state + Zotero identity · v0.48.4 unresolved
  cross-reference block
- Local gates at HEAD: backend pytest 1456 passed / 6 skipped / 4 xfailed,
  Ruff clean, mypy clean (127 files), plugin Vitest 921/921 across 86 files,
  `tsc --noEmit` clean, spec/version sync at v0.48.4.
- Acceptance test on the real vault, the user's own question
  ("2D GS가 3D보다 …여러 논문을 종합해서 설명해줘"): route `local → global`,
  L4 `0 → 4`, L3 `0 → 10`.
- Search index: knowledge units `1,098 → 2,215` (+1,117).

## Critical Context / Blockers

- **The D2 frozen holdout is CONSUMED (`run_count: 3`). Never rerun it.** Its
  tripwire fires on any change to a fingerprinted file; the documented response
  is a written non-impact proof plus a hash re-arm. Done four times this run —
  see the `v04*_rearm` entries in `D2_HOLDOUT_RESULT.yml`. `procedure`,
  `queries`, and `frozen_inputs` must stay byte-identical; verify with a YAML
  comparison, do not assert it.
- **The plugin CAN compute the vault cache key.** `vaultMachineCacheDir()` in
  `plugin/src/utils/machineCache.ts` computes `sha256(canonicalPath(root))
  .slice(0,16)`, mirroring the backend's `get_vault_cache_dir`. An earlier
  relay entry claimed the opposite and recommended shelling out to
  `wiki status --json` instead; that was wrong, and v0.48.2 shipped the direct
  read via `plugin.readRuntimeJson("jobs")`.
- `recover_formula()` / `classify_formula_loss()` are fully implemented and
  specified (§26.2) with **zero production call sites** and 14 test call sites.
  `classify_formula_loss` returns `image_only` for exactly the source-37 case
  and is never invoked. The evidence it needs is already in the DB: the
  placeholder spans carry page number and image dimensions.
- Retrieval costs one model call up front to derive the English search query.
  With a CLI provider at 8–12 s that is real. If it bites, cache the derivation
  by message hash; do not revert the boundary.
- The LLM router `curator.query_router` is registered and unwired. Deterministic
  signals cover the documented languages first per §17; wiring it needs a client
  threaded through the routing call chain.
- Runtime venv is `<repo>/.venv`; dev/validation is `<repo>/.venv-dev` via
  `scripts/backend-check`. Never create `backend/.venv` or backend-local caches.
- `curate.yml` exists ONLY in `01_Workspaces/<project>/`. Vault-scoped config is
  `.curator/settings.yml`.

## Immediate Next Action

**ROADMAP item 1 — wire formula recovery.** Needs an Arena plan, not a third
hot-patch; the two previous attempts at this bug both coded from the symptom
and shipped no-ops. The plan must decide:

- where in ingest `classify_formula_loss` is called (`rendered_formula_present`
  comes free from the placeholder, with bbox and page number)
- what `recover_formula` uses as provider input when the equation is image-only
  and there is no text to repair from
- whether recovery is a re-ingest pass or a repair pass over existing spans,
  and what invalidates a recovery (`invalidate_formula_recoveries` exists)

Still open after that: B3 P5–P7, B2, and B5/B7 which each need their own Arena
plan, plus the `.curator` state items (silent empty vault, vault rename,
`sessions.json` bloat, journal compaction, `wiki sync` false rebuild claims).
