# Goal
Automatically generate safe `.gitignore` and `.stignore` files when running `wiki init`. This prevents users from accidentally syncing the `.curator` runtime databases (like `state.sqlite` and `runtime/` files), which leads to sync conflicts, battery drain, and SQLite corruption.

# Status
Implemented.

# Proposed Changes

## `backend/src/curator/workspace/templates/`
- [x] **`gitignore.template`**: Added the recommended `.gitignore` rules from `docs/guides/SYNC_IGNORE_GUIDE.md` (without `.gemini/` as it's deprecated).
- [x] **`stignore.template`**: Added the recommended `.stignore` rules from `docs/guides/SYNC_IGNORE_GUIDE.md` (without `.gemini/`).

## `backend/src/curator/cli.py`
- [x] **`init()`**: Updated the `init()` command function to copy `gitignore.template` to `.gitignore` and `stignore.template` to `.stignore` in the vault root, only if they don't already exist. Added success logging.

## `docs/guides/`
- [x] **`USER_GUIDE.md` & `USER_GUIDE_KR.md`**: Updated the documentation for the `wiki init` command to explicitly mention that these synchronization safety files are generated automatically.

# Verification Plan
- `pytest` on backend to ensure basic CLI behavior holds.
- Manual test with `testbed init`.
