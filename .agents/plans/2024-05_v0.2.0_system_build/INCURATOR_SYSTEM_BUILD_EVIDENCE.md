# Incurator System Build Evidence Ledger

This file records the factual baseline that the v0.2.0 build plan must obey.
It exists so that documentation, monorepo migration, source import behavior, and
plugin deployment work do not drift away from the actual repository and vault
state.

The ledger is intentionally operational. It is not a philosophy document. It is
the evidence table that must be refreshed before any destructive repository
operation such as subtree import, `git mv`, submodule removal, database schema
migration, or plugin deployment folder replacement.

## 1. Current Repository Reality

Observed repository root:

```text
/home/shin/Workspace/Incurator
```

Current top-level layout observed before monorepo relocation:

```text
Incurator/
├── docs/
├── scripts/
├── src/
│   ├── curator/
│   └── qmd/
├── testbed/
├── tests/
├── README_KR.md
├── README.md
├── AGENTS.md
└── CLAUDE.md
```

This means the target `backend/` layout described in the v0.2.0 plan is not a
fact to assume; it is a migration target. Any document that mentions
`backend/src/curator` must either say "target layout" or be written after the
move has actually happened.

## 2. Current Plugin Naming And Location

The current plugin name is:

```text
incurator-obsidian-agent
```

The old name:

```text
obsidian-ai-agent
```

must be treated as historical language only. New instructions, commands, paths,
and deployment examples must use `incurator-obsidian-agent` unless they are
explicitly explaining a rename.

Current vault deployment/source location observed in the active vault:

```text
/home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent
```

At the time this ledger was written, the plugin source still exists in the
vault plugin folder. The v0.2.0 target is to move canonical plugin source into
the Incurator monorepo under `plugin/` and leave the vault plugin folder as a
compiled deployment target containing only the runtime files needed by
Obsidian.

## 3. Current Dirty Worktree Categories

The Incurator repository currently has documentation, backend implementation,
test, and unrelated worktree changes. Because these changes may belong to the
user or another agent, no command may revert them casually.

Observed categories:

- v0.2.0 documentation:
  - `.agents/plans/2024-05_v0.2.0_system_build/INCURATOR_SYSTEM_BUILD.md`
  - `docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.2.0.md`
  - `docs/specs/curator_schema/SCHEMA_v0.2.0.md`
  - guide and README files
- backend source/provenance work:
  - `src/curator/db.py`
  - `src/curator/ingest_raw.py`
  - `src/curator/mcp_server.py`
  - `src/curator/parsers/pdf.py`
  - `src/curator/search.py`
  - `tests/test_source_provenance.py`
- unrelated or separately owned changes observed:
  - `scripts/dev/testbed_template/create_testbed.py`
  - `src/curator/testbed_manager.py`
  - `src/qmd/finetune/experiments/gepa/score.py`

Any later implementation phase must classify dirty files again immediately
before editing.

## 4. Known Validation Results From Current Work

The following focused checks have passed during recent implementation work:

```bash
cd /home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent
npx tsc --noEmit
npm run build
git diff --check
```

```bash
cd /home/shin/Workspace/Incurator
python -m compileall src/curator/parsers/pdf.py src/curator/db.py src/curator/ingest_raw.py src/curator/cli.py src/curator/mcp_server.py src/curator/search.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_source_provenance.py
git diff --check
```

The following broader check is known to be environment-sensitive:

```bash
pytest
```

