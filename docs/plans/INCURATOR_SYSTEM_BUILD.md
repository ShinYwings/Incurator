# Operation: Incurator System Build v0.2.0

This document is the execution blueprint for turning Incurator into a single
backend-plus-client system in which the Python Incurator backend is the durable
RAG/source-of-truth engine and the Obsidian plugin is the interactive client for
notes, PDFs, chat, source ingestion, and human-in-the-loop confirmation.

This plan intentionally does not treat the previous phase layout as binding.
The earlier layout placed "Documentation Alliance" at Phase 0 and declared it
complete. That was too weak for the actual risk profile. Documentation is not
the first mutation. Documentation is the contract, and the contract must be
derived from an evidence-locked view of the current repositories, installed
commands, vault topology, database schema, plugin deployment flow, and machine
specific path constraints. Therefore Phase 0 is redefined below as an
architecture freeze and evidence-capture phase. Documentation becomes Phase 1:
it is still mandatory before destructive implementation, but it is not allowed
to invent reality or silently override measured repository state.

The document is deliberately verbose. It is not a changelog, not a high-level
proposal, and not an executive summary. It is a handoff-grade operational plan
that another engineer or agent should be able to execute without guessing what
the system is supposed to become.

---

## 0. Vocabulary, Authority, And Non-Negotiable Model

### 0.1. Authority hierarchy

All implementation and documentation decisions must respect this authority
order:

1. The user's explicit architecture requirement:
   Incurator is the backend/RAG/source-of-truth system. Obsidian is the client.
2. The current repository reality discovered by direct inspection.
3. The durable system philosophy already expressed in README, guides, schema
   docs, and system behavior specs.
4. Existing tests and reproducible testbed behavior.
5. Preferred future architecture, only after it is reconciled with the first
   four sources.

No phase may rely on a desirable diagram when direct repository inspection
contradicts it. If the repository currently has `src/curator`, `src/qmd`, and
`tests` at the root, the plan must name that state as current reality. If a
future monorepo layout uses `backend/src/curator`, the plan must mark that as a
target state and enumerate every path migration required to get there.

### 0.2. Backend/client boundary

The Incurator backend owns:

- `.curator/state.sqlite`
- `.curator/qmd/index.sqlite`
- `.curator/Collections/`
- source registration
- source provenance
- source hash policy
- RAG search over compiled DAG state
- RAG search over tracked raw sources
- MCP tools that expose backend capabilities
- L1-L4 compilation
- sync/lint/integrity repair of generated DAG nodes
- testbed generation and backend validation

The Obsidian plugin owns:

- visible chat UI
- PDF viewer interaction
- active tab and pinned context chips
- source ingest confirmation UI
- destination selection UI
- provider model selection and provider process orchestration
- MCP client configuration and tool-call surfacing
- local immediate PDF context for currently open PDFs
- human-readable status presentation

The Obsidian plugin must not write `.curator` directly. It calls MCP tools or
backend CLI commands with explicit arguments. If the plugin ever needs to mutate
backend state, it must do so through a named backend API/tool whose behavior is
documented, tested, and recoverable.

### 0.3. Source domains

`03_Notes/` is human truth. It contains human-authored or human-verified notes.
The backend and plugin may read it. They may propose changes. They must not
autonomously rewrite it.

`04_Resources/` is immutable vault-local reference material. It may contain
external PDFs/docs copied into the vault when copying is explicitly desired.
Existing files in this folder must never be overwritten by automatic import.

External resource roots such as Zotero libraries are not the same thing as
`04_Resources/`. Zotero-managed PDFs may remain outside the vault and be tracked
by reference. Reference mode must not duplicate large PDFs merely to satisfy an
older "raw_dirs must be vault-local" assumption.

`02_Wiki/` is promoted human-readable knowledge. It is not raw source truth in
the same sense as `03_Notes`. It is a durable human-facing layer created through
explicit promotion or consensus.

`.curator/` is machine state. It is generated, indexed, repaired, migrated, and
queried by Incurator. Users and clients must not manually edit it except through
documented development/debugging workflows.

### 0.4. Reference mode vs copy mode

The v0.2.0 source import system must support two distinct policies.

Copy mode:

- The source file is copied into `04_Resources/`.
- The copied vault file becomes the source path used by `wiki add`.
- This is appropriate for documents that are intentionally stored in the vault.
- Hash changes are interpreted as changes to the vault-local source.

Reference mode:

- The source file remains outside the vault.
- The backend records an external path hint, content hash, and logical source id.
- A lightweight vault-local proxy may be created when Obsidian/vault anchoring is
  useful, but the binary PDF is not copied.
- This is the default target for Zotero-managed PDFs, especially when iPad
  annotation modifies the file in place.
- Hash drift is not automatically considered corruption. It may represent a
  legitimate annotation update and must be surfaced for human-approved rebinding
  or re-ingestion.

