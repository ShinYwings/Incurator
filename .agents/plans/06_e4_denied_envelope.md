# v0.82.5 Master Implementation Plan

Date: 2026-09-11
Status: APPROVED — two independent proposals and cross-critiques synthesized from live evidence.

## 1. Objective
Normalize agy 1.2.0 exit-zero SUCCESS envelopes with denied_actions and no answer into provider errors, so the existing graph batch retry handles the refusal. Done means exact-envelope regressions, live extraction/denial checks, local checks, review and CI pass, then merge.

## 2. Explicit Non-Goals
No permission expansion, no provider rerouting, no prompt/schema changes, no retry budget changes, no user-vault rebuild or migration. Broader retry taxonomy is a separate issue.

## 3. Strict Quality Conditions & Release Gates
- Two denied envelopes then a valid graph retry the original prompt three times, without JSON repair.
- Only validated batches enter cache; earlier completed batches survive exhaustion and resume.
- Recovered output and legitimate empty structured results remain accepted by existing validation.
- Explicit ERROR envelopes cannot return successful payloads, regardless of exit code.
- Existing capacity cooldown and OS sandbox stay enforced.
- Exact live contract, harmless forced-command probe, all backend/plugin gates, required code-review skill, green CI.

## 4. Locked Design Decisions (Arena Consensus)
Correct the provider boundary in llm.py; retain AntigravityCliError and existing graph loop. Detect no-answer denial using native denied_actions, not arbitrary log prose. Preserve present structured results (including empty arrays) and usable response text. Explicit provider ERROR takes precedence over payload. Correct claims that schema/one turn guarantees no tools. See agy_shell_out_arena/05_* and 06_* for domain analyses, pseudocode and cross-critique.

## 5. Scope Exclusions & Stop Conditions
No reduction in tool capability or changed routing. Stop before any user-data migration or reindex. Report live/provider/review blockers honestly; do not equate simulated execution with live validation.

## 6. Evidence Ledger
See 06_e4_roadmap_evidence.md. Base ce854940, current release 0.82.4. Only pre-existing dirty item is the user's untracked E4 draft. No DB/schema change and no rollback of user data needed.

## 7. Execution Phases
- P0: Reconcile stale draft with current retry/resume, measure real graph and denied envelopes (done).
- P1: Update English specs/guides then Korean guide; preserve extraction contract v2.
- P2: Write failing provider and full adapter-to-graph regressions.
- P3: Normalize result errors before unwrapping; run targeted tests and Ruff.
- P4: Replay captured live graph/denial envelopes through isolated graph DB. Per user correction, remove login-triggering pytest live calls and the provider guard opt-out; no further real agy invocations.
- P5: Full checks, patch manifests/changelog, PR and code-review skill, CI, merge, prune, refresh relay. Delete completed master plan; keep evidence in Git.