Plain `pytest` may be blocked by a global pytest plugin environment issue
outside this repository. When this happens, use
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` for repository-local validation and record
the blocker explicitly.

## 5. Current Schema Reality To Recheck Before Migration

Before any schema migration is applied to a real vault, inspect:

```bash
sqlite3 /home/shin/Workspace/second_brain/.curator/state.sqlite '.schema sources'
sqlite3 /home/shin/Workspace/second_brain/.curator/state.sqlite '.schema source_pdf_pages'
```

The v0.2.0 schema plan distinguishes:

- existing or transitional provenance fields such as `import_origin` and
  `import_policy`
- target reference-mode fields such as `external_path`, `is_reference`, and
  `logical_source_id`

No migration may drop transitional columns during the same phase that introduces
reference mode.

## 6. Rollback Requirements Before Destructive Operations

Before monorepo restructuring:

```bash
cd /home/shin/Workspace/Incurator
git status --short
git branch incurator-v0.2-before-monorepo
git tag incurator-v0.2-pre-migration
```

Before replacing the Obsidian plugin deployment folder:

```bash
cd /home/shin/Workspace/second_brain
mkdir -p /tmp/incurator-plugin-v0.2-backup
cp -a .obsidian/plugins/incurator-obsidian-agent/data.json /tmp/incurator-plugin-v0.2-backup/data.json 2>/dev/null || true
cp -a .obsidian/plugins/incurator-obsidian-agent/manifest.json /tmp/incurator-plugin-v0.2-backup/manifest.json 2>/dev/null || true
cp -a .obsidian/plugins/incurator-obsidian-agent/main.js /tmp/incurator-plugin-v0.2-backup/main.js 2>/dev/null || true
cp -a .obsidian/plugins/incurator-obsidian-agent/styles.css /tmp/incurator-plugin-v0.2-backup/styles.css 2>/dev/null || true
```

Do not delete the plugin folder until `data.json` is accounted for.

## 7. Phase 1-3 Execution Update

Execution date: 2026-05-28.

Rollback anchors were created before structural relocation:

```bash
git branch incurator-v0.2-before-monorepo
git tag incurator-v0.2-pre-migration
```

The monorepo layout now exists in the working tree:

```text
Incurator/
├── backend/
│   ├── pyproject.toml
│   ├── install.sh
│   ├── src/
│   │   ├── curator/
│   │   └── qmd/
│   └── tests/
├── plugin/
│   ├── main.ts
│   ├── src/
│   ├── package.json
│   ├── package-lock.json
│   ├── esbuild.config.mjs
│   └── manifest.json
├── docs/
├── scripts/
├── setup.sh
├── README_KR.md
└── README.md
```

Backend relocation was performed with `git mv` for tracked files:

- `src/` -> `backend/src/`
- `tests/` -> `backend/tests/`
- `pyproject.toml` -> `backend/pyproject.toml`
- `install.sh` -> `backend/install.sh`

`uv.lock` was untracked/ignored in the repository and was moved physically to
`backend/uv.lock` for local continuity, but it is still ignored by root
`.gitignore`.

Plugin source was copied from the active vault submodule into `plugin/` with
runtime files excluded:

- excluded `.git`
- excluded `node_modules`
- excluded `data.json`
- excluded generated `main.js`

The vault plugin folder was converted from submodule source checkout into a
deployment target. The full pre-conversion plugin folder was backed up at:

```text
/tmp/incurator-plugin-v0.2-backup-full/incurator-obsidian-agent
```

The key runtime files were also copied to:

```text
/tmp/incurator-plugin-v0.2-backup/
```

The active deployment folder now contains only:

```text
/home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent/data.json
/home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent/main.js
/home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent/manifest.json
/home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent/styles.css
```

The `second_brain` git submodule entry was removed from `.gitmodules`, and the
deployment folder is ignored by `.gitignore` so compiled plugin artifacts do not
re-enter the vault git history.

Path updates applied during this phase:

- `backend/pyproject.toml` now uses `readme = "../README_KR.md"`.
- `backend/pyproject.toml` now points Hatch at `../scripts/build/hatch_build.py`.
- `scripts/build/hatch_build.py` resolves the repository root from either
  backend or root execution and locates qmd at `backend/src/qmd` first.
- `backend/install.sh` changes into its own directory and invokes
  `../scripts/build/hatch_build.py`.
- `backend/src/curator/testbed_manager.py` now resolves `scripts/dev` from the
  deeper `backend/src/curator` path.

- `plugin/esbuild.config.mjs` supports `OBSIDIAN_PLUGIN_DIR` and copies
  `manifest.json` and `styles.css` to the deployment directory after build.
- root `setup.sh` installs the backend, installs plugin dependencies, and
  builds the plugin.

Focused validation passed after relocation:

```bash
cd /home/shin/Workspace/Incurator
python -m compileall backend/src/curator
PYTHONPATH=backend/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest backend/tests/test_source_provenance.py
PYTHONPATH=backend/src python -c "import curator, inspect; print(curator.__file__)"
git diff --check -- setup.sh backend plugin scripts docs README_KR.md README.md AGENTS.md CLAUDE.md
```

```bash
cd /home/shin/Workspace/Incurator/plugin
npm install
npx tsc --noEmit
npm run build
npm test
OBSIDIAN_PLUGIN_DIR=/home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent npm run build
```

Plugin test result:

```text
Test Files  4 passed (4)
Tests       46 passed (46)
```

Known residuals:

- The Incurator worktree is intentionally very large because structural `git mv`
  now shows many renames.
- Full `pytest` remains unverified in this step because previous evidence
  showed the environment can be affected by global pytest plugin loading. Use
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` for repository-local checks unless the
  environment is cleaned.