### 0.5. The actual reason Phase 0 must change

The previous plan's Phase 0 said documentation must be completed before code.
That is directionally correct but operationally incomplete. Before writing or
declaring documentation complete, the system must answer the following:

- Which repo currently owns the plugin source?
- Is the plugin a submodule, a copied folder, or a regular directory inside the
  vault?
- Which files are already dirty, and which dirty changes belong to a user or
  another agent?
- Does `wiki` resolve to the current Incurator source checkout or an installed
  package elsewhere?
- What is the current schema version and what columns exist in production
  `.curator/state.sqlite`?
- Does the current backend already have page-level PDF provenance, import
  helpers, or MCP source tools?
- Is qmd embedded under `src/qmd` and how does the build hook locate it?
- Which paths are synced across machines and which must remain machine-local?
- What is the rollback plan if git subtree import or directory relocation fails?

Documentation written before those facts are captured is not a contract. It is
a wish. Phase 0 must therefore be an evidence phase.

---

## Phase 0: Architecture Freeze, Evidence Ledger, And Mutation Gate

Phase 0 is not documentation completion. Phase 0 creates the factual ledger that
all later documents and code changes must obey. It prevents the plan from being
pulled around by stale assumptions.

### 0.1. Phase 0 entry conditions

Before Phase 0 begins:

- No destructive command is allowed.
- No `git mv`, `git rm`, subtree import, submodule removal, migration, or file
  relocation is allowed.
- Read-only inspection commands are allowed.
- Test/build commands are allowed if they do not rewrite tracked files.
- Existing dirty files must be treated as user/agent work and not reverted.

### 0.2. Create the evidence ledger

Create or update a dedicated evidence section inside this document, or a sibling
file if the execution team wants machine-readable logs later:

`docs/plans/INCURATOR_SYSTEM_BUILD_EVIDENCE.md`

The ledger must include exact command outputs or precise paraphrases for the
following categories.

Repository state:

```bash
cd /home/shin/Workspace/Incurator
git status --short
git branch --show-current
git remote -v
git submodule status || true
find . -maxdepth 2 -type d | sort
```

Plugin/vault state:

```bash
cd /home/shin/Workspace/second_brain
git status --short
git submodule status || true
find .obsidian/plugins -maxdepth 2 -name manifest.json -o -name package.json
ls -la .obsidian/plugins/incurator-obsidian-agent || true
ls -la .obsidian/plugins/obsidian-ai-agent || true
```

Command resolution:

```bash
command -v wiki
python - <<'PY'
import curator, inspect
print(curator.__file__)
PY
```

Backend package state:

```bash
cd /home/shin/Workspace/Incurator
python -m compileall src/curator
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_source_provenance.py || true
```

Plugin package state:

```bash
cd /home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent
npx tsc --noEmit
npm run build
```

Database reality, using the user's actual vault only for read-only inspection:

```bash
cd /home/shin/Workspace/second_brain
sqlite3 .curator/state.sqlite '.schema sources'
sqlite3 .curator/state.sqlite '.schema source_pdf_pages'
sqlite3 .curator/state.sqlite 'select id, relpath, status, file_type from sources limit 20;'
```

The ledger must also explicitly name any command that failed because of
environment issues. For example, if plain `pytest` fails because an unrelated
global Dash plugin cannot import `flask`, that must be recorded as an
environment blocker rather than as a product failure.

### 0.3. Freeze the target vocabulary

Phase 0 must freeze these terms so that later documentation does not drift:

- `backend/`: target monorepo folder that will contain Python package files.
- `plugin/`: target monorepo folder that will contain Obsidian plugin source.
- `second_brain/.obsidian/plugins/incurator-obsidian-agent`: deployment target
  for compiled plugin files and vault-local `data.json`, not the long-term
  source-of-truth TypeScript source directory.
- `copy import`: import policy that creates a vault-local binary copy.
- `reference import`: import policy that tracks an external binary without
  copying it.
- `logical_source_id`: stable identity for a source across path movement and
  hash drift. For Zotero this should eventually map to a Zotero key or a
  deterministic composite, not merely an absolute path.
- `external_path`: machine-local or platform-specific hint path used to locate
  an external source.
- `source hash`: content hash of the current bytes. It may change when the user
  annotates a PDF.
- `hash drift`: source hash differs from previously compiled source hash.
- `path drift`: external path hint no longer resolves.
- `rebind`: human-approved update that associates an existing logical source
  with a new path/hash after movement or annotation.

### 0.4. Define mutation gates

No phase after Phase 0 may begin until the following gates are satisfied.

Gate A: repository ownership is known.

- The plan must state where the canonical plugin source currently is.
- If the plugin source is currently only inside `second_brain`, the plan must
  not assume a GitHub subtree import can recover full plugin history unless
  that remote and branch have been verified.
