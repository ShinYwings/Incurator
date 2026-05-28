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
If the response contains `needs_initialization: true`:
1. Tell the user: *"이 워크스페이스가 아직 Curator에 연결되지 않았습니다. 초기 설정이 필요합니다."*
2. Read the `instructions` in the response carefully.
3. Present the `current_step` question and its `suggestions` to the user in Korean.
4. Wait for their answer, then call `curator_workspace_init` again with the new answer and all previously `provided_so_far` answers.
5. Repeat this step-by-step interview loop until initialization completes.
6. After init succeeds, follow the `recommended_next_steps` returned by the tool (e.g. curate, reindex, persona setup).
5. Tell the user: *"초기화 완료! 이제 페르소나를 설정하려면 'Curator 페르소나 설정해줘'라고 말씀해주세요."*

### 0-C. Handle `exhibition_exists: false`
If curator_check_workspace returns `ok: true` but `exhibition_exists: false`:
- Call `curator_curate_workspace(workspace_path="{{workspace_path}}")`
- Call `curator_reindex()`

## 1. Knowledge Query

- **[Trigger]** User asks any question requiring domain knowledge.
- **[Action]** Call `search_curator(query="<your query>", workspace_path="{{workspace_path}}")` FIRST.
- **[Handle `needs_curation: true`]** Call `curator_curate_workspace` → `curator_reindex` → retry search.
- **[Fallback]** Only if Curator returns no relevant results: search local workspace files.
- **[Constraint]** State clearly when falling back. Never silently skip Curator.

## 2. Work With Evidence

- Separate sourced claims, hypotheses, and unknowns explicitly.
- Keep local drafts inside the workspace until the human accepts them.
- Do not invent citations, file paths, or results.

## 3. Update The Graph

- Promote accepted knowledge to `02_Wiki/` only with explicit human consensus.
- After accepted changes, run or request `wiki add`, workspace curation, and `wiki sync`.
- Leave ambiguous Curator repair items visible for review.

## 4. Persona Setup (on user request)

- **[Trigger]** User asks to configure or update the workspace persona.
- **[Action]** Ask: domain, goal, exhibition_intent (researcher/engineer/learner), keywords.
- **[Action]** Call: `curator_update_artist_persona(workspace_path="{{workspace_path}}", request=<summary of answers>)`

## 5. Session End

- Follow `.agents/curator/workflows/session_closeout.md`.
