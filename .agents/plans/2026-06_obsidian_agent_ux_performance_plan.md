# Obsidian Agent UX & Performance Improvements

## Source Plan

Imported from:

`/Users/shin/.gemini/antigravity-ide/brain/b0e5cb7d-9600-4b66-9c89-42b417037c71/implementation_plan.md`

This repo-local copy exists so future agents can discover the active plan from
`.agents/plans/` and `.agents/relay.md` without depending on Antigravity's
external brain directory.

## Goal

Improve the Obsidian plugin's Zotero import UX, PDF viewer resize performance,
and confirmation behavior for chat deletion and dashboard reset actions.

## Approved Scope

1. Zotero import modal
   - Auto-load the first saved profile when opening the wizard.
   - Trigger empty-query suggestions when the search modal opens.
   - Track recently imported Zotero item keys in an LRU list.
   - Prioritize recently imported items in Zotero suggestions.
   - Render output folders, filenames, and asset subfolders with the existing
     Nunjucks `TemplateRenderer` rather than the legacy `{{key}}` regex.
   - Add practical Zotero metadata filters for author names, tags, and safe
     path segments.
2. PDF viewer
   - Avoid rerendering pages on resize callbacks unless the client width
     actually changes.
3. Dashboard reset
   - Require two confirmations before running backend reset.
4. Chat history
   - Delete sessions immediately when the trash action is clicked, without a
     native confirmation prompt.

## Verification

- Update plugin docs and plugin schema for changed settings/behavior.
- Add focused Vitest coverage for reusable Zotero helper behavior and template
  filters.
- Run plugin tests/build.
- Run the available testbed smoke commands and report any blocker.