- If `obsidian-ai-agent` is merely the old name and
  `incurator-obsidian-agent` is the current name, every command must use the
  current name.

Gate B: data loss risks are named.

- Removing a submodule or plugin folder must not delete `data.json`.
- Replacing the deployed plugin folder must preserve vault-local settings.
- Moving backend files must not invalidate installed `wiki` without a reinstall
  path.
- DB migrations must be idempotent and safe on existing vault databases.

Gate C: rollback exists.

Before any destructive change, record rollback commands. Examples:

```bash
git status --short
git branch incurator-v0.2-before-monorepo
git tag incurator-v0.2-pre-migration
```

For the vault plugin deployment target, before deleting or replacing anything:

```bash
cp -a \
  /home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent \
  /home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent.backup-pre-v0.2
```

If a backup is not acceptable because it would copy node_modules or large files,
then the plan must at least preserve:

```bash
data.json
manifest.json
main.js
styles.css
```

Gate D: migration path is reversible.

- `git mv src backend/src` must happen in a clean, reviewable commit.
- Plugin import must happen in its own commit.
- DB schema changes must be additive before any destructive schema tightening.
- Reference mode must be added without removing existing copy mode.

### 0.5. Phase 0 deliverables

Phase 0 is complete only when these are true:

- Evidence ledger exists and includes command outputs.
- Current dirty files are listed and categorized as user work, implementation
  work, generated artifacts, or unknown.
- Current canonical plugin name is confirmed as `incurator-obsidian-agent`.
- Current canonical plugin source path is confirmed.
- Current backend layout is confirmed.
- Desired target backend layout is confirmed.
- `wiki` command resolution is confirmed.
- Current schema reality is confirmed.
- High-risk destructive operations have rollback commands written down.
- The master plan has been revised to match the evidence.

If any item is missing, do not proceed to documentation finalization, subtree
import, path migration, or DB migration.

---

## Phase 1: Specification Contract, Not Documentation Ceremony

Phase 1 updates documentation, but it is not a ceremonial "docs first" phase.
It converts the Phase 0 evidence ledger into a binding implementation contract.
Every document update must answer exactly what code will later do, what it will
not do, and which tests prove it.

### 1.1. Master plan document requirements

`docs/plans/INCURATOR_SYSTEM_BUILD.md` must remain the top-level build plan.
It must not only say that a feature exists. It must preserve:

- exact current layout
- exact target layout
- exact transition commands
- exact path offset reasoning
- exact DB DDL
- exact MCP tool contracts
- exact plugin build/deploy behavior
- exact validation commands
- exact rollback plan
- exact known blockers

The document must explicitly distinguish:

- current reality
- target architecture
- transition mechanism
- irreversible operations
- reversible operations
- tests
- manual acceptance
- open questions

No section may say "update docs" without naming the documents and the semantic
changes required.

### 1.2. System behavior spec

Create or update:

`docs/spec/system_behavior/incurator_v0.2.0.md`

This document must define the backend/client architecture in behavioral terms,
not only in directory terms.

Required content:

- Incurator backend as source-of-truth.
- Obsidian plugin as client.
- MCP as the primary client/backend boundary.
- CLI as operator/admin boundary.
- `.curator` as generated machine state.
- `03_Notes` immutability.
- `04_Resources` copy-mode immutability.
- external reference-mode policy.
- Zotero/iPad annotation flow.
- hash drift and path drift detection.
- human-approved rebind.
- platform-specific path isolation.
- no silent fallback from invalid `VAULT_ROOT`.
- no autonomous source rewriting.

The spec must include both AS-IS and TO-BE, but it must avoid saying TO-BE has
already happened until implementation phases actually complete.

### 1.3. Schema spec

Create or update:

`docs/spec/curator_schema/SCHEMA_v0.2.0.md`

This document must define additive DB changes in executable form.

Required DDL concepts:

```sql
ALTER TABLE sources ADD COLUMN external_path TEXT;
ALTER TABLE sources ADD COLUMN is_reference INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sources ADD COLUMN logical_source_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_sources_logical_source_id
ON sources(logical_source_id)
WHERE logical_source_id IS NOT NULL AND logical_source_id != '';
```

If the current implementation already added `import_origin` and
`import_policy`, the schema document must reconcile that with the intended
v0.2.0 fields. It must say whether those fields are transitional, permanent, or
subsumed by `external_path`, `is_reference`, and `logical_source_id`.

The schema spec must include:

- migration idempotency rules
- WAL policy
- foreign key policy
- source page provenance table policy
- page-level PDF provenance meaning
- reference source invariants
- rebind transaction invariants

### 1.4. MCP scenario spec

Update:

`docs/spec/system_behavior/mcp_scenarios.md`

Required tools and scenarios:

