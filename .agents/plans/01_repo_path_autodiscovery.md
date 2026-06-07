# Repo Path Auto-Discovery — Master Implementation Plan

Date: 2026-06-07
Status: APPROVED — Arena debate concluded (`repo_path_autodiscovery_arena/`).

## Strict quality condition (절대 타협 불가)
- A fresh device needs ZERO manual "Repository path" entry for plugin updates.
- `wiki plugin version` MUST remain vault-independent (no `_resolve_root_or_die`).
- No machine-local path (repo_path) written into any SYNCED artifact. Only
  global `.cache/config/devices.json` and `.stignore`'d plugin `data.json`.
- Non-editable (site-packages) installs report `repo_path: null` → plugin hides
  the update action instead of erroring.

## Locked design decisions (Arena 합의)
1. **Detection = `__file__` markers.** `detect_repo_root()` returns
   `parents[2].parent` only when both `setup.sh` and `plugin/manifest.json` exist
   there; else `None`. No `.git` requirement (tarball checkouts updatable). Pure
   stdlib, no config/vault imports.
2. **JSON surface = `wiki plugin version`** (live) + `devices.json` backend block
   (cache). Plugin prefers live, writes through to cache.
3. **Plugin precedence:** `settings.incuratorRepoPath` (override, `.trim()` so
   empty = unset) → `incuratorClient.repoPath` (live) → cached devices.json → null.
4. **Update scope = current open vault** via `getBasePath()` (unchanged).
5. **Settings field** stays as an optional override with auto-detected hint, not
   a required input. Update toast gated on `needsUpdate && repoPath != null`.

## Evidence Ledger (증거 장부)
- Rollback anchor: branch `hotfix/v0.4.1-device-local-paths` HEAD before this work.
- Verified reality:
  - `curator.__file__` → `.../Incurator/backend/src/curator/__init__.py`;
    `parents[2].parent` = repo root; `setup.sh`+`plugin/main.js` present.
  - `plugin_version()` (cli.py:6034) does NOT resolve a vault. Safe to extend.
  - `backend_launcher()` (device_registry.py:204) already in devices.json.
  - `data.json` already `.stignore`'d (line 28); `devices.json` in global cache.
- Pre-validation: `pytest tests/test_device_registry*.py` + plugin vitest green.

## Execution Phases (각 단계: TDD + ruff + CI 통과 후 다음)

### P1 — Backend detection + JSON surface
- `device_registry.py`: add `detect_repo_root() -> str | None` (markers: setup.sh
  + plugin/manifest.json). Add `repo_path` to `backend_launcher()` output.
- `cli.py` `plugin_version()`: add `repo_path: detect_repo_root()` to JSON.
- **TDD:** test detect_repo_root() with/without markers (monkeypatch root);
  test `wiki plugin version` runs in a non-vault cwd and returns repo_path key.
- **Verify:** `pytest tests/test_device_registry.py tests/test_plugin_cli.py`; `ruff`.

### P2 — Plugin resolution + caching
- `incuratorClient.ts`: capture `repo_path` from `plugin version` into
  `this.repoPath`.
- `main.ts`: cache repo_path into devices.json; `updateIncuratorBackend()` uses
  precedence chain; show clear Notice when repoPath null.
- `deviceRegistry.ts`: add `getLocalBackendRepoPath()` reader if absent.
- **TDD:** vitest for precedence (override > live > cache > null) and the
  null-disables-update path.
- **Verify:** `npx tsc --noEmit`, `npx vitest run`.

### P3 — Settings UX
- `settings.ts`: repo path field → optional override; show auto-detected hint;
  gate update toast on `needsUpdate && repoPath`.
- **Verify:** vitest for settings boundary; manual UX note.

### P4 — Docs + CHANGELOG
- `PLUGIN_GUIDE.md` (+ `_KR`): repo path now auto-detected, override optional.
- `SYSTEM_BEHAVIOR.md`: `wiki plugin version` reports `repo_path`; null for
  non-editable installs.
- CHANGELOG v0.4.1 entry (still on the same hotfix branch).
- **Verify:** full `pytest -q` + `ruff` + plugin `vitest` + `tsc`.
