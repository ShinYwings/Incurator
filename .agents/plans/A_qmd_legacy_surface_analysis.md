# Domain Analysis: Legacy QMD Surface

Date: 2026-06-20

## Design Constraints From Codebase

- Search is already DB-native in `backend/src/curator/search.py` and
  `backend/src/curator/retrieval/`.
- Runtime status is produced by `backend/src/curator/runtime_state.py` and read
  by plugin dashboard/status code.
- MCP status duplicates some runtime status fields in
  `backend/src/curator/mcp_server.py`.
- `scripts/build/hatch_build.py` still installs the retired external search
  binary and must stop doing so.
- Tests patch `_refresh_qmd_index`; renaming the function requires updating those
  tests.

## Docs/Specs Invariants

- `docs/specs/search_engine/SEARCH_ENGINE_SCHEMA.md` says search state lives in
  `.curator/state.sqlite`.
- `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md` says retrieval is DB-native and
  durable query traces are first-class records.
- `AGENTS.md` and `CLAUDE.md` must remain synchronized if agent rules change.

## Alternatives & Trade-Offs

- Keep compatibility keys and only rename comments: lowest risk but leaves active
  misleading API fields.
- Remove all compatibility keys now: cleaner and consistent with current plugin
  `search_*` support, but a minor public contract cleanup.
- Delete all historical benchmark evidence: satisfies broad grep goals, but
  destroys useful migration evidence.

## Final Decision

Remove active runtime/build/API references and compatibility keys now. Preserve
or rewrite historical benchmark material only as needed after active source,
tests, plugin, scripts, guides, specs, and agent rules are clean.

## Implementation Pseudocode

```text
add guard tests:
  forbidden = "q" + "md"
  scan backend/src, backend/tests, plugin, scripts/build, docs/guides, docs/specs,
       AGENTS.md, CLAUDE.md
  fail unless allowlisted historical references are outside active functional scope

rename backend helpers:
  _refresh_qmd_index -> _refresh_search_index
  update tests and user strings

status API:
  remove qmd_* keys from runtime_state and mcp_server
  plugin reads search_ready/search_version/search_engine only

query expander:
  _QMD_GRAMMAR -> _STRUCTURED_EXPANSION_GRAMMAR
  _parse_qmd_lines -> _parse_structured_expansion_lines
  tests renamed accordingly

build:
  remove qmd installer and qmd-specific requirements from hatch build hook
```