- `curator_source_status`
- `curator_import_source`
- `curator_ingest_source`
- `curator_search_source`
- `curator_get_pdf_page`
- `curator_get_provenance`
- `curator_list_external_resources`
- `curator_rebind_source`

For every tool, specify:

- whether it mutates state
- whether it can touch external files
- whether it can write vault-local files
- required human confirmation
- return shape
- error shape
- path handling
- `VAULT_ROOT` behavior
- idempotency behavior

The scenario doc must include full flows:

1. Vault-local PDF copy import.
2. Zotero reference import.
3. Existing source status lookup.
4. Missing external path lookup.
5. Path moved but same hash found.
6. Hash drift at same path.
7. Hash drift plus path drift.
8. Human accepts rebind.
9. Human rejects rebind.
10. Bad `VAULT_ROOT`.

### 1.5. User guide updates

Update:

- `docs/guides/USER_GUIDE.md`
- `docs/guides/MCP_USER_GUIDE.md`
- `docs/guides/MCP_USER_GUIDE_EN.md`

The user guide must not hide the distinction between copy mode and reference
mode. It must explicitly tell the user:

- If the PDF is managed by Zotero and annotated from iPad, use reference mode.
- If the PDF is a standalone file the user wants in the vault, use copy mode.
- If a source is moved, the system will ask before rebinding.
- If a source hash changes, the system will ask whether to treat it as an
  updated source.
- The backend will not rewrite `03_Notes`.
- The plugin displays backend status but does not own backend state.

### 1.6. Developer guide updates

Update:

- `docs/guides/DEV_SCRIPTS_SPEC.md`
- `docs/guides/CONTRIBUTION_GUIDE.md`
- `docs/guides/CONTRIBUTION_GUIDE_EN.md`
- `README.md`
- `README_EN.md`
- `AGENTS.md`
- `CLAUDE.md`
- `GEMINI.md`

Required content:

- monorepo target layout
- actual current layout until migration is complete
- how to run backend tests
- how to run plugin build
- how to run qmd tests
- how to deploy plugin to Obsidian without symlinks
- how to set `OBSIDIAN_PLUGIN_DIR`
- how to keep machine-specific paths outside synced vault config
- how to avoid modifying production vault data during tests

### 1.7. Documentation validation gate

Phase 1 is complete only when:

- Every changed doc uses current canonical names.
- No doc refers to `obsidian-ai-agent` as the current plugin.
- Every doc that mentions moved paths distinguishes current path from target
  path.
- Every new tool in docs has either implementation planned or explicitly
  marked pending.
- Every schema claim has matching DDL or a clear future migration phase.
- The master plan includes rollback instructions before destructive commands.

---

## Phase 2: Repository Provenance And Monorepo Scaffolding

Phase 2 moves repository structure. It must be isolated from backend behavior
changes and plugin feature changes. This phase is about file ownership,
history, and deploy topology.

### 2.1. Decide plugin import strategy

There are three possible plugin source situations. Phase 2 must choose the one
that matches Phase 0 evidence.

Case A: plugin remote exists and is authoritative.

Use subtree import:

```bash
cd /home/shin/Workspace/Incurator
git subtree add \
  --prefix=plugin \
  https://github.com/ShinYwings/incurator-obsidian-agent.git \
  main \
  --squash
```

Case B: plugin source currently exists only in the vault folder and must be
copied into the monorepo.

Use `git mv` only if the plugin folder is inside the same repository. If it is
in another repository or untracked vault folder, copy with explicit provenance:

```bash
mkdir -p /home/shin/Workspace/Incurator/plugin
rsync -a \
  --exclude node_modules \
  --exclude .git \
  /home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent/ \
  /home/shin/Workspace/Incurator/plugin/
```

Then record in the commit message that plugin history was not preserved because
the source was imported from the vault deployment folder.

Case C: plugin already exists in `plugin/`.

Do not re-import. Verify and proceed.

### 2.2. Backend relocation

Target layout:

```text
Incurator/
├── backend/
│   ├── src/
│   │   ├── curator/
│   │   └── qmd/
│   ├── tests/
│   ├── pyproject.toml
│   ├── install.sh
│   └── uv.lock
├── plugin/
├── docs/
├── scripts/
├── README.md
├── README_EN.md
├── AGENTS.md
├── CLAUDE.md
└── GEMINI.md
```

If the backend is currently root-based, use `git mv` to preserve history:

```bash
cd /home/shin/Workspace/Incurator
mkdir -p backend
git mv src backend/src
git mv tests backend/tests
git mv pyproject.toml backend/pyproject.toml
git mv install.sh backend/install.sh
git mv uv.lock backend/uv.lock
```

Do not move `docs/`, `scripts/`, root agent rule files, or README files unless
the docs explicitly say the target root no longer owns them.

### 2.3. second_brain deployment folder conversion

The vault plugin folder must become a compiled deployment target, not the source
repository.

Before removing anything:

