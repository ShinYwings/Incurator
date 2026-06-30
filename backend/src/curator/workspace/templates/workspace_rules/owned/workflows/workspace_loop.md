---
description: Incurator workspace loop
---

# Workspace Loop

Use this workflow for all sessions inside `{{project_name}}`.

## 0. Session Start — Curator Sync (MANDATORY)

- **[Trigger]** New conversation session begins, or first domain question arrives.
- **[Constraint]** Do NOT respond to any domain query before completing this step.

### 0-A. Check workspace status
Call: `curator_check_workspace(workspace_path="{{workspace_path}}")`

### 0-B. Handle `needs_initialization: true`
Respond in the workspace's configured output language for every user-facing
message in this step (`curate.yml` → `prompts.output_language`; the default
`same_as_latest_request` means match the language of the user's most recent
message). Do not hard-code a language.

If the response contains `needs_initialization: true`:
1. Tell the user this workspace is not yet connected to Curator and needs initial setup.
2. Read the `instructions` in the response carefully.
3. Present the `current_step` question and its `suggestions` to the user.
4. Wait for their answer, then call `curator_workspace_init` again with the new answer and all previously `provided_so_far` answers.
5. Repeat this step-by-step interview loop until initialization completes.
6. After init succeeds, follow the `recommended_next_steps` returned by the tool (e.g. build, query, persona setup).
7. Tell the user initialization is complete, and how to configure the persona next (e.g. ask Curator to set up the workspace persona).

### 0-C. Handle incomplete graph processing
If curator_check_workspace reports incomplete graph processing:
- Ask the user whether to run `wiki build --wait` or continue with currently available evidence.

## 1. Knowledge Query

- **[Trigger]** User asks any question requiring domain knowledge.
- **[Action]** Call `curator_query(question="<your query>", workspace_path="{{workspace_path}}")` FIRST.
- **[Fallback]** Only if Curator returns no relevant results: search local workspace files.
- **[Constraint]** State clearly when falling back. Never silently skip Curator.

## 2. Work With Evidence

- Separate sourced claims, hypotheses, and unknowns explicitly.
- Keep local drafts inside the workspace until the human accepts them.
- Do not invent citations, file paths, or results.

## 3. Update The Graph

- Promote accepted knowledge to `02_Wiki/` only with explicit human consensus.
- After accepted changes, run or request `wiki add`, `wiki build`, and `wiki sync`.
- Leave ambiguous Curator repair items visible for review.

## 4. Persona Setup (on user request)

- **[Trigger]** User asks to configure or update the workspace persona.
- **[Action]** Ask: domain, goal, output_intent (researcher/engineer/learner), keywords.
- **[Action]** Call: `curator_update_artist_persona(workspace_path="{{workspace_path}}", request=<summary of answers>)`

## 5. Session End

- Follow `.agents/curator/workflows/session_closeout.md`.
