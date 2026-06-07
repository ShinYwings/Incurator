---
description: Research-session logging workflow
---

# Daily Research Log

Use this workflow when a research session ends or when the researcher asks for a status digest.

1. Ensure `Research Notes/` exists.
2. Create or update `Research Notes/YYYY-MM-DD.md` with:
   - the question studied,
   - evidence checked,
   - accepted conclusions,
   - rejected assumptions,
   - open problems.
3. Refresh `research_digest.md` with only stable conclusions that should guide future work.
4. Add unresolved derivations, experiments, or paper-reading tasks to `todo_list.md`.
5. If files changed in `02_Wiki/`, run the workspace curator flow before treating the knowledge graph as current.
6. Keep system workflow changes inside `.agents/` or `.antigravity/`, never in the research notes.
