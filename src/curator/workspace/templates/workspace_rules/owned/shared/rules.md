# incurator Shared Workspace Rules

These rules are the incurator contract for `{{project_name}}`.
Runtime-specific files must point back here instead of forking behavior.

## Workspace Scope

- Active workspace: `{{workspace_path}}`
- Wiki root: `{{wiki_root}}`
- `curate.yml`: `{{curate_yml_path}}`
- Keep searches, edits, and citations scoped to this workspace unless the human explicitly asks for a broader context.
- Do not mix evidence from unrelated workspaces or projects.

## Curator Usage

- Read `curate.yml` before searching.
- Prefer incurator MCP with `WORKSPACE_PATH={{workspace_path}}` when available.
- Start from L4 Exhibitions, then backtrack to Concepts, Atoms, and Contexts when provenance, confidence, or contradictions require it.
- If MCP is unavailable, use local workspace files only when they exist and say clearly when no local fallback is available.

## Knowledge Updates

- Do not edit `03_Notes/`, `04_Resources/`, or `06_Archives/` autonomously.
- If source truth appears wrong, ask the human before changing sources or generated Curator nodes.
- Promote workspace-derived knowledge to `02_Wiki/` only after explicit human consensus.
- After promotion or Curator-node correction, run or request `wiki add`, `wiki curate`, and `wiki sync` when practical.

## Evidence Discipline

- Do not invent citations, filenames, functions, experiments, or results.
- Mark unsupported claims as hypotheses or TODOs.
- Keep generated drafts separate from accepted workspace knowledge until the human approves them.