- The stale integrity test for bottom-up concept regeneration was updated to
  match the current contract: `_regenerate_concept()` intentionally returns
  `False` because bottom-up regeneration has been deprecated in favor of
  top-down Exhibition-driven repair.
- The vault repository now records deletion of the old submodule gitlink
  (`D .obsidian/plugins/incurator-obsidian-agent`) plus `.gitmodules` deletion
  and `.gitignore` modification. The physical plugin deployment folder still
  exists and Obsidian can load it.

## 8. Phase 4-6 Backend Source State Update

Execution date: 2026-05-28.

The backend schema now stamps:

```text
SCHEMA_VERSION = 3
```

The `sources` table now includes the v0.2.0 reference-mode fields:

- `external_path`
- `is_reference`
- `logical_source_id`
- `import_origin`
- `import_policy`

SQLite connections now enable:

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys = ON;
```

Reference import behavior now exists in the backend helper layer:

```python
ingest_raw.import_source_file(paths, external_path, policy="reference")
```

This registers an external supported file in place, records `external_path`,
sets `is_reference = 1`, creates a deterministic fallback `logical_source_id`,
and stores PDF page provenance when the parser supplies page metadata. This is
not yet a Zotero-key integration; Zotero-specific logical IDs remain a later
adapter concern.

Copy import still lands external files under `04_Resources/Imports` or mirrors
`03_Notes/...` into `04_Resources/...`, and it marks `is_reference = 0`.

MCP source-tool compatibility now includes both historical and v0.2.0 names:

- historical: `curator_search_sources`
- v0.2.0 alias: `curator_search_source`
- historical: `curator_get_source_page`
- v0.2.0 alias: `curator_get_pdf_page`

Focused validation passed after the schema/reference-mode update:

```bash
cd /home/shin/Workspace/Incurator
python -m compileall backend/src/curator
PYTHONPATH=backend/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest backend/tests/test_source_provenance.py backend/tests/test_mcp_source_tools.py
python -c "import tomllib; tomllib.load(open('backend/pyproject.toml','rb')); print('ok')"
git diff --check -- backend/src/curator backend/tests docs setup.sh plugin scripts AGENTS.md CLAUDE.md README_KR.md README.md
```

Test result:

```text
11 passed
```

Full backend test result after updating the stale integrity assertion:

```bash
PYTHONPATH=backend/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest backend/tests
```

```text
39 passed
```

## 9. Phase 7-9 Integration Update

Execution date: 2026-05-28.

Additional backend reference-mode integration now exists beyond the first
schema/import pass.

New backend helper module:

```text
backend/src/curator/source_tools.py
```

This module is intentionally independent of FastMCP so it can be tested without
starting a wire-protocol server. It owns:

- external resource root normalization from config
- live source status calculation for vault-local and reference-mode sources
- moved-file candidate discovery inside configured external roots
- hash-drift detection without automatic mutation
- dry-run/apply source rebind logic
- source rebind ledger append

The backend default config now includes:

```yaml
external:
  roots: []
  zotero:
    enabled: true
    roots: []
