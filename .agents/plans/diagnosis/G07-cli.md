# Diagnosis: G07-cli
Coverage:
- `backend/src/curator/cli.py` (7,487 lines in this checkout) - parsed/structure-scanned fully; targeted line reads across app setup, config, init/status/add/build/update/jobs/sync/query/lint/workspace/persona/plugin/MCP/testbed command regions.
- Neighbor context verified only where needed to prove CLI behavior: `backend/src/curator/query.py` (`run_query` handoff), `backend/src/curator/retrieval/models.py` (`QueryRequest` fields), `backend/src/curator/config.py` (active `llm.primary` format and migration stripping nested `ollama.model`), `backend/src/curator/ingest_worker.py`/`db.py` (background-worker race shape), focused docs/tests for CLI/plugin command contracts.

## Findings

### [G07-cli-1] (a) S1 - `wiki config models use <ollama-model>` writes a legacy key that is stripped on load, so the active Ollama model does not change
- Loc: backend/src/curator/cli.py:5583, backend/src/curator/cli.py:5684, backend/src/curator/config.py:175, backend/src/curator/config.py:456
- Evidence: The CLI advertises `models_use` as "Set the active model in project config" (cli.py:5595). Cloud providers update `config["llm"]["primary"] = provider::model` (cli.py:5638-5640), but the Ollama branch writes only `config["llm"]["ollama"]["model"] = model` (cli.py:5684). The current config contract says the model lives in `llm.primary`/`llm.fallback` (config.py:175-177,193), and `_migrate_llm_config` strips nested `ollama.model` on load (config.py:456-462). Result: the command prints success, but the next `load_config` drops the value and the active Ollama model remains unchanged.
- Fix sketch: In the Ollama branch, update `config["llm"]["primary"] = cfg.join_provider_model(consts.BACKEND_OLLAMA, model)` and preserve/reset `primary_effort` appropriately. Add a regression test that initializes an Ollama primary, runs `wiki config models use <tag>`, reloads config, and asserts `llm.primary == "ollama::<tag>"`.
- Blast radius: User-facing model selection, dashboard flows that depend on CLI model changes, all local Ollama LLM calls after a model switch.
- Suggested PR: `fix(cli): persist ollama model selection in llm.primary`

### [G07-cli-2] (a/i) S2 - Ollama `ModelNotFound` recovery pulls the default model, not the missing active model
- Loc: backend/src/curator/cli.py:2037, backend/src/curator/cli.py:2057, backend/src/curator/cli.py:2059
- Evidence: `_start_client_inner` parses the configured primary provider but discards the parsed model (`primary_key, _ = split_provider_model(...)` at cli.py:2037). If the client raises `ModelNotFound`, the recovery prompt uses `llm_cfg.get("model", consts.DEFAULT_OLLAMA_MODEL)` (cli.py:2059), a legacy top-level key that is no longer canonical. For `llm.primary = "ollama::qwen2.5:14b"`, the CLI can offer `ollama pull <default>` instead of the missing `qwen2.5:14b`.
- Fix sketch: Keep `primary_model` from `split_provider_model`, and when `primary_key == "ollama"` use `primary_model or consts.DEFAULT_OLLAMA_MODEL` for the pull/retry prompt. Cover with a mocked `ModelNotFound` test.
- Blast radius: First-run local model setup and any query/build/sync command that starts an Ollama client.
- Suggested PR: `fix(cli): pull the configured ollama model on startup recovery`

### [G07-cli-3] (a/f/i) S2 - `wiki query` exposes several no-op search controls after the orchestrator migration
- Loc: backend/src/curator/cli.py:4821, backend/src/curator/cli.py:4836, backend/src/curator/cli.py:4839, backend/src/curator/cli.py:4842, backend/src/curator/cli.py:4845, backend/src/curator/cli.py:4943, backend/src/curator/query.py:496
- Evidence: The CLI validates and passes `--mode`, `--limit`, `--min-score`, `--no-rerank`, `--scope`, and workspace boost terms in `run_kwargs` (cli.py:4943-4951). `query.run_query` immediately returns `_run_query_orchestrated(...)` (query.py:496-501), whose `QueryRequest` only carries route/workspace/language fields; the legacy code that consumed these search controls begins after the unconditional return. Users can pass apparently valid flags and get unchanged retrieval behavior.
- Fix sketch: Either remove/hide the no-op flags from `wiki query`, or thread them into the orchestrator/search engine as explicit `QueryRequest` fields. Prefer a staged PR that first makes the CLI honest, then adds supported orchestrator controls deliberately.
- Blast radius: CLI query accuracy/debuggability, user trust in search tuning, docs that describe query flags.
- Suggested PR: `fix(cli): reconcile query flags with QueryOrchestrator`

