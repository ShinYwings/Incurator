# docs_parity Proposal: Contract Parity Audit of CLI Surface Policy, MCP Tool List, Guide Commands, and EN↔KR Sync

Date: 2026-08-04 | Agent Persona: Contract Parity Auditor (Gate G0, `docs_parity` domain)

Scope: spec/guide claims vs code for surfaces NOT owned by the other five
inspectors — SYSTEM_BEHAVIOR §11.4 CLI surface policy, `MCP_USER_GUIDE.md` tool
list vs `mcp/server.py` registrations, `USER_GUIDE.md` / `WORKFLOW_GUIDE.md`
command+flag accuracy, and EN↔KR guide pair sync.

Method: `grep` to locate, bounded `Read` to verify, plus **read-only** in-process
`CliRunner` `--help` renders through `.venv-dev` (no vault, no `testbed/`, no
mutating `wiki` command was executed). Every finding below was cross-checked
against `backend/tests/` first; where an existing test pins behavior, the test
is cited and the claim is sharpened to name the *stale side* rather than
inventing a code defect.

---

## 1. Core Logic & Implementation

### Finding DP-1 [P2] — SYSTEM_BEHAVIOR §11.4 visible/hidden CLI inventory is inverted and incomplete vs `cli.py`

**Spec claim** — `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:1022-1037`:

```text
The normal human-facing `wiki --help` command surface should stay focused on the
daily workflow:

    init, status, add, build, query, sync, lint, reindex,
    source, jobs, config, workspace, version

Advanced or integration-only command groups remain directly callable but should
be hidden from the default help listing:

- `wiki plugin ...`   - `wiki mcp ...`   - `wiki testbed ...`   - `wiki devices ...`
```

**Code reality** — `backend/src/curator/cli.py:82-95`:

```python
app.add_typer(source_app, name="source")
app.add_typer(inspect_app, name="inspect")
app.add_typer(workspace_app, name="workspace")
app.add_typer(config_app, name="config")
app.add_typer(persona_app, name="persona")
app.add_typer(testbed_app, name="testbed", hidden=True)
app.add_typer(jobs_app, name="jobs", hidden=True)      # <-- documented as VISIBLE
app.add_typer(plugin_app, name="plugin", hidden=True)
app.add_typer(devices_app, name="devices", hidden=True)
app.add_typer(db_app, name="db")
app.add_typer(models_app, name="models", hidden=True)  # <-- hidden, undocumented
app.add_typer(prompt_app, name="prompt")
app.add_typer(insight_app, name="insight")
```

Plus `backend/src/curator/commands/core.py:1667-1679`, which registers `reset`
and `migrate` as visible top-level commands:

```python
def register_core_commands(root_app: typer.Typer) -> None:
    root_app.command('reset')(reset)
    root_app.command()(version)
    root_app.command()(init)
    root_app.command()(status)
    root_app.command('migrate')(migrate_vault)
    ...
```

**Rendered `wiki --help` (read-only `CliRunner` invoke, no vault touched)** lists
20 entries: `reset, version, init, status, migrate, add, build, update, sync,
query, reindex, lint, source, inspect, workspace, config, persona, db, prompt,
insight`.

**Existing test pins the CODE side, not the spec** —
`backend/tests/test_command_surface_characterization.py:89-93`:

```python
    hidden_groups = {
        name for name, command in root.commands.items()
        if bool(getattr(command, "hidden", False))
    }
    assert hidden_groups == {"devices", "jobs", "mcp", "models", "plugin", "testbed"}
```

and `backend/tests/test_cli_update.py:39-48`:

```python
def test_jobs_group_is_hidden_but_functional() -> None:
    ...
    assert "jobs" not in top.output
```

So the spec is the stale side on every axis:

| Axis | §11.4 says | Reality (`cli.py` + characterization test) |
|---|---|---|
| `jobs` | visible daily-workflow command | `hidden=True` (`cli.py:88`) |
| `models` | not mentioned at all | hidden (`cli.py:92`) |
| hidden set | `{plugin, mcp, testbed, devices}` | `{devices, jobs, mcp, models, plugin, testbed}` |
| visible set | 13 names | 20 names; **7 undocumented**: `reset`, `migrate`, `inspect`, `persona`, `db`, `prompt`, `insight` |

