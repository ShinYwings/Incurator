# RELAY - ACTIVE

## Goal
Ship v0.36.5 Zotero import case-collision refresh hotfix.

## Plan Reference
`.agents/plans/02_zotero_refresh_collision.md`

## Analysis & Reasoning
ZotMoov recreated the EWA Zotero item (`RBKB7NXE`, attachment `6SFC2FXA`). The
wizard renders `EWA Splatting.md`, but the existing note is
`EWA splatting.md`. Obsidian's exact path lookup misses it; the case-insensitive
macOS filesystem then rejects creation with `EEXIST`.

## Progress Status
Root cause reproduced. Isolated v0.36.5 plan approved; docs-first implementation started.

## Critical Context / Blockers
Preserve `03_Notes` content and refresh only from the explicit user import action.

## Immediate Next Action
Add the failing collision-refresh tests, then implement the scoped writer fix.