### [G07-cli-4] (a/i) S2 - `--no-intent-classify` still performs an LLM intent-classification call in the CLI REPL
- Loc: backend/src/curator/cli.py:4857, backend/src/curator/cli.py:5015, backend/src/curator/cli.py:5018, backend/src/curator/cli.py:5052
- Evidence: The option help says `--no-intent-classify` skips intent classification (cli.py:4857-4860). But `_run_query_repl` always calls `intent_module.classify_intent(client, user_input)` before normal queries (cli.py:5015-5019). The later `run_query` call forcibly sets `"classify_intent_first": False` (cli.py:5052), so the flag only disables the now-dead query-layer classifier, not the live CLI-level classifier.
- Fix sketch: Add a `classify_promote_intent`/`enable_intent_classify` parameter to `_run_query_repl`. When disabled, only handle literal `save`/`save to wiki` commands with deterministic string matching and send all other input directly to `run_query`.
- Blast radius: Query latency, offline behavior, provider cost, users who explicitly request no classification.
- Suggested PR: `fix(cli): honor no-intent-classify in query repl`

### [G07-cli-5] (h/g) S2 - Default `wiki build` can spawn unbounded detached workers; concurrent L2 workers can skip the global L3 trigger
- Loc: backend/src/curator/cli.py:3224, backend/src/curator/cli.py:3291, backend/src/curator/cli.py:3310, backend/src/curator/ingest_worker.py:203, backend/src/curator/db.py:1583
- Evidence: `_spawn_background_worker` blindly starts `wiki jobs run` in a detached process (cli.py:3224-3243). `build` calls it whenever work is queued, including repeated invocations with no existing-worker check (cli.py:3291-3295,3310-3318). Job claiming is atomic, but the L3 trigger in `ingest_worker` is based on `count_active_l2_jobs` before the current job is marked done (ingest_worker.py:203-207; db.py:1583-1591). With multiple detached workers, the last two L2 jobs can both observe two active L2 jobs, both skip L3, then both finish, leaving no worker to run global L3.
- Fix sketch: Add a single-worker lease/PID lock around detached `jobs run`, or move global L3 enqueueing to an atomic transition when an L2 job is marked done and no queued/running L2 jobs remain. CLI should avoid spawning a daemon if one is already active.
- Blast radius: Background build correctness, plugin dashboard "Build" button, repeated `wiki build` invocations.
- Suggested PR: `fix(jobs): serialize background workers and atomically trigger global l3`

### [G07-cli-6] (c/e) S2 - Hidden plugin JSON commands duplicate broad `except Exception` wrappers and have inconsistent exit-code semantics
- Loc: backend/src/curator/cli.py:6202, backend/src/curator/cli.py:6312, backend/src/curator/cli.py:6536, backend/src/curator/cli.py:7136
- Evidence: The hidden plugin namespace repeats the same shape dozens of times: call a service, `_print_json(...)`, catch `Exception`, print `{"ok": false, "error": str(exc)}`. Most wrappers re-raise `typer.Exit(1)` (e.g. cli.py:6312-6314,6536-6538), but `plugin_models_pull` prints `ok:false` and does not exit nonzero (cli.py:7130-7138; existing test expects exit 0). `plugin_version` silently ignores manifest-read failures (cli.py:6173-6183). There is no shared helper to enforce JSON shape, redaction, typed errors, or exit-code policy.
- Fix sketch: Introduce a small `run_plugin_json(fn, *, exit_on_error=True, redact_paths=False)` helper and migrate wrappers incrementally. Preserve intentional exit-0 contracts only where tests/docs require them, and document those exceptions.
- Blast radius: Plugin/backend command boundary, dashboard error handling, future plugin command additions.
- Suggested PR: `refactor(cli): centralize plugin json command error handling`

