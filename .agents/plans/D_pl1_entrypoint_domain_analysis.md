# PL-1 Domain Analysis D: Plugin Entrypoint

Date: 2026-07-09

## Design Constraints From Codebase

- `main.ts` is 2,224 LOC and is the Obsidian plugin entrypoint.
- It constructs `LLMClient`, registers `ChatSidebarView` and `ExternalPdfView`,
  owns settings load/save, sync scheduler wiring, backend command wrappers,
  Zotero commands, and view-opening helpers.

## Docs/Specs Invariants

- Obsidian lifecycle methods (`onload`, `onunload`, view registration, command
  registration) must remain behaviorally identical.
- Backend command invocation boundaries in `PLUGIN_SCHEMA.md` remain unchanged.

## Alternatives & Trade-offs

- Include full `main.ts` decomposition in PL-1: more complete, too much risk.
- Limit PL-1 to extracted view/client modules and only touch `main.ts` imports:
  safer, leaves entrypoint debt for a later slice.

## Final Decision

PL-1 may only make `main.ts` import-path updates and extract obviously pure
startup helpers if needed to break cycles. A full `main.ts` decomposition is
deferred unless the three primary god-files are already green and the remaining
change is mechanical.

## Implementation Pseudocode

```text
keep main.ts as Obsidian Plugin subclass
update imports to facades or new public modules only after tests pass
do not change command ids, ribbon ids, view types, settings schema, or lifecycle order
```