```bash
cd /home/shin/Workspace/second_brain
mkdir -p /tmp/incurator-plugin-v0.2-backup
cp -a .obsidian/plugins/incurator-obsidian-agent/data.json \
  /tmp/incurator-plugin-v0.2-backup/data.json 2>/dev/null || true
cp -a .obsidian/plugins/incurator-obsidian-agent/manifest.json \
  /tmp/incurator-plugin-v0.2-backup/manifest.json 2>/dev/null || true
cp -a .obsidian/plugins/incurator-obsidian-agent/main.js \
  /tmp/incurator-plugin-v0.2-backup/main.js 2>/dev/null || true
cp -a .obsidian/plugins/incurator-obsidian-agent/styles.css \
  /tmp/incurator-plugin-v0.2-backup/styles.css 2>/dev/null || true
```

If it is a submodule:

```bash
git rm --cached .obsidian/plugins/incurator-obsidian-agent
```

Then edit `.gitmodules` and remove only the matching submodule block.

Deployment target after conversion:

```text
second_brain/.obsidian/plugins/incurator-obsidian-agent/
├── main.js
├── manifest.json
├── styles.css
└── data.json
```

No `src/`, no `node_modules/`, no plugin `.git/`.

### 2.4. Phase 2 validation

Run:

```bash
cd /home/shin/Workspace/Incurator
git status --short
test -d backend/src/curator
test -d backend/src/qmd
test -d plugin/src
```

The commit for Phase 2 must be structural only. It must not also change DB
schema, MCP behavior, provider behavior, or PDF extraction logic.

---

## Phase 3: Exhaustive Backend Path Migration

Phase 3 makes the moved backend runnable. It must not add new product behavior
except what is necessary to preserve the old behavior from the new path.

### 3.1. `backend/pyproject.toml`

The build hook path must point to the root scripts directory:

```toml
[tool.hatch.build.hooks.custom]
path = "../scripts/build/hatch_build.py"
```

Package paths remain relative to `backend/`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/curator"]

[tool.hatch.build.targets.wheel.force-include]
"src/curator/workspace/templates" = "curator/workspace/templates"
```

### 3.2. `scripts/build/hatch_build.py`

The root resolution must be explicit:

```python
def _repo_root(root: str | Path | None = None) -> Path:
    if root is not None:
        return Path(root).resolve()
    return Path(__file__).resolve().parents[2]
```

The qmd path must support both target and legacy layouts during transition:

```python
def _qmd_dir(root: str | Path | None = None) -> Path:
    repo = _repo_root(root)
    candidate = repo / "backend" / "src" / "qmd"
    if candidate.exists():
        return candidate
    return repo / "src" / "qmd"
```

### 3.3. `backend/install.sh`

When executed from `backend/`, the build hook is one directory up:

```bash
python ../scripts/build/hatch_build.py
```

Create a root wrapper:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/backend"
bash install.sh
```

### 3.4. Python path offset audit

Every `Path(__file__).resolve().parents[N]` must be audited.

Known required changes after moving `src/curator` to `backend/src/curator`:

`backend/src/curator/testbed_manager.py`

```python
return Path(__file__).resolve().parents[3] / "scripts" / "dev"
```

Reasoning:

```text
backend/src/curator/testbed_manager.py
parents[0] = backend/src/curator
parents[1] = backend/src
parents[2] = backend
parents[3] = Incurator
```

`backend/src/curator/cli.py` benchmark path:

If the code intentionally points outside the repo to `/home/shin/Workspace`,
the offset changes from `parents[3]` to `parents[4]`. If that external
benchmark assumption is accidental, Phase 3 must stop and redesign it instead
of blindly preserving it.

### 3.5. Backend migration validation

Run from monorepo root:

```bash
cd /home/shin/Workspace/Incurator/backend
python -m compileall src/curator
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests
```

Run qmd:

```bash
cd /home/shin/Workspace/Incurator/backend/src/qmd
npm run build
npx vitest run --reporter=verbose test/
```

Run testbed:

```bash
cd /home/shin/Workspace/Incurator/backend
wiki testbed init testbed_template --force
VAULT_ROOT=/home/shin/Workspace/Incurator/testbed wiki status
VAULT_ROOT=/home/shin/Workspace/Incurator/testbed wiki add
VAULT_ROOT=/home/shin/Workspace/Incurator/testbed wiki sync
VAULT_ROOT=/home/shin/Workspace/Incurator/testbed wiki lint
VAULT_ROOT=/home/shin/Workspace/Incurator/testbed wiki query "Summarize the testbed knowledge."
```

If `wiki` still resolves to a previously installed package, reinstall:

```bash
cd /home/shin/Workspace/Incurator/backend
uv pip install -e .
```

---

## Phase 4: Plugin Build, Deploy, And Local Development Workflow

Phase 4 makes plugin development immediate without symlink and without plugin
source living in `second_brain`.

