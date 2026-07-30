# RELAY — ACTIVE

## Goal

Implement v0.38.0 Sidechat Vault-Page Wikilinks so an Obsidian Agent answer can
cite a known existing vault note as a real `[[wikilink]]` and clicking it opens
the exact page, heading, or block.

## Plan Reference

- Umbrella: `.agents/plans/01_system_stability_overhaul.md`
- Evidence: `.agents/plans/01_roadmap_evidence.md`
- Current branch: `release/v0.38.0`
- Slice plan: `.agents/plans/02_sidechat_vault_wikilinks.md`
- Slice evidence: `.agents/plans/02_sidechat_vault_wikilinks_evidence.md`
- Arena: `.agents/plans/sidechat_vault_wikilinks_arena/`

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

## Progress Status

- v0.37.1 merged in PR #99; `master` and the worktree were clean.
- `release/v0.38.0` was created from commit `979bfe41`.
- Repository/docs/history audit and official Obsidian API research are complete.
- Existing F9 baseline and 31 focused plugin link/prompt tests pass.
- Arena, domain analyses, Master Plan, and evidence ledger are complete.
- No application code has changed.

## Critical Context / Blockers

- Treat Sidechat answer navigation and Failure Atlas F9 authored-note topology
  as separate workstreams.
- Never invent a vault page or send the full vault note inventory to a provider.
- Preserve native link behavior, modifier-click, hover, PDF navigation, hidden
  Curator DAG rewriting, and edit-loop phase markers.
- No DB schema or backend API change is planned.

## Immediate Next Action

Obtain user approval for the v0.38.0 plan, then begin docs-first/TDD
implementation.
