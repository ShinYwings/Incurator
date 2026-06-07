# incurator Shared Workspace Rules

These rules are the incurator contract for `{{project_name}}`.
Runtime-specific files must point back here instead of forking behavior.

## Workspace Scope

- Active workspace: `{{workspace_path}}`
- Wiki root: `{{wiki_root}}`
- `curate.yml`: `{{curate_yml_path}}`
- Do not use cross-workspace paths or mix results with external projects.
- Restrict knowledge extraction, graph search, and insertion commands strictly
  to this workspace's local DAG.
- Treat repo-local `testbed/` validation as fixture validation unless it is the
  same path as the active workspace.

## Research Flow

1. Read `curate.yml` before searching.
2. If incurator MCP is available, search with `WORKSPACE_PATH` scoped to this
   workspace and start from L4 Exhibitions.
3. Backtrack Exhibition -> Concept -> Atom -> Context when confidence is low,
   provenance is needed, or contradictions appear.
4. Use local files only when they exist in this workspace; otherwise report that
   no local fallback is available.
5. Keep methodology claims separate from exploratory notes until the researcher
   explicitly accepts them.

## Knowledge Updates

- Do not edit `03_Notes/` autonomously.
- If a source-truth error is found, ask the researcher before changing sources
  or derived Curator nodes.
- Promote project-derived knowledge to `02_Wiki/` only after explicit human
  consensus.
- After promotion or correction, run or request `wiki add`,
  workspace-scoped curation, and `wiki sync` when practical.

## Citation Discipline

- Prefer stable bracket citations from `Papers/paper_index.md` when available.
- If a citation is missing, add a TODO in `todo_list.md` instead of inventing a
  reference number.
- Do not invent file names, functions, papers, experiments, or results.