### 4.1. Required behavior

From:

```bash
cd /home/shin/Workspace/Incurator/plugin
npm run dev
```

The developer should be able to build in watch mode.

If `OBSIDIAN_PLUGIN_DIR` is set, build outputs go directly to:

```text
$OBSIDIAN_PLUGIN_DIR/main.js
$OBSIDIAN_PLUGIN_DIR/manifest.json
$OBSIDIAN_PLUGIN_DIR/styles.css
```

If `OBSIDIAN_PLUGIN_DIR` is not set, build outputs remain local:

```text
plugin/main.js
plugin/manifest.json
plugin/styles.css
```

### 4.2. `plugin/esbuild.config.mjs`

The build config must compute:

```js
const pluginDir = process.env.OBSIDIAN_PLUGIN_DIR;
const outfile = pluginDir ? `${pluginDir}/main.js` : "main.js";
```

It must also copy or emit:

- `manifest.json`
- `styles.css`

to the same target directory when `OBSIDIAN_PLUGIN_DIR` is set.

It must create the target directory if missing.

It must not copy:

- `src/`
- `node_modules/`
- `.git/`
- test files
- TypeScript config

### 4.3. `plugin/package.json`

Required scripts:

```json
{
  "scripts": {
    "dev": "node esbuild.config.mjs",
    "build": "tsc --noEmit && node esbuild.config.mjs --production",
    "deploy": "node scripts/deploy.mjs"
  }
}
```

If the current plugin already has equivalent scripts, do not rename them unless
there is a concrete reason. The important property is behavior, not naming.

### 4.4. Root `setup.sh`

Root setup must orchestrate both backend and plugin without hiding failures:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "=== Backend editable install ==="
cd "$ROOT/backend"
if command -v uv >/dev/null 2>&1; then
  uv pip install -e .
else
  pip install -e .
fi

echo "=== Plugin dependencies ==="
cd "$ROOT/plugin"
npm install
npm run build
```

If `OBSIDIAN_PLUGIN_DIR` is required for deployment, setup must say so clearly.
It must not guess a vault path.

### 4.5. Plugin validation

```bash
cd /home/shin/Workspace/Incurator/plugin
npx tsc --noEmit
npm run build
OBSIDIAN_PLUGIN_DIR=/home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent npm run build
test -f /home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent/main.js
test -f /home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent/manifest.json
test -f /home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent/styles.css
```

---

## Phase 5: Platform-Aware Configuration

Phase 5 removes machine-specific absolute paths from synced vault state.

### 5.1. Global config file

Use:

```text
~/.config/curator/config.yml
```

Proposed schema:

```yaml
external:
  zotero:
    roots:
      - "~/Zotero/storage"
      - "~/Documents/Zotero"
    enabled: true

paths:
  wiki_binary: "wiki"
  obsidian_plugin_dir: "~/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent"
```

The global config is machine-local. It must not be stored inside the synced
vault unless the user explicitly opts into that.

### 5.2. Vault config remains portable

`.curator/config.yml` may store logical preferences:

- enabled external providers
- source policies
- persona
- raw dirs
- collections dir

It must not store a Linux-only or macOS-only absolute Zotero path as the only
source of truth.

### 5.3. Plugin settings

If plugin settings need binary paths, they must support platform-specific
fields:

- Linux binary path
- macOS binary path
- Windows path if future support is desired

At runtime, the plugin chooses based on `process.platform`.

### 5.4. Validation

On Linux:

```bash
wiki config get external.zotero.roots
wiki config set external.zotero.roots "$HOME/Zotero/storage"
```

On macOS:

```bash
wiki config set external.zotero.roots "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Zotero"
```

The resulting synced vault files must not fight each other across machines.

---

## Phase 6: External Resource Reference Mode And Hash Healing

Phase 6 adds the core v0.2.0 product behavior for Zotero and external PDFs.

### 6.1. DB fields

Add to `sources`:

```sql
external_path TEXT
is_reference INTEGER NOT NULL DEFAULT 0
logical_source_id TEXT
```

Add index:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_sources_logical_source_id
ON sources(logical_source_id)
WHERE logical_source_id IS NOT NULL AND logical_source_id != '';
```

If previous transitional fields exist:

- `import_origin`
- `import_policy`

Keep them until a deliberate cleanup migration. Do not remove them during the
same phase that introduces reference mode.

### 6.2. Reference import behavior

`curator_import_source(policy="reference")` must:

1. Accept an absolute external file path.
2. Verify the file exists.
3. Verify the extension is supported.
4. Parse or hash the source.
5. Create or update a `sources` row with:
   - `is_reference=1`
   - `external_path=<absolute path hint>`
   - `logical_source_id=<stable id>`
   - `content_hash=<current bytes hash>`
