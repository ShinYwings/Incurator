# v0.36.5 Master Implementation Plan

Date: 2026-07-22
Status: APPROVED — user approved the isolated hotfix on 2026-07-22.

## 1. Objective

Make **Import Zotero Item** refresh an existing note when the newly rendered
filename differs only by case, instead of failing with `File already exists` on
case-insensitive filesystems. Preserve the existing note body while refreshing
frontmatter, annotations, assets, and the current Zotero parent/attachment keys.

## 2. Explicit Non-Goals

- Do not rename notes whose titles materially differ.
- Do not guess identity from a stale attachment key or mutate `03_Notes`
  outside the user-triggered import.
- Do not change Zotero DB records or ZotMoov-managed files.

## 3. Strict Quality Conditions & Release Gates

- Exact-path imports keep the existing update behavior.
- A create-time `EEXIST` collision resolves only to a case-insensitive matching
  vault path and retries as `modify()`.
- Other create failures remain visible and are never swallowed.
- Existing content is passed into the template renderer so persist blocks survive.
- Plugin tests/build, backend checks, testbed smoke, docs, v0.36.5 manifests,
  and changelog pass before release.

## 4. Locked Design Decisions

- Keep exact `getAbstractFileByPath()` as the fast path.
- Extract a small helper that finds one case-insensitive vault-file match.
- On `vault.create()` failure, retry as refresh only when the error is an
  already-exists collision and the helper finds the canonical existing file.
- Re-render with that existing file's content before `modify()`; do not reuse
  markdown rendered against an empty body.

## 5. Evidence Ledger

- Existing note: `03_Notes/Papers/EWA splatting.md`.
- Current Zotero title/output: `EWA Splatting` → `EWA Splatting.md`.
- macOS filesystem treats those paths as the same inode while Obsidian's exact
  path lookup does not.
- Current Zotero parent key: `RBKB7NXE`; effective attachment key: `6SFC2FXA`;
  PDF resolves under the ZotMoov iCloud directory.
- Old note keys `N553UVKA` / `2JBAPFWN` no longer exist in the current DB.

Rollback anchor: `master` at branch creation. No database or Zotero mutation is
part of this patch; rollback is the normal PR revert.

## 6. Execution Phases

- **P0 Docs/TDD**: document case-only refresh semantics; add failing unit tests.
- **P1 Implementation**: add collision-aware refresh without changing normal creation.
- **P2 Validation**: targeted/full plugin tests, build, backend checks, and a
  testbed or isolated vault reproduction.
- **P3 Release**: bump v0.36.5, update changelog/roadmap, delete this plan,
  commit, push, and open a draft PR.
