# Installation & Version Management Unification Plan

## Context
Triaged from USER_REPORT on 2026-06-11. The backend install path is fragmented:
multiple `wiki` binaries coexist at different versions and the Obsidian plugin
resolves the wrong one, so a freshly built backend is not the one actually
executed. This silently breaks the self-update mechanism (the version bump that
triggers the Obsidian update toast). This is foundational/high-priority cleanup
and is partly hotfix-class.

## Observed Symptoms (verbatim evidence to preserve)
- Plugin shows `0.4.2` while `manifest.json` is `0.4.3`. Plugin reads
  `/Users/shin/.local/bin/wiki`, which reports `0.3.2`. Plain `wiki version`
  reports `0.4.3`. `./backend/.venv/bin/wiki version` reports `0.4.2`.
  → At least three separate `wiki` installs exist on the dev machine.
- `uv tool` installed one copy into the isolated env under
  `~/.local/share/uv/tools/incurator/`; `model_setup.py` uses
  `uv pip install --python sys.executable llama-cpp-python`, which can target a
  different venv than the one the plugin invokes.
- `./setup.sh` updates `incurator_project_path/.venv/bin/wiki` (→ `0.4.3` via
  `uv run wiki version`), but `./backend/.venv/bin/wiki` is stale at `0.4.2`.
- Agent commands mix `cd backend && uv pip install -e .` vs
  `uv pip install -e ./backend`, producing inconsistent install targets.
- Entering `0.4.0` (etc.) in the project causes version-string mismatches across
  docs / client / backend because there is no single source of truth.

## Requirements
1. **Single version source of truth.** Backend version owned by
   `build_manifest.json`; plugin version owned by `buildManifest.json`
   (and `manifest.json`/`package.json`/`pyproject.toml` derived from it). Remove
   redundant hardcoded version strings. Decide whether docs need a version
   string at all (user leans "no" for docs).
2. **One canonical backend install command.** Pick exactly one of
   `uv pip install -e ./backend` OR `cd backend && uv pip install -e . && cd ..`
   and use it everywhere. All installs must land in one external location, never
   a per-folder `.venv`. Every agent command that does `cd backend`/`cd plugin`
   MUST `cd ..` back.
3. **Eliminate duplicate `wiki` binaries.** Investigate `uv tool` vs `uv pip`
   vs `~/.local/bin` installs; ensure plugin resolves the same binary that
   `./setup.sh` updates. Document a clean re-install/uninstall path.
4. **Finish the `OBSIDIAN_PLUGIN_DIR` / `.env` removal** promised in the 0.4.2
   changelog: purge remaining `build_env["OBSIDIAN_PLUGIN_DIR"] = ""` in
   `cli.py` and elsewhere; find and remove the root cause that generates
   `plugin/.env.example`.
5. **Fix `plugin/deploy.sh`.** Remove the stale `exit 1`; fall back to local
   build (mirror the smart `.cache/config/last_root` logic already in root
   `setup.sh`).
6. **Fix dashboard model-display persistence.** After changing the model and
   restarting, the dashboard keeps showing `antigravity gemini 3.5 flash` even
   though `wiki status` confirms the real model changed. UI reads a stale/default
   value instead of the persisted config.
7. **Docs path cleanup.** Remove all real/absolute machine paths
   (e.g. `/Users/shin/...`, `second_brain`) from `docs/`.

## Files Likely Involved
- `backend/src/curator/model_setup.py` (the `uv pip install --python` logic)
- `backend/src/curator/cli.py` (`build_env["OBSIDIAN_PLUGIN_DIR"]`, version)
- `setup.sh`, `plugin/deploy.sh`
- `backend/src/curator/data/build_manifest.json`, plugin `buildManifest.json`,
  `manifest.json`, `package.json`, `pyproject.toml`
- Dashboard UI source reading the active model
- `docs/**` (path scrub)

## Notes
- This touches the self-update contract — see CLAUDE.md "VERSION BUMP IS
  MANDATORY". Plan must verify the version-consistency CI gate still passes.
- Needs testbed validation of a clean install from scratch.
