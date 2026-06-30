## Curator Knowledge Navigation

**Vault Topology**: You are working in a **Workspace** (`{{workspace_path}}`), which is connected to the **Vault Root** (`{{vault_root}}`).
- **Knowledge Sources**: Global folders (`02_Wiki/`, `03_Notes/`, `04_Resources/`) live at the Vault Root.
- **Rules for `curate.yml`**: All `sources.include/exclude` patterns MUST be relative to the **Vault Root**.
> [!CAUTION]
> **Workspace-source boundary**: Do not add local workspace folders or files to `sources.include` in `curate.yml`. Workspace-local material should be promoted to shared vault knowledge only after explicit human approval.


**Mandatory for every session in `{{workspace_path}}`:**

**Session start** — call `curator_check_workspace(workspace_path="{{workspace_path}}")`.

- If response has `needs_initialization: true`:
  Tell the user initialization is required. The response contains `instructions` and `current_step`.
  You MUST present the `current_step` question to the user and wait for their answer.
  Call `curator_workspace_init` again with the new answer plus any previously `provided_so_far` answers.
  Repeat this loop until initialization is complete.
  After init: follow the `recommended_next_steps` returned by the tool.

- If response reports incomplete graph processing:
  Ask the user whether to run `wiki build --wait` or continue with available evidence.

**Every domain query** — call `curator_query(question="<your query>", workspace_path="{{workspace_path}}")` BEFORE
searching local files, the web, or training knowledge.

- Use Curator results as the primary evidence source.
  Fall back to local files only if Curator returns nothing, and state clearly when falling back.

**Session end** — follow `.agents/curator/workflows/session_closeout.md`.

Full rules: `.agents/curator/shared/rules.md`
Runtime guidance: `.agents/curator/runtime/{{agent_runtime}}.md`