**Failure scenario (concrete):** a user or an external agent reads §11.4 —
declared authoritative by CLAUDE.md ("Specs are authoritative… spec-vs-code
divergence is a finding even when the code works") — and runs `wiki jobs list`
expecting a documented, discoverable command; `wiki --help` never lists it, so
the group looks removed. Conversely an agent auditing the surface for "new
top-level public command groups" (§11.4:1047-1048 makes that a *normative* rule:
"Plugin-local JSON commands must be added under `wiki plugin ...` rather than as
new top-level public command groups") has no way to tell whether `db`, `prompt`,
`insight`, `persona`, and `inspect` were sanctioned additions or policy
violations, because the policy's own inventory was never updated when they
landed. `wiki db` in particular is a first-class user-facing group with a whole
`USER_GUIDE.md` chapter (`docs/guides/USER_GUIDE.md:789-885`, "기기 간 지식
동기화 / cross-device sync") yet is absent from the spec's public surface list.

**Verified-clean sub-claim (not a finding):** §11.4:1036-1037 says "Running
`wiki devices` without a subcommand is equivalent to `wiki devices status`."
Confirmed correct — `backend/src/curator/commands/devices.py:91-95`:

```python
@devices_app.callback(invoke_without_command=True)
def devices_default(ctx: typer.Context) -> None:
    ...
        devices_status()
```

**Fix direction:** rewrite §11.4's two lists from `cli.py:82-95` +
`core.py:1667-1679`. Visible: `init, status, add, build, update, sync, query,
reindex, lint, source, inspect, workspace, config, persona, db, prompt, insight,
reset, migrate, version`. Hidden: `plugin, mcp, testbed, devices, jobs, models`
(each with a one-line rationale, matching the existing `plugin`/`mcp` style).
Optionally extend `test_command_surface_characterization.py` with a doc-parity
assertion so §11.4 cannot silently drift again — that file already owns the
canonical inventory, so the spec list can be asserted against it.

---

### Finding DP-2 [P2] — §11.4 declares `wiki update` non-public; code, tests, and `USER_GUIDE.md` all say it is the primary everyday command

**Spec claim** — `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:1039-1041`:

```text
The frozen-staging command family is **removed** in v0.3.1: the L4 layer is the shared
Synthesis layer (built automatically by `wiki build`) and curation is a dynamic
query-time lens (`wiki query`). `wiki update` is not part of the public CLI.
```

**Code reality** — `backend/src/curator/commands/core.py:1675`:

```python
    root_app.command()(update)
```

No `hidden=True`. The rendered `wiki --help` shows
`update  Bring the vault fully up to date in one step.`

**Tests pin the opposite of the spec** —
`backend/tests/test_command_surface_characterization.py:118-128`:

```python
def test_cli_help_and_hidden_commands_are_stable() -> None:
    ...
    assert "plugin" not in clean_root
    assert "mcp" not in clean_root
    assert "jobs" not in clean_root
    assert "update" in clean_root
```

and `backend/tests/test_cli_update.py:1-7`, whose module docstring states the
intended contract outright: "`wiki update` is the one-shot pipeline (add ->
build -> embed -> sync)."

**Guide reality** — `docs/guides/USER_GUIDE.md:715` documents it as the flagship
command:

```text
| `wiki update` | **One-shot pipeline**: runs `add` → `build --wait` → vector embeddings → `sync` synchronously … | The everyday "just make it current" command |
```

and `docs/guides/USER_GUIDE.md:143` steers users to it directly.

**Failure scenario (concrete):** an external agent (Claude Code / Antigravity)
following the repo's own docs-hierarchy rule — "When they conflict, the more
concrete layer (spec) dictates the implementation reality" — reads §11.4:1041,
concludes `wiki update` is a retired private command, and instead emits the
three-command `add`/`build --wait`/`sync` sequence, losing the
`_maybe_auto_export` step that `update` performs
(`test_cli_update.py:192-203` asserts `auto_export.assert_called_once()`).
A stricter agent could go further and "clean up" the non-public command. This is
a three-way conflict in which the spec is the sole dissenter, and CLAUDE.md
states that any divergence means "both are wrong until reconciled."

**Fix direction:** delete the sentence "`wiki update` is not part of the public
CLI." from §11.4 and add `update` to the visible-surface list in DP-1's rewrite,
describing it as the one-shot `add → build → embed → sync` pipeline consistent
with `USER_GUIDE.md:715`. This is a pure spec edit — no code changes; the code
side is already pinned by two tests.

---

### Finding DP-3 [P3] — `WORKFLOW_GUIDE_KR.md` carries an entire behavioral section (§6-1 background-processing monitoring) with no English counterpart

**KR-only content** — `docs/guides/WORKFLOW_GUIDE_KR.md:358-399`:

```markdown
## 6-1. 백그라운드 처리 모니터링

플러그인 Add Source 또는 `wiki build`가 queue에 넣은 L2/L3 작업은 MCP 서버의
IngestWorker 스레드, `wiki jobs run`, 또는 Dashboard의 **Run queued**가 처리합니다.
진행 상황을 확인하는 방법은 세 가지다.

### 방법 1: Incurator Dashboard (Obsidian)   … (dashboard.md Active/Queue/Completed layout)
### 방법 2: wiki status (CLI)                 … (Background jobs section)
### 방법 3: 플러그인 상태 바                   … (`⚡ 2 running / 1 queued`, click opens dashboard.md)
```

**English counterpart: absent.** `grep -n "Monitoring\|Background Processing\|6-1"
docs/guides/WORKFLOW_GUIDE.md` returns nothing. The EN heading sequence goes
`## 6. Agent Workflows` (`WORKFLOW_GUIDE.md:296`) → `### Key MCP Tools`
(`:354`) → `## 7. Installation Flow` (`:373`); the KR file inserts §6-1 between
`### 주요 MCP 도구` (`:340`) and `## 7. 설치 흐름` (`:401`). Structural heading
counts confirm the asymmetry: EN 67 headings / KR 76.

**Contract violated** — `CLAUDE.md`, Documentation Requirements: "edit the
English guide first as the source text, then update the matching `_KR.md` guide
as a faithful translation. Do not use the Korean guide as the canonical source
for new behavior." and "If a `_KR.md` guide changes, the matching English guide
must change in the same commit unless the edit is Korean-only wording with no
behavioral meaning." §6-1 is unambiguously behavioral: it names three concrete
observation surfaces (`dashboard.md` and its exact table layout, the
`Background jobs` section of `wiki status`, and the plugin status-bar
`⚡ N running / M queued` indicator with its click-to-open action).

**Failure scenario (concrete):** an English-reading user (or any agent that
reads only the canonical EN guide, per the "EN is the source text" rule) has no
documented way to discover that queued L2/L3 work is observable at all. They run
`wiki build`, see it return, and have no pointer to `dashboard.md`, to the
`wiki status` background-jobs section, or to the status-bar indicator — the
three surfaces the KR guide treats as the standard answer to "is it still
working?". Additionally, any future change to the status-bar string or the
dashboard layout will be updated in EN (where it does not exist) and silently
rot in KR, since the KR section has no EN anchor to keep it honest.

**Fix direction:** back-port §6-1 into `WORKFLOW_GUIDE.md` as `## 6-1.
Monitoring Background Processing` at the same position (between "Key MCP Tools"
and "7. Installation Flow"), verifying the three surfaces against the current
plugin/dashboard code before translating, then re-align the KR section to the
new EN source text. Do **not** resolve this by deleting the KR section — that
would be the lossy-compression anti-pattern CLAUDE.md §6 forbids.

---

## 2. Pros & Cons

### 2.1 What I verified CLEAN (no finding — reported so the gate is closable)

**MCP tool list vs `mcp/server.py` — exact parity, zero drift.** I extracted all
48 `@mcp.tool()` registrations programmatically from
`backend/src/curator/mcp/server.py` (walking forward from each decorator to its
`def`, so multi-line decorator bodies are not missed) and diffed against every
tool identifier mentioned in `docs/guides/MCP_USER_GUIDE.md`. Result:

- **Documented but absent: none.** Two apparent gaps resolved on inspection:
  `curator_update_artist_persona` (`server.py:333`) and
  `curator_update_curator_persona` (`server.py:419`) are module-level functions
  registered late via the explicit-call form at `server.py:3346-3350`
  (`mcp.tool()(curator_update_artist_persona)`), not the decorator form, so a
  naive decorator grep under-reports them. The third apparent gap,
  `curator_search_source` (singular), appears only inside a *negative*
  statement at `MCP_USER_GUIDE.md:164` — "The singular alias
  `curator_search_source` was removed in v0.2.1" — which is accurate.
- **Implemented but undocumented: none.** All 48 registered tools appear in the
  guide.
- **EN↔KR MCP tool parity: exact.** `diff` of the tool-identifier sets extracted
  from `MCP_USER_GUIDE.md` and `MCP_USER_GUIDE_KR.md` is empty (both 65
  headings).

Note this does **not** contradict the pre-recorded CAND-05, which is about stale
*payload examples* in `SCHEMA.md §7`, a different surface from the tool roster.

**`USER_GUIDE.md` / `WORKFLOW_GUIDE.md` command names — clean.** Every
`wiki <group> <sub>` form mentioned in the two guides resolves to a real
registration: `wiki source retry` (`commands/sources.py:278`), `wiki prompt
show`/`eval` (`commands/prompts.py:27,56`), `wiki testbed list`
(`commands/workspace.py:237`), `wiki plugin models refresh`
(`commands/plugin.py:947`). The only guide mention of a non-existent command,
`wiki paths` at `USER_GUIDE.md:213-216`, is itself a *negative* statement
("Incurator exposes no `wiki paths` migration command"), which is correct and is
pinned by `backend/tests/test_cli_update.py:51-59`
(`test_paths_migration_group_is_removed`). `wiki repos`, `wiki commands`, `wiki
sync default`, and `wiki init updates` were false positives from my regex —
each is English/Korean prose, not a command.

**Documented CLI flags — 15/15 exist.** I extracted every `wiki <cmd> … --flag`
pattern from both guides and verified each against the live `--help` output via
read-only `CliRunner`: `build --wait`, `config provider --primary`, `config set
--local`, `db autosync --dry-run`, `db export --compress/--out/--since`, `models
ensure --smoke`, `persona update --workspace`, `query --workspace`, `reindex
--embed`, `reset --force`, `status --json`, `sync --full`, `sync --reemit`. All
present, all exit 0. No flag drift.

**EN↔KR sampling — 2 of 3 pairs clean.** `MCP_USER_GUIDE` (65/65 headings,
identical tool sets) and `SYNC_IGNORE_GUIDE` (25/25 headings) show no structural
divergence. Only `WORKFLOW_GUIDE` (DP-3) has a missing-section asymmetry.

### 2.2 What I could NOT verify (limitations to state honestly)

- **README / setup accuracy.** The domain brief names `README`/setup accuracy as
  in-scope, but **there is no `README*` file at the repository root** (`ls
  README*` → no matches). Nothing to audit; not a finding, but the gate cannot
  claim coverage of a document that does not exist. (Whether the project *should*
  have a README is a product decision, not a parity defect.)
- **EN↔KR semantic parity below the section level.** I compared heading
  structure, tool/command identifiers, and — for `WORKFLOW_GUIDE` — actual
  section content. I did **not** perform a sentence-by-sentence semantic diff of
  ~5,000 combined lines of Korean prose. `PLUGIN_GUIDE` (1698 EN / 1457 KR
  lines, 60/60 headings) and `USER_GUIDE` (1109 EN / 1066 KR lines) have equal
  heading counts, but a 240-line body-text gap in `PLUGIN_GUIDE` is large enough
  that a paragraph-level omission could hide inside a matched heading. Naive
  `^#` counting is unreliable here because bash-comment lines inside fenced code
  blocks are miscounted as headings — I confirmed DP-3 by reading the actual
  section body rather than trusting the count. A deeper KR body-text sweep is
  worth a follow-up pass but exceeded this gate's token budget.
- **`docs/philosophy/` and `docs/specs/plugin_schema/`** were out of my domain
  (owned by `plugin_lifecycle`) and were not audited.
- **Guide *behavioral* accuracy** (does `wiki sync --full` actually do what the
  guide's prose says?) is out of scope for a parity gate — I verified that every
  documented command/flag/tool **exists**, not that its runtime semantics match
  the description. Semantics for the pipeline, sync/db, retrieval, and plugin
  surfaces belong to the other four inspectors.

### 2.3 Severity calibration and honest downgrades

DP-1 and DP-2 are rated **P2 (contract violation)** rather than P3 because
§11.4 is *normative policy text*, not descriptive prose: it dictates where new
command groups may be added (`:1047-1048`) and the repo's own rule makes specs
authoritative over guides. A spec whose inventory is wrong in both directions
cannot enforce the policy it states. They are **not** P1 — no user-visible
breakage occurs, every command still works, and the guides (which most humans
actually read) are correct.

DP-3 is **P3** — a documentation-completeness gap in the non-canonical direction,
with a clear workaround (the KR guide, `wiki status`, or the plugin UI itself).

I deliberately did **not** report the following, which a less disciplined pass
might have inflated into findings: heading-count deltas between EN and KR pairs
where the delta is an artifact of counting `#` comments inside code fences;
line-count differences attributable to Korean's higher information density per
line; wording, tone, or example-value differences between EN and KR; and the
`curator_search_source` / `wiki paths` mentions, both of which are accurate
negative statements. Per the gate's instructions, three findings from four target
areas — with two areas returning genuinely clean — is the honest result.
