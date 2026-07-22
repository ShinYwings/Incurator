# RELAY - RELEASE READY

## Goal
Ship v0.36.5 Zotero import case-collision refresh hotfix.

## Plan Reference
Completed plan artifacts deleted per release workflow; history is preserved in Git.

## Analysis & Reasoning
ZotMoov recreated the EWA Zotero item (`RBKB7NXE`, attachment `6SFC2FXA`). The
wizard renders `EWA Splatting.md`, but the existing note is
`EWA splatting.md`. Obsidian's exact path lookup misses it; the case-insensitive
macOS filesystem then rejects creation with `EEXIST`.

## Progress Status
v0.36.5 implementation and all local release gates passed. Branch is ready for review and merge.

## Critical Context / Blockers
Preserve `03_Notes` content and refresh only from the explicit user import action.

## Immediate Next Action
Review and merge the v0.36.5 hotfix PR, then sync `master` and reset this relay to IDLE.
