# v0.36.7 Briefing: Headless Read And Open-Tab Context Integrity

Date: 2026-07-26

## User Report

Obsidian Agent intermittently returns:

> jetski: no output produced — a tool required the "read_file" permission that
> headless mode cannot prompt for

The issue was nominally fixed in v0.36.4. The user additionally observed that
opening several Obsidian tabs does not produce the same number of purple PDF
`Add source` context chips and suspects the two behaviors are related.

## Measured Reproduction

- Repository rollback anchor: `45cd97f` on `master`.
- Installed plugin files are v0.36.6 and were written on 2026-07-23.
- The live Obsidian process started on 2026-07-20, before the v0.36.4 bundle was
  deployed.
- A real failed turn is visible in the live Obsidian chat history.
- After that turn,
  `~/.gemini/antigravity-cli/settings.json` did not contain
  `permissions.allow` or `$read_file$()`.
- The current source and deployed `main.js` are byte-identical and contain the
  v0.36.4 permission helper. The helper's targeted test suite passes.
- The live workspace contains one external PDF leaf and three Markdown content
  leaves, while the observed chip row showed only the active PDF and Markdown
  contexts.
- `getOpenTabContexts()` explicitly removes `0x0` leaves, which are the hidden
  members of an Obsidian tab group.

## Root-Cause Boundary

There are two separate defects:

1. **Activation lifecycle:** deployment copies a new bundle to disk but allows
   the old in-memory plugin to continue answering questions. The v0.36.4 helper
   cannot run if v0.36.4+ was never loaded.
2. **Tab discovery:** an API named `openTabs` actually returns only visible
   split leaves. Hidden tab-group leaves are absent from chips, the add-context
   menu, and prompt assembly.

The second defect can increase the chance that an agent attempts a native
`read_file`, but it does not remove the permission rule and is not the direct
cause of the denial.

## Constraints

- Never restore `--dangerously-skip-permissions`.
- Preserve OS sandboxing and `--add-dir` path containment.
- Never auto-register or ingest a PDF because its tab is open.
- Do not send every hidden tab into the prompt by default; the existing prompt
  repeats tab content across multiple blocks and would grow without a useful
  bound.
- Do not modify `03_Notes/`, production source files, or external PDFs during
  validation.
- No DB/schema/data migration is required.

## Decision Requested

Approve the conservative context contract:

- every eligible open Markdown/PDF leaf is represented by a context chip;
- visible split leaves start eye-on;
- hidden tab-group leaves start eye-off and enter the prompt only after an
  explicit eye-on/pin action;
- exact duplicate `(view type, source identity, page)` leaves may be deduplicated
  while different pages remain distinct.