### [G07-cli-7] (g/i) S2 - `wiki status` is too expensive and stateful for a frequently-polled status command
- Loc: backend/src/curator/cli.py:2777, backend/src/curator/cli.py:2782, backend/src/curator/cli.py:2797, backend/src/curator/cli.py:2940
- Evidence: `status` mutates state by calling `ingest_llm._mark_existing_l3_done_if_present(paths)` and writing runtime snapshots (cli.py:2777-2782). The human path recursively counts every file in every raw dir (`raw_dir.rglob("*")`, cli.py:2797-2800) and then runs a lint preflight (cli.py:2940-2944). The plugin dashboard intentionally calls `wiki status --json`; the JSON branch avoids the raw-file count and lint, but still writes snapshots and marks L3 done before returning.
- Fix sketch: Split read-only status snapshot construction from repair/cache writes. Make `--json` pure by default, and gate repair/cache refresh behind an explicit `--refresh` or a separate maintenance command. Cache raw-file counts if they remain useful in the human table.
- Blast radius: Dashboard responsiveness, large vault status latency, unexpected state churn from status checks.
- Suggested PR: `perf(cli): make status fast and side-effect-light`

### [G07-cli-8] (a/i) S2 - `wiki lint` mutates routing/log files even without `--fix` or `--save`
- Loc: backend/src/curator/cli.py:5329, backend/src/curator/cli.py:5359, backend/src/curator/cli.py:5363, backend/src/curator/cli.py:5366
- Evidence: The lint command is described as checking for broken links/orphans (cli.py:5352-5356). Before it runs the report, it always rebuilds index/overview/ledger and appends a log entry (cli.py:5359-5372), even for plain `wiki lint` with no `--fix` and no `--save`. This makes a diagnostic command write files and can dirty a clean vault/repo merely by checking health.
- Fix sketch: Keep `wiki lint` read-only unless `--fix`, `--save`, or a new explicit `--refresh-manifests` flag is set. If manifest freshness is required for lint correctness, compute in memory or make the write visible in the command name.
- Blast radius: CI/lint workflows, user Git cleanliness, sync tools watching `.curator/` changes.
- Suggested PR: `fix(cli): make lint read-only unless explicitly fixing or saving`

### [G07-cli-9] (d) S3 - `--backward` exits before the later generative-backprop block, leaving unreachable legacy code
- Loc: backend/src/curator/cli.py:4307, backend/src/curator/cli.py:4377, backend/src/curator/cli.py:4530
- Evidence: `sync` still exposes `--backward` (cli.py:4307-4310), then immediately warns that direct generated-L4 backprop was removed and exits (cli.py:4377-4380). Later, inside the full sync body, an `if backward and should_fix:` block still claims to execute "Multi-Agent Generative Backpropagation" (cli.py:4530-4544). That block is unreachable because every `backward=True` invocation already exited.
- Fix sketch: Delete the unreachable block and either remove/hide the `--backward` option or keep the early error as a small compatibility shim with no dead implementation below it.
- Blast radius: CLI help clarity, sync maintenance, future refactors that might accidentally revive removed backprop behavior.
- Suggested PR: `chore(cli): remove unreachable sync backward path`

