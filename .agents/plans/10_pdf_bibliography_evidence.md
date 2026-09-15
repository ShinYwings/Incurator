# v0.82.8 evidence ledger

Before code: schema14/base14b793f4. Clean isolated hotfix checkout; lifetime WIP
is another worktree. No application code edited before Arena/docs/test phase.
Native identity omission and failed-result negative cache verified in source;
specific incident cause unconfirmed. Backend tools available for absolute PDF
path and authoritative page metadata. No new server interface needed.

Pending: failing regressions, implementation, source-bearing prompt verification,
private PDF fixture, full checks, review, release. Runtime .venv is untouched by
hotfix tests; worktree uses its own .venv-dev.

## Verified 2026-09-15

Backend2045passed,6skipped,4xfail,3subtests; Ruff and mypy134files passed.
Plugin1307passed,3skipped; TypeScript and production bundle passed. A private
11-page PDF fixture returned actual page7 and page11 text with total_pages11
through existing backend API. Isolated testbed status passed after creating
the worktree's previously absent synthetic testbed settings. Spec sync10passed.

TDD: reader missing-module red, bibliography six regression failures red,
followup missing-module red, cache extent7->11 and outline change red, new
bibliography block announcement3fail red; all now green. Native7->11 outgoing
prompt includes real author text and source persists on author followup.

Independent review found removed seen-page index/docID (restored from captured
leaf with behavioral distant-page regression), cache extent poisoning (fixed
with coverage signature), external reload cache invalidation (restored docID),
and missing block announcement (fixed in both instructions). Final five-lens
review found native same-path stale bibliography (P2/85); failing replacement
test confirmed it. Native scans now bypass cache reads/writes. Reviewer verified
propagation, seeded-cache bypass, repeated replacements, no cache writes and
actual popover followup. Finding closed, no remaining introduced finding >=80.
Final plugin1308passed,3skipped; TypeScript and production build passed.
Review skill substitution remains user-authorized after Claude OAuth failure;
the skill itself was not used for this PR.
Actual reported document/viewer was not supplied; do not claim exact incident
reproduction or universal prevention of arbitrary model hallucinations.
