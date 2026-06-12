# Problem Definition: Purge Legacy QMD References

## 1. What is the problem?
The `qmd` binary was officially retired in v0.3.2 in favor of DB-native search (FTS5 + vector + RRF + reranking). However, a `grep_search` reveals that over 50 references to `qmd` still exist in the active codebase (including `search.py`, `cli.py`, `lint.py`, `hatch_build.py`, and multiple tests).
This creates a critical risk: if we remove the strict "Do not use qmd" warnings from `AGENTS.md` and `CLAUDE.md`, AI agents may read the remaining legacy code and hallucinate that `qmd` is still an active dependency, leading to broken implementations.

## 2. Why is it happening?
The transition to DB-native search deprecated `qmd`, but a comprehensive codebase cleanup was not completed. Legacy checks, fallback paths, and documentation still refer to it.

## 3. Constraints & Success Criteria
- **Constraint 1:** Do not break the current DB-native search logic while removing `qmd` paths.
- **Constraint 2:** Test files (e.g., `tests/test_search_index_fallback.py`) must be updated or deleted if they specifically test the retired `qmd` fallback.
- **Success Criteria 1:** A full `grep_search` for `qmd` across the entire codebase (`src/`, `tests/`, `plugin/`, `scripts/`) returns 0 functional matches.
- **Success Criteria 2:** Once the purge is confirmed by CI and tests, the tombstone warning in `AGENTS.md` and `CLAUDE.md` is safely deleted in the final release commit.