6. Avoid copying the binary into `04_Resources`.
7. Optionally create a proxy markdown note if the UI requires a vault anchor.
8. Return status including:
   - `source_id`
   - `logical_source_id`
   - `external_path`
   - `content_hash`
   - `state`
   - `requires_rebind`

### 6.3. Copy import behavior

`curator_import_source(policy="copy")` must:

1. Copy the file into `04_Resources` or a user-chosen subfolder.
2. Never overwrite existing files.
3. Deduplicate by content hash.
4. Register the copied vault-local path.
5. Set `is_reference=0`.

### 6.4. Source status behavior

`curator_source_status` must handle:

- source id lookup
- vault-relative relpath lookup
- absolute external path lookup
- logical source id lookup

For reference sources:

1. Check `external_path`.
2. If present and file exists, hash it.
3. If hash matches DB, return `indexed` or current layer state.
4. If hash differs, return `hash_drift`.
5. If path missing, search configured external roots by logical source id or
   filename/hash hints.
6. If moved and same hash found, return `moved`.
7. If moved and hash differs, return `moved_and_hash_drift`.
8. If unresolved, return `missing`.

No status call may silently update DB identity. Status is observation. Rebind is
a separate human-approved mutation.

### 6.5. Rebind behavior

`curator_rebind_source` must:

1. Require source id or logical source id.
2. Require new path or confirmed candidate.
3. Require explicit `apply=true`.
4. Recalculate hash.
5. Record old path/hash in an audit log.
6. Update `external_path`.
7. Update `content_hash` only if the user confirms the new bytes represent the
   same logical source after annotation or movement.
8. Mark the source pending if content changed.
9. Never edit the external file.
10. Never edit `03_Notes`.

### 6.6. External resources listing

`curator_list_external_resources` must return configured roots:

```json
{
  "resources": [
    {
      "name": "zotero",
      "enabled": true,
      "roots": ["/home/shin/Zotero/storage"],
      "exists": true
    }
  ]
}
```

### 6.7. Validation

Tests must cover:

- reference import stores external path and does not copy binary
- copy import stores vault-local copied path
- duplicate reference import deduplicates logical source
- moved source returns moved
- hash drift returns hash_drift
- rebind updates path only after explicit apply
- bad external root produces clear error
- source status never mutates by observation alone

---

## Phase 7: Obsidian Client Integration

Phase 7 wires the plugin to backend reference/copy import and source status.

### 7.1. PDF chip backend states

PDF chips should show:

- untracked
- reference
- copied
- queued
- extracting
- L1
- L2
- L3
- indexed
- curated
- hash drift
- moved
- missing
- error

The chip label must not lose page identity. Backend status is separate from:

- file label
- page number
- pinned state
- active/open-tab state

### 7.2. Ingest modal

The modal must ask:

- Reference mode or copy mode?
- If copy mode, which `04_Resources` subfolder?
- If reference mode, which external library/root?
- If linked to an active `03_Notes/<domain>/<note>.md`, should copy-mode
  default to `04_Resources/<domain>/<note>/`?
- If Zotero path is detected, should reference mode be recommended?

Default recommendation:

- Zotero-managed absolute PDF: reference mode.
- Vault-local PDF already in `04_Resources`: register in place.
- External non-Zotero PDF: ask, with copy mode default if no external root
  matches.

### 7.3. Provider context

For questions about the current PDF, the plugin may use local immediate PDF
context:

- current page
- neighboring pages
- outline
- local PDF RAG hits

For durable knowledge, the plugin uses Incurator MCP:

- source status
- source page search
- `search_curator`
- provenance traversal

The prompt must distinguish:

```xml
<pdf_window>
...
</pdf_window>

<pdf_rag_hits>
...
</pdf_rag_hits>

<incurator_hits>
...
</incurator_hits>
```

Local PDF context is not the same as durable Curator knowledge. The model must
not imply that an un-ingested PDF is already in the Curator DAG.

### 7.4. Human-in-the-loop rebind UI

If backend returns:

- `moved`
- `hash_drift`
- `moved_and_hash_drift`

the plugin must show a confirmation UI. It must include:

- old path
- new candidate path
- old hash
- new hash
- source title
- current DB state
- consequence of accepting
- consequence of rejecting

The plugin must call `curator_rebind_source(apply=true)` only after explicit
user confirmation.

---

## Phase 8: End-To-End Verification

### 8.1. Backend verification

```bash
cd /home/shin/Workspace/Incurator/backend
python -m compileall src/curator
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests
ruff check src/curator
```

If full pytest is blocked by global plugins, run with plugin autoload disabled
and record the blocker.

### 8.2. QMD verification

```bash
cd /home/shin/Workspace/Incurator/backend/src/qmd
npm run build
npx vitest run --reporter=verbose test/
```

### 8.3. Plugin verification

