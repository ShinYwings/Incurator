## Curator Knowledge Navigation

**Vault Topology**: You are working in a **Workspace** (`{{workspace_path}}`), which is a sub-directory of the **Vault Root** (`{{vault_root}}`).
- **Knowledge Sources**: Global folders (`02_Wiki/`, `03_Notes/`, `04_Resources/`) live at the Vault Root.
- **Rules for `curate.yml`**: All `sources.include/exclude` patterns MUST be relative to the **Vault Root**.
> [!CAUTION]
> **CRITICAL PROHIBITION**: NEVER add local workspace files, folders, or patterns (e.g., `01_Workspaces/**`, `Papers/`, `methodology.md`) to `sources.include` in `curate.yml`. Including local project data in the global Curator DAG is a severe architecture violation. Local data must only be "promoted" to `02_Wiki/` before being curated.


**Mandatory for every session in `{{workspace_path}}`:**

**Session start** — call `curator_check_workspace(workspace_path="{{workspace_path}}")`.

- If response has `needs_initialization: true`:
  Tell the user initialization is required. The response contains `instructions` and `current_step`.
  You MUST present the `current_step` question to the user and wait for their answer.
  Call `curator_workspace_init` again with the new answer plus any previously `provided_so_far` answers.
  Repeat this loop until initialization is complete.
  After init: follow the `recommended_next_steps` returned by the tool.

- If response has `exhibition_exists: false`:
  Call `curator_curate_workspace(workspace_path="{{workspace_path}}")` then `curator_reindex()`.

**Every domain query** — call `search_curator(query="<your query>", workspace_path="{{workspace_path}}")` BEFORE
searching local files, the web, or training knowledge.

- If response has `needs_curation: true`:
  Call `curator_curate_workspace` → `curator_reindex` → retry search.

- Use Curator results as the primary evidence source.
  Fall back to local files only if Curator returns nothing, and state clearly when falling back.

**Session end** — follow `.agents/curator/workflows/session_closeout.md`.

Full rules: `.agents/curator/shared/rules.md`
Runtime guidance: `.agents/curator/runtime/{{agent_runtime}}.md`
