# C - Plugin API Domain Analysis

Date: 2026-07-09

## Design Constraints From Codebase

- `backend/src/curator/plugin_api.py` is 1,100 lines.
- It is a backend-local function API, not an HTTP router module.
- Hidden `wiki plugin ...` CLI commands import and call these functions.
- `mcp_server.py` imports `plugin_api` for durable L1 and PDF context behavior.
- Existing tests import `from curator import plugin_api` and call direct
  functions, including `register_source`, `pdf_context`, `curator_query`, and
  private helper `_safe_pdf_page_cache_key`.

## Docs And Spec Invariants

- `PLUGIN_SCHEMA.md` defines the hidden command namespace and backend command
  contracts.
- `SYSTEM_BEHAVIOR.md` requires the plugin to mutate durable state only through
  backend-owned commands/APIs.
- Plugin-facing JSON envelopes and warning/error fields must remain unchanged.

## Alternatives And Tradeoffs

- Leave `plugin_api.py` as one file: lowest risk, but leaves a known god-file.
- Convert to `plugin_api/` package with re-exported functions: best long-term
  shape but requires an atomic module-to-package move.
- Introduce HTTP routes: rejected because current code and docs use backend
  command/function APIs, and adding HTTP semantics would be a behavior change.

## Final Decision

Convert `curator.plugin_api` into a package only after tests lock the export set
and representative response envelopes. `plugin_api/__init__.py` re-exports the
existing public and currently-tested private helper names.

When code moves from `curator/plugin_api.py` into
`curator/plugin_api/*.py`, every sibling import must be re-based from the package
level to the parent `curator` package. Current imports such as
`from . import db, ingest_raw, llm, page_writer, query, search, source_tools`
must become `from .. import db, ingest_raw, llm, page_writer, query, search,
source_tools` in extracted modules. Lazy imports inside functions need the same
shift, for example `from . import zotero_tools` becomes
`from .. import zotero_tools`.

## Pseudocode

```python
# curator/plugin_api/__init__.py
from .sources import source_row, source_dict, source_status, import_source
from .sources import register_source, rebind_source, search_sources
from .pdf import pdf_context, durable_l1_section, _safe_pdf_page_cache_key
from .context import fetch_context, expand_context, verify_context, feedback_context
from .query import curator_query, promote_answer

# curator/plugin_api/sources.py
from .. import db, ingest_raw, search, source_tools
```

## Required Characterization

- Assert `from curator import plugin_api` still imports.
- Assert expected function names exist on `plugin_api`.
- Assert representative responses preserve keys for source status, source
  registration warnings, PDF context, context fetch validation, query fallback,
  and promotion validation.
