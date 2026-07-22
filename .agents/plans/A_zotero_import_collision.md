# Plugin Domain Analysis: Zotero Import Collision Refresh

Date: 2026-07-22

## Design constraints

- Obsidian exact vault lookup can miss a path whose case differs, while the
  macOS filesystem rejects creation of the case-only duplicate.
- Existing note content must be supplied to `TemplateRenderer` so persist
  blocks survive a refresh.
- Only an explicit Import Zotero Item action may rebind the note to the newly
  selected Zotero parent and attachment keys.

## Alternatives and trade-offs

- Pre-scan case-insensitively on every import: avoids an exception, but changes
  valid behavior on case-sensitive filesystems.
- Catch every create failure and update: hides unrelated filesystem failures.
- Catch only already-exists, resolve one case-insensitive vault file, and
  re-render against its content: preserves current behavior everywhere else.

## Decision

Use the third option. Keep exact-path update as the fast path. If create reports
an already-exists collision, find exactly one case-insensitive file match,
read it, render again, and modify that file. Re-throw all other failures.

## Pseudocode

```text
if exact file exists:
    modify(exact, render(read(exact)))
else:
    try create(path, render(""))
    catch already-exists:
        collision = unique file where lower(path) == lower(requested path)
        modify(collision, render(read(collision)))
```
