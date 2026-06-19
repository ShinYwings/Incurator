# Problem Definition: Purge Legacy QMD References

Date: 2026-06-20

## Briefing

The external `qmd` binary was retired in v0.3.2 and replaced by DB-native search
inside `state.sqlite` using FTS5, chunk vectors, RRF fusion, reranking, and query
traces. Active repository files still contain many legacy `qmd` references in
backend code, MCP status payloads, plugin fallbacks, install scripts, tests, and
documentation.

## Current Baseline

- Branch: `fix/purge-legacy-qmd-references`
- Active plans before this work: none.
- Measured matches: `rg -i -n "qmd" backend/src backend/tests plugin scripts docs/guides docs/specs AGENTS.md CLAUDE.md .agents/drafts/purge_qmd_legacy.md .agents/ROADMAP.md .agents/RELAY.md | wc -l` -> 202.
- High-risk files include:
  - `scripts/build/hatch_build.py` still installs `@tobilu/qmd`.
  - `backend/src/curator/mcp_server.py` describes and returns `qmd_*` readiness.
  - `backend/src/curator/runtime_state.py` returns `qmd_*` compatibility keys.
  - `plugin/main.ts` and `plugin/src/ui/incuratorDashboardModal.ts` still fall
    back to `qmd_*`.
  - `backend/src/curator/cli.py` has `_refresh_qmd_index` and user-facing
    `qmd` strings.
  - `backend/src/curator/retrieval/query_expander.py` uses qmd names for its
    structured expansion parser.

## Success Criteria

- No active runtime/build path shells out to, installs, configures, or reports an
  external qmd binary.
- Backend status/MCP status expose DB-native `search_*` keys only.
- Plugin status UI consumes `search_*` keys only and uses search-oriented naming.
- Tests enforce the purge without themselves reintroducing literal legacy terms
  in active source/test/plugin/script files.
- Search/query behavior still validates through backend and plugin tests.

