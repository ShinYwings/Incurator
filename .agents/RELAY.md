# RELAY — IDLE at v0.53.0

No active goal. Master is at **v0.53.0**, working tree clean, no open PRs.

## Shipped this run (v0.52.1 → v0.53.0)

- **v0.52.1** — job snapshot re-derived on terminal transitions (the spinner that
  never stopped while `wiki jobs list` was empty); truthful Convert-to-LaTeX
  errors.
- **v0.52.2** — §26.2b loss records backfilled (2 → 132 on the reporting vault);
  an unreadable region is served as a statement, not the parser artifact.
- **v0.52.3** — unmapped PDF glyphs read as an image instead of being deleted.
  This reverted a regression I shipped in v0.52.1.
- **v0.53.0** — the MCP server made startable at all, plus
  `wiki mcp install obsidian`.

## Critical context

- **The MCP server was unstartable by ANY client from v0.34.0 to v0.53.0.**
  `no_args_is_help=True` and a callback missing `invoke_without_command` were
  both introduced by the v0.34.0 CLI decomposition (`3c63dde`), whose own plan
  promised "preserving every observable CLI, MCP, and hidden plugin command
  contract". Undetected because every MCP test calls `build_server()` in
  process — none spawns the CLI entry point. `test_mcp_obsidian_install.py` now
  pins both Typer settings.
- **The plugin chat reaches the knowledge base ONLY through an `mcpServers`
  entry named `incurator`.** Tool injection and the system-prompt section are
  both gated on it (`ChatSidebarView.ts:1391`). The reporting vault had
  `mcpServers: []`, so every retrieval improvement in v0.43–v0.52 was invisible
  from the plugin. PLUGIN_SCHEMA had said that field was for "external/
  non-Incurator" servers — it contradicted shipped behavior and is now corrected.
- **`pdfFullDocumentIndex` has zero consumers.** The "Background page indexing"
  toggle writes a value nothing reads, so `search_pdf_anchor` is still limited
  to already-rendered pages. `fetch_pdf_page` reads any page, so the model can
  follow a reference it can name but cannot search unread pages. **This is the
  next item and needs a plan.**
- Venvs live at the repo root: `.venv` runtime (now carries `[mcp]`),
  `.venv-dev` checks. Never `backend/.venv`, `backend/uv.lock`, or backend-local
  caches. Install hints must name `--python` or point at `./setup.sh`.
- Two time-dependent tests expired mid-session. Use far-future sentinels
  (2099-01-01), never a plausible near date.
- A stale pytest assertion-rewrite cache made a correct fix look broken for two
  full runs. If a fix passes in a copied file but fails in the original, clear
  `__pycache__` before doubting the fix.

## Immediate next action

ROADMAP item 1 (formula recovery) is still blocked on its three prerequisites.
The live candidate is `pdfFullDocumentIndex` — implement background indexing so
the chat can search unrendered PDF pages. Needs an Arena plan first.