### [G07-cli-10] (e/b) S2 - `cli.py` is a 7,487-line god-file with command bodies, service orchestration, plugin API, MCP setup, testbed tooling, and UI rendering interleaved
- Loc: backend/src/curator/cli.py:66, backend/src/curator/cli.py:4266, backend/src/curator/cli.py:6161, backend/src/curator/cli.py:7276
- Evidence: The module owns the root Typer app and all sub-apps (cli.py:66-260), plus large command bodies such as `sync` (352 lines), `init` (280), `status` (191), `add` (156), `workspace_init` (149), `query` (149), and `config_provider` (146). It also mixes hidden plugin JSON endpoints (cli.py:6161 onward), MCP server startup/install (cli.py:7276 onward), model provisioning, workspace agent-rule editing, and testbed management. This makes small CLI fixes risky because imports, helpers, and side effects are shared globally.
- Fix sketch: Split by boundary, not by arbitrary size: `cli/root.py`, `cli/config_commands.py`, `cli/ingest_commands.py`, `cli/sync_commands.py`, `cli/query_commands.py`, `cli/plugin_commands.py`, `cli/mcp_commands.py`, `cli/testbed_commands.py`. Keep a thin `app` assembler for Typer registration and move reusable behavior to service modules instead of command modules.
- Blast radius: Large refactor surface, but mostly import paths/tests if done incrementally with `app` preserved.
- Suggested PR: `refactor(cli): split typer command modules behind stable app assembler`

### [G07-cli-11] (c) S3 - Best-effort config/MCP writes swallow failures silently
- Loc: backend/src/curator/cli.py:666, backend/src/curator/cli.py:681, backend/src/curator/cli.py:689, backend/src/curator/cli.py:2587, backend/src/curator/cli.py:2739
- Evidence: `_sync_mcp_configs` writes known MCP config files during `wiki init`, but any failure is swallowed with `except Exception: pass` (cli.py:681-690). Runtime snapshot refresh after `config set` and `config provider` also swallows all exceptions (cli.py:2587-2593,2739-2742). These are best-effort operations, but silent failure means users are told initialization/provider changes succeeded while MCP or dashboard state may not actually be updated.
- Fix sketch: Keep the command non-fatal, but collect failed target paths and print a dim warning with the exception class/message. For plugin-facing calls, include a non-fatal `warnings` list in JSON.
- Blast radius: Init/config UX and troubleshooting only; no core data model change.
- Suggested PR: `chore(cli): surface nonfatal config sync warnings`

### [G07-cli-12] (h/g) S3 - Persona and workspace LLM client paths leak clients on success/fallback paths
- Loc: backend/src/curator/cli.py:2429, backend/src/curator/cli.py:5966, backend/src/curator/cli.py:6113
- Evidence: `init` starts `_persona_client = _start_client(config)` and runs `_run_curator_persona_wizard` without a `finally: close()` (cli.py:2429-2430). `workspace_init` starts `_ws_client` for the Artist persona wizard and never closes it after success or fallback (cli.py:5966-5977). `persona_update` starts `client = _start_client(config)` and writes config/curate.yml without closing (cli.py:6113-6149). Other long-running commands (`build`, `query`, `sync`) consistently close clients in `finally`, so these are outliers.
- Fix sketch: Wrap each persona client in `try/finally`, or make `_start_client` return a context-manageable adapter and use `with` consistently.
- Blast radius: Mostly long-lived CLI sessions and subprocess resource hygiene; low data risk.
- Suggested PR: `fix(cli): close persona wizard clients`

### [G07-cli-13] (f/i) S3 - CLI-visible docs/help still describe old behavior
- Loc: backend/src/curator/cli.py:1, backend/src/curator/cli.py:14, backend/src/curator/cli.py:4313, backend/src/curator/cli.py:4322, backend/src/curator/cli.py:4362, docs/guides/WORKFLOW_GUIDE.md:173
- Evidence: The module docstring still says "Later stages add: ingest, query, sync, serve" (cli.py:14); there is no `wiki ingest` or `wiki serve`, and core commands are now `add/build/update/query/sync`. `sync`'s docstring says "By default, wiki sync runs LLM contradiction detection" (cli.py:4322-4324), but the no-flag path returns through incremental sync without starting an LLM (cli.py:4362-4375). The user guide correctly says default `wiki sync` is incremental and `--full` runs full revalidation (WORKFLOW_GUIDE.md:173-193), so CLI help is the stale layer.
- Fix sketch: Update CLI docstrings/help first, then re-check `USER_GUIDE`/`WORKFLOW_GUIDE` for the same wording. Consider a small `CliRunner(... --help)` snapshot for the important help text.
- Blast radius: User help and docs only.
- Suggested PR: `docs(cli): align help text with current sync and command surface`

