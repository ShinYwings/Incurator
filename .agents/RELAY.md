# Active Relay State

**STATUS: IDLE.**

No active goal. v0.27.4 (System Stability Overhaul Phase B — G17 S3 cleanup:
Zotero reload empty-metadata/no-item-key guard + legacy `imageFolder`
retirement) shipped and merged via PR #63.

## Next candidates (not started)

Remaining Phase B work — start each on a fresh branch with its own Arena plan
(these are larger, Minor-sized, and warrant plan approval before coding):

- S2 architectural: XC-1 broad-except narrowing.
- S2 architectural: CM-1/PL-1/DB-2 god-file decomposition.

## Deferred / Icebox

- **G17-7 full fix**: citekey → Zotero item-key resolution needs a backend
  resolver (citekeys are derived, not stored in `items.key`). Minor with its own
  plan if multi-profile users need refresh of notes lacking `zotero_app_url`.
- **G17-10**: Zotero passthrough consistency — low priority, only when a wrapper
  cleanup PR already touches those methods.