```

The MCP server now exposes the planned human-in-the-loop source repair tools:

- `curator_list_external_resources`
- `curator_rebind_source`

`curator_source_status` now returns enriched row metadata for tracked sources,
including fields such as:

- `state`
- `message`
- `current_path`
- `current_hash`
- `candidate_path`
- `candidate_hash`
- `requires_rebind`

The plugin integration was also extended:

- `IncuratorClient.getPdfRagHits()` now tries `curator_search_source` before
  older aliases.
- `IncuratorClient.ingestPdf()` now sends an explicit `policy`:
  - `reference` for reference-mode registration
  - `mirror_03_to_04` for copy-mode import
- `IncuratorClient.rebindSource()` calls `curator_rebind_source`.
- `IngestDestinationModal` now asks for import mode:
  - reference external file
  - copy into vault
- plugin settings now include `incuratorDefaultImportMode`.
- PDF backend status chips now recognize:
  - `missing`
  - `moved`
  - `hash_drift`
  - `moved_and_hash_drift`
- When a moved source returns a `candidate_path`, the plugin asks the human for
  confirmation before calling `curator_rebind_source(apply=true)`.

Reference/rebind coverage was added to:

```text
backend/tests/test_mcp_source_tools.py
```

The added cases cover:

- reference import stores external path and does not copy into `04_Resources`
- hash drift is detected without mutating the source row
- moved candidates are found under configured external roots
- rebind dry-run does not mutate
- rebind apply updates `external_path`
- external resource config roots normalize into MCP-friendly objects

Validation results:

```bash
cd /home/shin/Workspace/Incurator
python -m compileall backend/src/curator
PYTHONPATH=backend/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest backend/tests -q
```

```text
43 passed
```

```bash
cd /home/shin/Workspace/Incurator/plugin
npx tsc --noEmit
npm test -- --run
npm run build
OBSIDIAN_PLUGIN_DIR=/home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent npm run build
```

```text
TypeScript passed
46 plugin tests passed
plugin production build passed
vault deployment build passed
```

```bash
cd /home/shin/Workspace/Incurator/backend/src/qmd
npm run build
npx vitest run --reporter=verbose test/
```

```text
18 test files passed
788 tests passed
```

Changed-file lint and whitespace validation:

```bash
ruff check backend/src/curator/source_tools.py backend/src/curator/mcp_server.py backend/src/curator/config.py backend/tests/test_mcp_source_tools.py
git diff --check
cd /home/shin/Workspace/second_brain
git diff --check -- .gitignore .gitmodules
```

```text
All checks passed
```

Whole-backend lint/type status:

```bash
ruff check backend/src
mypy backend/src
```

These broad checks still fail because of pre-existing repository-wide lint/type
issues unrelated to the new source-tools files. Examples include unused imports,
legacy one-line statements, a pre-existing undefined `sync_module` reference in
`cli.py`, duplicate `eval` modules under qmd finetuning, and missing third-party
typing stubs for `yaml`, `bs4`, and `fitz`. The changed-file ruff check passes.

## 10. Phase 5 Platform-Aware Config CLI Update

Execution date: 2026-05-28.

`wiki config get` and `wiki config set` commands are now implemented in
`backend/src/curator/cli.py` under the existing `config_app` typer group.

Behavior:

- `wiki config get <key>` — reads a dot-separated key from the merged global
  plus project config. Falls back to global-only if no project root is found.
- `wiki config set <key> <value>` — writes to the global config at
  `~/.config/curator/config.yml` by default. Pass `--local` to write to the
  project config instead.
- `wiki config set ... --append` — appends to a list field rather than
  replacing. Preserves an existing scalar value by promoting it to a list.

Phase 5.4 validation now passes:

```bash
wiki config set external.zotero.roots "$HOME/Zotero/storage"
# ✓ global config updated: external.zotero.roots = "/home/shin/Zotero/storage"
wiki config get external.zotero.roots
# /home/shin/Zotero/storage

wiki config set external.zotero.roots "$HOME/Documents/Zotero" --append
# ✓ global config updated ...
wiki config get external.zotero.roots
# ["/home/shin/Zotero/storage", "/home/shin/Documents/Zotero"]
```

The editable install `.pth` file was also corrected from the old
`/home/shin/Workspace/Incurator/src` path to the new monorepo location
`/home/shin/Workspace/Incurator/backend/src` via:

```bash
cd /home/shin/Workspace/Incurator/backend && pip install -e .
```

This was required because the wiki binary was still loading curator from the
pre-migration root and raising `ModuleNotFoundError: No module named 'curator.cli'`.

## 11. Phase 8 Final Automated Verification

Execution date: 2026-05-28.

Full automated Phase 8 suite results:

```bash
cd /home/shin/Workspace/Incurator
python -m compileall backend/src/curator
```

passed

```bash
PYTHONPATH=backend/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest backend/tests -q
```

43 passed

```bash
ruff check backend/src/curator/source_tools.py backend/src/curator/mcp_server.py backend/src/curator/config.py backend/tests/test_mcp_source_tools.py
```

All checks passed

```bash
cd /home/shin/Workspace/Incurator/backend/src/qmd && npm run build && npx vitest run test/
```

18 test files passed, 788 tests passed

```bash
cd /home/shin/Workspace/Incurator/plugin
npx tsc --noEmit && npm run build
OBSIDIAN_PLUGIN_DIR=/home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent npm run build
test -f .../main.js && test -f .../manifest.json && test -f .../styles.css
```

TypeScript passed, build passed, vault deployment passed, all artifact files verified

```bash
cd /home/shin/Workspace/Incurator
wiki testbed init testbed_template --force
VAULT_ROOT=testbed wiki status
VAULT_ROOT=testbed wiki add
VAULT_ROOT=testbed wiki sync
VAULT_ROOT=testbed wiki lint
VAULT_ROOT=testbed wiki reindex
VAULT_ROOT=testbed wiki query "Summarize the core concepts in this vault."
```

All testbed steps passed after reinstalling backend editable install from `backend/`.

```bash
git diff --check -- backend/src/curator/cli.py
```

passed

Manual Obsidian acceptance (Phase 8.5) remains pending: requires running Obsidian
app GUI. All automated gates are green.
