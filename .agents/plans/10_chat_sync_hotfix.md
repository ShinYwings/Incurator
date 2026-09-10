# v0.82.0 Master Implementation Plan

Date: 2026-09-10
Status: APPROVED — Arena debate concluded for P1/P2/P4; P3 runtime enforcement remains subject to live probe evidence.

## 1. Objective
Ship the user's five urgent fixes before any roadmap work: remove avoidable answer preparation waits, expose sidechat automatic knowledge on/off and remove Plan, preserve complete Codex edit proposals, refresh verified CLI models, and make valid source-deletion audit snapshots import safely across devices. Diagnose and correct Antigravity denied-shell and 300-second buffered answer behavior with a measured native runtime contract.

## 2. Explicit Non-Goals
No roadmap E4 graph extraction changes, live vault mutation, source deletion, database migration/reindex, snapshot file patching, blanket permission bypass, provider swapping, guessed edit patches or automatic note acceptance.

## 3. Strict Quality Conditions & Release Gates
- Valid source removal→export→fresh-peer import preserves retained audit records and passes repeatedly; legacy missing source 32 fixture imports without binding to unrelated local IDs. Active orphan corruption still fails atomically.
- Sidechat off performs no automatic stored-knowledge fetch; explicit context survives. Enabled evidence overlaps document preparation with unchanged evidence ordering. Popover retains deadline/cache semantics.
- Independent Codex progress/final messages preserve intact final edit fences; no duplicated proposal from output-file recovery. Canonical diff target resolves correctly.
- agy live stream probe demonstrates real deltas, tool status, timeout partial preservation; no unsupported flag or unverified tool enforcement claims. Native denied-shell prevention requires actual tool-selection evidence.
- Current models/efforts/defaults agree backend/plugin; Gemini 3.5 absent and saved plugin choice normalizes through existing load path.
- Relevant failing tests before implementation, English then Korean docs, full pytest/ruff/mypy/vitest/TypeScript and testbed checks. Invoke installed code-review skill on PR, resolve findings, green CI before merge.

## 4. Locked Design Decisions (Arena Consensus)
- Parallelize only independent backend/document reads with immediate rejection handling and captured turn identity; no concurrent shared LLMClient image mutation. Knowledge switch controls automatic prior-knowledge consultation, default on; explicit/manual references remain available.
- Remove Plan prompt and typed setting, not just composer UI. Old stored extra key has no effect.
- Codex stream accumulation respects item identity; final file reconciles complete final text. Review/Accept remains note write boundary.
- Source deletion preserves retired knowledge_units and discarded compiler_generations, detaches their nullable source_id after graph reconciliation in the same transaction. Narrow historical terminal-orphan normalization belongs in common transport semantics, including importer/exporter; live unresolved parents still reject. No source reconstruction or dropping audit rows.
- Static shared catalogue: Gemini 3.8 Flash default, GPT-6 Astra default, add Claude Fable 5.1 while retaining Opus 5 default. Use installed CLI context/effort values, not public API context assumptions.
- Antigravity stream-json replaces buffered text only after observed event schema. Custom-agent tools must be behaviorally probed before claiming shell exclusion; preserve research tools needed by user's section/notes comparison.

## 5. Scope Exclusions & Stop Conditions
- Exclusions: E4 draft and all unrelated roadmap items remain paused.
- Stop conditions: live user data repair/deletion/migration, unresolved product capability trade, unverified runtime tool containment. Do not call the release complete with unresolved user behavior; record exact blockers.

## 6. Evidence Ledger
- Current repository/schema: base b4b8721, release 0.81.0, schema 14; nullable terminal audit source_id already supported, no schema change required.
- Dirty worktree at start: only untracked `.agents/drafts/e4_agy_shell_out.md`, preserved.
- Rollback: additive revert of release commits; no production DB changes. Details in `10_hotfix_evidence.md`.
- Arena: `hotfix_chat_arena/A_latency.md`, `B_provider_edit.md`, `C_linux_sync.md`, `D_models.md`, independent critiques and root critique. P3 probe findings amend domain document before coding native policy.

## 7. Execution Phases (Follow TDD and CI at each phase)
- Review amendment F: preserve same-request evidence readiness past the deadline;
  gate agy success on a valid final result; preserve caller cancellation;
  ignore auth substrings in successful native answers. Independent cross-critique
  and exact edge cases are in `hotfix_chat_arena/F_review_followup.md`.
  Claude verification was explicitly waived by the user on 2026-09-11;
  Codex adversarial review and CI remain release gates.
- **P0 — Research & Measured Baseline:** isolated sync import reproduced exact user source_id 32 failure; native CLI model lists verified; actual agy stream/custom agent probes and timing fixture.
- **P1 — Contract Specification:** domain-specific guide/spec updates before code, English then KR. No stored schema change or live migration.
- **P2 — Source lifecycle + transport:** source removal, legacy terminal orphan import/export, atomic failure tests; targeted pytest and ruff.
- **P3 — Provider runtime:** Codex stream/diff tests; agy native event parser and measured safe agent policy; targeted vitest and typecheck.
  Preserve each caller's response format: the shared agy invocation policy must
  not force Sidechat edit fences into inline plain-text replacements or JSON
  completion tasks. Sidechat's own supplied edit contract remains authoritative.
- **P4 — Context preparation + catalogue:** deferred scheduling/toggle/Plan tests and model catalogue/default tests; implement minimal matching code.
- **P5 — Testbed Smoke and Release:** existing complex_math_backprop/ResNet testbed, no production writes; full checks, review skill, version/spec title/changelog sync, push PR/CI/merge, delete implemented plan and prune finished branch. Resume no roadmap item in this task.
