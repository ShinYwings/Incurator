# RELAY — v0.48.1 shipped; knowledge-value audit findings are the live queue

## Goal

Make the knowledge system actually serve real questions. The v0.43.0–v0.48.1
run closed the structural reasons it could not; what remains is queued in
`.agents/ROADMAP.md` items 2 and 3.

## Plan Reference

- Live queue: `.agents/ROADMAP.md`
- Knowledge-value Arena (4 inspectors, 2 critiques, synthesis, 4 raw evidence
  packs): `.agents/plans/knowledge_value_arena/`
- `.curator` state Arena: `.agents/plans/curator_state_arena/`
- System integrity milestone: `.agents/plans/03_system_integrity_consolidation.md`
  and its evidence ledger `03_b3_roadmap_evidence.md`

## Analysis And Reasoning

**The method that works is measuring the real vault, not auditing code against
specs.** Every high-value finding this run came that way, and the two Arenas
that started from artifacts found things a conformance review structurally
cannot — because in each case the code conformed:

- the ≥2 corroboration gate quarantining 99.3% of the graph (v0.43.0)
- `support_status='verified'` gating the search index, hiding 61% of live
  knowledge units (v0.47.0)
- ASCII-only route signals making L3/L4 unreachable in Korean (v0.47.0)
- a `runtime/jobs.json` frozen since 2026-07-04 that the sidebar still polls

**Two corrections the user made that changed the design**, both recorded because
they generalize:

1. **Internals are English, without exception.** v0.47.0 first made Korean
   questions work by teaching the route signals Korean/CJK/Cyrillic. That was
   backwards: it made the internals multilingual when the contract
   (USER_GUIDE: "using English only as the internal search/reasoning language")
   says only input/output carry the user's language. v0.48.0 reverted that and
   fixed the boundary instead — `english_query` was simply never populated.
2. **An invariant with no exceptions cannot be a caller-supplied parameter.**
   The `--english-query` flag was removed; `fetch_context` derives it. A caller
   that forgets a flag degrades silently, which was the original bug.

**And the derivation is extraction, not translation.** "이 문장을 한글로 번역해줘:
<body>" translated into English becomes an English sentence asking for a Korean
translation, which would then be routed and BM25-matched as a vault question.
`curator.query_search_terms` extracts a short English search query instead and
returns `is_knowledge_question=false` when there is nothing to look up —
decided by reading intent, never by matching trigger words.

## Progress Status

Shipped this run: **v0.43.0 → v0.48.1**, 16 merged PRs.

- v0.43.0 corroboration gate · v0.44.0 B4 · v0.44.1 lint truthfulness ·
  v0.45.0 B3 P1–P4 · v0.46.0 vault move/delete tracking · v0.47.0 support
  gate + routing + lens + entity prompt · v0.48.0 English-internal boundary ·
  v0.48.1 distant-equation hotfix
- Local gates at HEAD: backend pytest 1456 passed / 6 skipped / 4 xfailed,
  Ruff clean, mypy clean (127 files), plugin Vitest 911/911 across 86 files,
  `tsc --noEmit` clean, spec/version sync at v0.48.1.
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
- **Highest-value open item is the dead status file** (ROADMAP item 3): the chat
  sidebar polls `<vault>/.curator/runtime/jobs.json`, frozen at 2026-07-04
  saying `idle: true`, while the live file says `running: 1`. This is the user's
  own "build indicator appears then stops" report. Fix by calling
  `wiki status --json` as `incuratorDashboardModal` already does — **not** by
  correcting the path, because the plugin cannot compute the vault cache key.
- Retrieval now costs one model call up front to derive the search query. With
  a CLI provider at 8–12 s that is real. If it bites, cache the derivation by
  message hash; do not revert the boundary.
- `recover_formula()` / `classify_formula_loss()` are fully implemented and
  specified (§26.2) with **zero production call sites** and 14 test call sites.
  Wiring them is a separate item from the indexing gate that v0.47.0 fixed.
- The LLM router `curator.query_router` is registered and unwired. Deterministic
  signals cover the documented languages first per §17; wiring it needs a client
  threaded through the routing call chain.
- Runtime venv is `<repo>/.venv`; dev/validation is `<repo>/.venv-dev` via
  `scripts/backend-check`. Never create `backend/.venv` or backend-local caches.
- `curate.yml` exists ONLY in `01_Workspaces/<project>/`. Vault-scoped config is
  `.curator/settings.yml`.

## Immediate Next Action

ROADMAP item 3, in the synthesis's stated order: the dead `runtime/jobs.json`
first (only finding with a symptom the user has already hit, small
self-contained fix), then the silent-empty-vault guard, then `sessions.json`
bloat (15 MB, 81% re-embedded context, ~1.1 s per send), then sync-journal
compaction (24 MB, gzip measured at 9.86× and unused).

Still open in the integrity milestone: B3 P5–P7, B2, and B5/B7 which each need
their own Arena plan.