```bash
cd /home/shin/Workspace/Incurator/plugin
npx tsc --noEmit
npm run build
OBSIDIAN_PLUGIN_DIR=/home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent npm run build
```

### 8.4. Testbed verification

```bash
cd /home/shin/Workspace/Incurator/backend
wiki testbed init testbed_template --force
VAULT_ROOT=/home/shin/Workspace/Incurator/testbed wiki status
VAULT_ROOT=/home/shin/Workspace/Incurator/testbed wiki add
VAULT_ROOT=/home/shin/Workspace/Incurator/testbed wiki sync
VAULT_ROOT=/home/shin/Workspace/Incurator/testbed wiki lint
VAULT_ROOT=/home/shin/Workspace/Incurator/testbed wiki query "Summarize the core concepts in this vault."
```

### 8.5. Manual Obsidian verification

Open Obsidian and verify:

1. Markdown note and PDF split view both produce active purple chips.
2. Pinned PDF chips survive query-line context operations.
3. External Zotero PDF recommends reference mode.
4. External non-Zotero PDF asks copy vs reference.
5. Copy mode proposes `04_Resources/<mirrored note folder>/<note title>/`.
6. Reference mode does not copy the PDF into `04_Resources`.
7. Backend status badge updates.
8. `search_curator` is actually callable by the selected provider.
9. Bad `VAULT_ROOT` returns visible error.
10. Hash drift produces confirmation UI, not silent mutation.
11. Rebind requires explicit confirmation.
12. Provider switching does not lose context.
13. LaTeX rendering and copy remain correct.

---

## Phase 9: Commit And Release Discipline

Use small commits. Do not combine unrelated risk domains.

Recommended commit order:

1. `docs: capture v0.2 evidence-led build plan`
2. `docs: add v0.2 behavior and schema contracts`
3. `chore: import plugin into monorepo`
4. `refactor: move backend into backend directory`
5. `fix: update backend path resolution for monorepo`
6. `build: add plugin deploy workflow`
7. `feat: add platform-aware curator config`
8. `feat: add reference source import and status`
9. `feat: add hash drift rebind workflow`
10. `feat: wire Obsidian plugin to reference import`
11. `test: add external resource and rebind coverage`

Each commit must include tests run in the body or associated handoff note.

Do not squash the entire operation into one commit unless there is a later
manual archival reason. This migration crosses docs, git topology, Python
backend, TypeScript plugin, DB schema, and user vault deployment. One commit
would make rollback and blame analysis unnecessarily difficult.

---

## Open Questions That Must Not Be Hidden

1. What is the stable `logical_source_id` for Zotero PDFs?
   Candidate answers include Zotero item key, attachment key, BetterBibTeX
   citekey plus attachment filename, or a generated Incurator id. This must be
   decided before relying on rebind across machines.

2. Should reference sources create proxy markdown notes in `04_Resources`?
   Proxy notes help Obsidian linking and human inspection, but they must not
   pretend to be the binary source itself.

3. Should `04_Resources` remain git-tracked when it contains proxy notes?
   Large binaries should not be forced into git. Lightweight proxy notes can be.

4. How should qmd index external reference text?
   Options: index generated L1-L4 only, index raw page text separately, or both.

5. How should provider CLIs be forced to use MCP?
   The plugin can configure MCP, but provider behavior must be verified with
   actual tool-use traces.

6. Should old `import_origin` / `import_policy` columns remain permanently?
   They may be useful audit fields, but they must be reconciled with
   `external_path`, `is_reference`, and `logical_source_id`.

7. How should encrypted or scanned PDFs behave in reference mode?
   Reference registration can record the source, but extraction may require
   vision/OCR fallback and must expose quality state.

---

## Final Acceptance Criteria

The v0.2.0 build is accepted only when all of the following are true:

- Incurator repo contains backend and plugin source in a single coherent
  monorepo layout, or the plan explicitly marks the migration as pending with
  no false claim that it is complete.
- Plugin deployment to Obsidian works without symlink and without git submodule
  dependency.
- Machine-specific absolute paths live outside synced vault state.
- Zotero PDFs can be registered by reference without copying into
  `04_Resources`.
- Vault-local PDFs can still be copied/imported into `04_Resources` safely.
- Existing `04_Resources` files are never overwritten.
- `03_Notes` is never modified by MCP automation.
- Source status can distinguish indexed, untracked, moved, missing, hash drift,
  and error states.
- Rebind is human-approved and auditable.
- PDF page provenance is preserved.
- Source-specific search can return page-aware hits.
- `search_curator` still works for compiled DAG knowledge.
- Obsidian plugin shows backend status in the PDF UI.
- Current PDF questions use local PDF context immediately.
- Durable knowledge questions use Incurator backend search.
- Bad `VAULT_ROOT` fails explicitly.
- Backend tests, plugin typecheck/build, qmd build/tests, and manual Obsidian
  acceptance are recorded with results.
