# RELAY — RELEASE READY

## Goal

Publish v0.38.0 Sidechat Vault-Page Wikilinks after verified implementation and
navigation smoke tests.

## Plan Reference

- Umbrella: `.agents/plans/01_system_stability_overhaul.md`
- Evidence: `.agents/plans/01_roadmap_evidence.md`
- Current branch: `release/v0.38.0`
- Completed slice plan/evidence: preserved in Git history and removed from the
  active workspace per release workflow.

## Analysis & Reasoning

- v0.17.0 already made hidden Curator DAG links clickable. Reimplementing that
  path would duplicate shipped behavior and would not meet the user's goal.
- Ordinary internal links are already left to Obsidian's native renderer. The
  missing boundary is answer generation: the shared Sidechat prompt does not
  require wikilinks, pinned context can lose its exact path, and the provider
  formatter omits existing ContextService locators.
- The minimal design exposes only grounded paths already present in current
  context/evidence/tool output. It does not inject a whole-vault inventory and
  does not auto-link plain answer text after generation.
- Weak-provider smoke testing showed that supplying raw path fragments invited
  reconstruction errors. Safe context now carries one completed
  `vault_link_target` literal, while malformed and external identities fail
  closed.

## Progress Status

- v0.37.1 merged in PR #99; `master` and the worktree were clean.
- `release/v0.38.0` was created from commit `979bfe41`.
- Repository/docs/history audit and official Obsidian API research are complete.
- Existing F9 baseline and 31 focused plugin link/prompt tests pass.
- Arena, domain analyses, Master Plan, and evidence ledger are complete.
- The approved plan was implemented through docs-first TDD and incremental
  commits. Completed slice plans are deleted from the live workspace.
- Antigravity at effort Low and local Ollama returned exact supplied wikilinks.
- Real Obsidian native navigation opened an exact block and an exact heading.
- Validation passes: backend `1325 passed, 6 skipped, 5 xfailed`; plugin
  `68 files / 737 tests`; Ruff; Mypy; production build; 10 spec-sync tests; and
  zero-vulnerability `npm audit`.

## Critical Context / Blockers

- Treat Sidechat answer navigation and Failure Atlas F9 authored-note topology
  as separate workstreams.
- Never invent a vault page or send the full vault note inventory to a provider.
- Preserve native link behavior, modifier-click, hover, PDF navigation, hidden
  Curator DAG rewriting, and edit-loop phase markers.
- No DB schema or backend API change is planned.
- Desktop accessibility automation could not dispatch Sidechat's Send button;
  provider output and native rendered-link navigation were validated
  independently. This is not a product blocker.

## Immediate Next Action

Monitor the v0.38.0 release PR through checks and review. After the user merges
it, fast-forward `master` and apply the documented IDLE relay cleanup.