### [G07-cli-14] (f/i) S3 - `wiki config provider --primary <provider>` can still prompt in the flagged path, despite the non-interactive-safe contract
- Loc: backend/src/curator/cli.py:2650, backend/src/curator/cli.py:2700, backend/src/curator/cli.py:2704, backend/src/curator/cli.py:2710, docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:584
- Evidence: The spec says `wiki config provider` must be non-interactive-safe for subprocess callers (SYSTEM_BEHAVIOR.md:584-589). The CLI treats any flag as the direct path (cli.py:2650-2652), but if `--primary` is provided without `--model`, it invokes `_pick_cloud_model` or `_pick_ollama_model` (cli.py:2700-2711), both prompt. Existing tests cover `--primary ... --model ...` only; the partial-flag path can still abort/hang in non-TTY contexts.
- Fix sketch: If stdin is not a TTY and `--model` is absent, either keep the existing model for that provider, choose the provider default, or fail fast with a clear non-interactive error before any prompt. Add tests for `--primary ollama` and `--primary claude-code` with empty input/non-TTY.
- Blast radius: Dashboard/subprocess safety, scripting, CI.
- Suggested PR: `fix(cli): make config provider partial flags noninteractive-safe`

### [G07-cli-15] (g/i) S3 - `wiki init --no-interactive` still auto-runs `npm install`/`npm run build` for the Obsidian plugin
- Loc: backend/src/curator/cli.py:2196, backend/src/curator/cli.py:2251, backend/src/curator/cli.py:2255, backend/src/curator/cli.py:2267
- Evidence: `--no-interactive` is documented as suitable for CI/scripting (cli.py:2196-2200). But if the repo `plugin/` directory exists, non-interactive init sets `build_plugin = True` (cli.py:2251-2255) and runs `npm install` plus `npm run build` (cli.py:2267-2268). Failures are warnings, but the command can still spend network/time in an unrelated Node build when the caller only asked to initialize a backend/test vault.
- Fix sketch: Add `--install-plugin/--no-install-plugin` or make `--no-interactive` skip plugin build by default unless explicitly requested. Keep interactive default unchanged if desired.
- Blast radius: Tests, CI, testbed initialization, first-run setup latency.
- Suggested PR: `fix(cli): make noninteractive init skip plugin build unless requested`

## Positives (keep / do-not-break)
- The root Typer app deliberately hides integration/development namespaces (`plugin`, `mcp`, `testbed`, `devices`, `jobs`, search `models`) from daily `wiki --help`, matching the workflow guide's limited default surface.
- `_resolve_root_or_die` already avoids persisting testbed vaults to `last_root` when it can read the testbed flag, and disables `last_root` fallback when a specific `hint_path` is supplied. Preserve that safety in any root-resolution refactor.
- `build --wait`, `query`, and full `sync` consistently close their LLM clients in `finally`; use these as the pattern for persona/workspace fixes.
- Plugin commands consistently return JSON payloads rather than Rich human text, which is the right boundary for the Obsidian subprocess API. The problem is duplication/inconsistency, not the JSON contract itself.
- `mcp_callback` refuses to start stdio JSON-RPC when stdin is a TTY and prints setup guidance instead. That guard prevents a common confusing terminal failure mode.
- `config_provider` already saves provider changes before optional install offers, which is the right ordering for subprocess safety; the remaining issue is only prompt-free partial-flag handling.

## Open questions for the human
- Should `wiki query "question"` remain a chat REPL after the first answer, or should one-shot behavior become the default with an explicit `wiki query --chat`/`wiki chat` mode?
- For `wiki config models use`, should the command always change the primary slot, or should it support choosing whether to update primary vs fallback?
- Is `wiki lint` expected to refresh routing manifests as part of linting, or should that move fully to `wiki sync`/`wiki update` so lint becomes a pure diagnostic command?
- Should `wiki build` own detached worker lifecycle at all, or should background processing be exclusively the MCP worker plus explicit foreground `wiki jobs run`?
- Is `plugin_models_pull` intentionally exit-code 0 on `ok:false` because the plugin only reads JSON, or should plugin JSON commands standardize on nonzero process status for failed operations?
