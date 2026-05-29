"""MCP server — exposes the Curator DAG to workspace agents.

Run via:    wiki mcp           # stdio transport (default)
Install:    wiki mcp install   # prints a config snippet for Claude / Gemini

The server combines two responsibility layers:

1. **Search delegation** — the `search` tool shells out to the bundled
   `backend/src/qmd/bin/qmd` to leverage qmd's BM25 + vector + LLM-rerank pipeline.
   No HTTP daemon required; qmd is invoked per-call and qmd's own model
   caching keeps latency low.

2. **Curator-specific traversal** — tools like `curator_traverse_evidence`,
   `curator_get_node`, `curator_find_contradictions` walk the DAG by ID
   using the on-disk markdown source-of-truth, so the agent can follow
   EXH → CON → ATM chains, surface contradictions, and respect confidence
   thresholds.

Vault resolution:
    1. `VAULT_ROOT` env var
    2. cfg.find_wiki_root() walking up from `cwd`
    Server raises a clear error early if neither resolves.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    from mcp.server.fastmcp import Context, FastMCP
except ImportError as e:  # pragma: no cover - import-time hint
    raise ImportError(
        "The `mcp` package is required. Install with: "
        "cd backend && uv pip install -e '.[mcp]'"
    ) from e

from . import config as cfg
from . import page_writer
from . import source_tools


# ---------------------------------------------------------------------------
# Vault resolution (run once at import / server-start)
# ---------------------------------------------------------------------------


def _resolve_paths(hint_path: str = "") -> cfg.WikiPaths:
    """Locate the vault. No fallback — ambiguous resolution raises immediately.

    Priority (first match wins, no further fallback):
    1. VAULT_ROOT env var — set at server start by mcp_callback; always authoritative.
    2. curate.yml vault_root — explicit spec in the workspace; honoured only when
       VAULT_ROOT is absent (e.g. standalone tool call without a running server).

    No upward traversal, no CWD discovery. If neither source resolves to a valid
    vault the call fails loudly so callers can supply the correct path rather than
    silently landing in the wrong vault.
    """
    # 1. VAULT_ROOT — pinned by mcp_callback() before the server starts; must win.
    env_root = os.environ.get("VAULT_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if (candidate / cfg.INTERNAL_DIR / cfg.CONFIG_FILE).exists():
            return cfg.paths_from_config(candidate)
        raise RuntimeError(
            f"VAULT_ROOT is set to '{env_root}' but no vault was found there "
            f"(missing {cfg.INTERNAL_DIR}/{cfg.CONFIG_FILE}). "
            "Re-run `wiki mcp` from inside an initialised vault."
        )

    # 2. curate.yml vault_root — only when VAULT_ROOT is absent.
    if hint_path:
        ws_path = Path(hint_path).expanduser().resolve()
        if ws_path.is_file():
            ws_path = ws_path.parent
        try:
            from . import curate_yml as _cym
            spec = _cym.load_curate_spec(ws_path)
            if spec and spec.vault_root:
                vroot = Path(spec.vault_root).expanduser().resolve()
                if (vroot / cfg.INTERNAL_DIR / cfg.CONFIG_FILE).exists():
                    return cfg.paths_from_config(vroot)
                raise RuntimeError(
                    f"curate.yml vault_root='{spec.vault_root}' does not contain a valid vault. "
                    "Update vault_root in curate.yml or set VAULT_ROOT."
                )
        except RuntimeError:
            raise
        except Exception:
            pass

    raise RuntimeError(
        "Cannot resolve vault: VAULT_ROOT is not set and no curate.yml with vault_root was found. "
        "Start the MCP server via `wiki mcp` (which sets VAULT_ROOT automatically), "
        "or ensure your workspace curate.yml contains a valid vault_root."
    )


# ---------------------------------------------------------------------------
# DAG helpers — read-only access to the on-disk Curator collections
# ---------------------------------------------------------------------------


_LAYERS = {
    "context":    ("01_Contexts",    "CTX-"),
    "atom":       ("02_Atoms",       "ATM-"),
    "concept":    ("03_Concepts",    "CON-"),
    "exhibition": ("04_Exhibitions", "EXH-"),
}


def _layer_for_id(node_id: str) -> Optional[tuple[str, str]]:
    for layer, (subdir, prefix) in _LAYERS.items():
        if node_id.startswith(prefix):
            return layer, subdir
    return None


def _read_node(paths: cfg.WikiPaths, node_id: str) -> dict[str, Any]:
    """Load a Curator page by ID. Returns dict with frontmatter + body, or
    {'error': ...} if not found.
    """
    info = _layer_for_id(node_id)
    if info is None:
        return {"error": f"Unknown ID prefix in '{node_id}' (expected CTX-/ATM-/CON-/EXH-)"}
    layer, subdir = info
    page_path = paths.collections / subdir / f"{node_id}.md"
    if not page_path.exists():
        return {"error": f"Page not found: {subdir}/{node_id}.md"}
    parsed = page_writer.read_page(page_path)
    if parsed is None:
        return {"error": f"Could not read {page_path}"}
    return {
        "id": node_id,
        "layer": layer,
        "path": f"{subdir}/{node_id}.md",
        "frontmatter": parsed.frontmatter,
        "body": parsed.body,
    }


def _normalize_link(link: str) -> str:
    """Strip wiki-link decorations to bare 'LAYER/ID' form."""
    if not link:
        return ""
    s = link.strip()
    if s.startswith("[[") and s.endswith("]]"):
        s = s[2:-2]
    if "|" in s:
        s = s.split("|", 1)[0]
    if s.endswith(".md"):
        s = s[:-3]
    return s.strip("/")


def _id_from_link(link: str) -> str:
    """'02_Atoms/ATM-abc12345' -> 'ATM-abc12345'."""
    s = _normalize_link(link)
    return s.rsplit("/", 1)[-1]


def _concept_atom_ids(con: dict[str, Any]) -> list[str]:
    """Concept → Atom edges live in the terminal `## Relations` section."""
    atom_ids: list[str] = []
    for target in page_writer.extract_relation_targets(con.get("body", ""), prefix="02_Atoms/"):
        atom_id = _id_from_link(target)
        if atom_id.startswith("ATM-") and atom_id not in atom_ids:
            atom_ids.append(atom_id)
    return atom_ids


# ---------------------------------------------------------------------------
# Persona update tools (also registered on the MCP server in build_server)
# ---------------------------------------------------------------------------

_ARTIST_PERSONA_KEYS = [
    "domain", "subdomain", "goal", "exhibition_intent",
    "confidence", "disambiguation_keywords", "updated_at",
]

_CURATOR_PERSONA_KEYS = [
    "area", "text", "knowledge_artifacts", "verification_philosophy",
    "exhibition_intent", "confidence", "disambiguation_keywords", "updated_at",
]


def curator_update_artist_persona(workspace_path: str, request: str) -> dict:
    """Update the Artist persona (workspace-level) based on a natural-language request.

    workspace_path: absolute or relative path to the workspace directory (contains curate.yml)
    request: natural language description of what to change, e.g. "Make it more theory-focused"

    Returns: {"updated_fields": [...], "before": {...}, "after": {...}}
    """
    import yaml as _yaml
    from .llm import build_client, ChatMessage

    ws = Path(workspace_path).expanduser().resolve()
    curate_file = ws / "curate.yml"
    if not curate_file.exists():
        return {"error": f"curate.yml not found in {ws}"}

    try:
        raw = _yaml.safe_load(curate_file.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return {"error": f"Failed to read curate.yml: {exc}"}

    old_persona: dict = raw.get("persona", {}) or {}

    try:
        paths = _resolve_paths(workspace_path)
        config = cfg.load_config(paths)
        client = build_client(config)
    except Exception as exc:
        return {"error": f"Could not start LLM client: {exc}"}

    try:
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "You are a knowledge-base configuration assistant. Given a current "
                    "Artist persona and a user request, produce an updated persona JSON. "
                    "Return ONLY valid JSON with the updated persona fields. "
                    "Do not change fields not mentioned in the request."
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    f"Current persona: {json.dumps(old_persona)}\n\n"
                    f"User request: {request}\n\n"
                    f"Return an updated persona JSON object with only these keys: "
                    f"{', '.join(_ARTIST_PERSONA_KEYS)}."
                ),
            ),
        ]
        response = client.chat(messages, temperature=0.3)
    except Exception as exc:
        return {"error": f"LLM call failed: {exc}"}
    finally:
        try:
            client.close()
        except Exception:
            pass

    try:
        new_persona = json.loads(response)
        if not isinstance(new_persona, dict):
            raise ValueError("LLM returned non-object JSON")
    except Exception:
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            try:
                new_persona = json.loads(match.group())
            except Exception:
                return {"error": f"Could not parse LLM JSON response: {response[:200]}"}
        else:
            return {"error": f"Could not parse LLM JSON response: {response[:200]}"}

    new_persona["updated_at"] = datetime.now().isoformat()
    updated_fields = [k for k in new_persona if new_persona.get(k) != old_persona.get(k)]

    raw["persona"] = new_persona
    try:
        curate_file.write_text(
            _yaml.safe_dump(raw, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
    except Exception as exc:
        return {"error": f"Failed to write curate.yml: {exc}"}

    return {"updated_fields": updated_fields, "before": old_persona, "after": new_persona}


def curator_update_curator_persona(request: str, workspace_path: str = "") -> dict:
    """Update the vault-level Curator persona based on a natural-language request.

    request: natural language description of what to change
    workspace_path: Optional workspace path to help resolve the vault.

    Returns: {"updated_fields": [...], "before": {...}, "after": {...}}
    """
    from .llm import build_client, ChatMessage

    try:
        paths = _resolve_paths(workspace_path)
        config = cfg.load_config(paths)
    except Exception as exc:
        return {"error": f"Could not load vault config: {exc}"}

    old_persona: dict = config.get("persona", {}) or {}

    try:
        client = build_client(config)
    except Exception as exc:
        return {"error": f"Could not start LLM client: {exc}"}

    try:
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "You are a knowledge-base configuration assistant. Given a current "
                    "vault persona and a user request, produce an updated persona JSON. "
                    "Return ONLY valid JSON."
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    f"Current persona: {json.dumps(old_persona)}\n\n"
                    f"User request: {request}\n\n"
                    f"Return an updated persona JSON with only these keys: "
                    f"{', '.join(_CURATOR_PERSONA_KEYS)}."
                ),
            ),
        ]
        response = client.chat(messages, temperature=0.3)
    except Exception as exc:
        return {"error": f"LLM call failed: {exc}"}
    finally:
        try:
            client.close()
        except Exception:
            pass

    try:
        new_persona = json.loads(response)
        if not isinstance(new_persona, dict):
            raise ValueError("LLM returned non-object JSON")
    except Exception:
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            try:
                new_persona = json.loads(match.group())
            except Exception:
                return {"error": f"Could not parse LLM JSON response: {response[:200]}"}
        else:
            return {"error": f"Could not parse LLM JSON response: {response[:200]}"}

    new_persona["updated_at"] = datetime.now().isoformat()
    updated_fields = [k for k in new_persona if new_persona.get(k) != old_persona.get(k)]

    config["persona"] = new_persona
    try:
        cfg.save_config(paths, config)
    except Exception as exc:
        return {"error": f"Failed to save config: {exc}"}

    return {"updated_fields": updated_fields, "before": old_persona, "after": new_persona}


# ---------------------------------------------------------------------------
# Wizard questions helper
# ---------------------------------------------------------------------------



def _get_workspace_files_summary(workspace_path: Path) -> str:
    """Return a brief summary of files in the workspace to help the LLM."""
    try:
        files = []
        for p in workspace_path.glob("*"):
            if p.name.startswith(".") or p.name == "__pycache__":
                continue
            if p.is_dir():
                files.append(f"{p.name}/")
                count = 0
                for subp in p.glob("*"):
                    if subp.name.startswith("."):
                        continue
                    if subp.is_file():
                        files.append(f"  {p.name}/{subp.name}")
                        count += 1
                    if count > 5:
                        break
            else:
                files.append(p.name)
            if len(files) > 20:
                break
        return "\n".join(files)
    except Exception:
        return "Could not list files."


def _get_interview_suggestions(workspace_path: str, field_id: str, provided: dict) -> list[str]:
    """Use LLM to suggest 5 options for a specific field based on workspace content."""
    from . import llm, config as cfg
    import json
    import re
    from pathlib import Path
    from .llm import ChatMessage

    try:
        paths = _resolve_paths(workspace_path)
        config = cfg.load_config(paths)

        ws = Path(workspace_path).expanduser().resolve()
        context = f"Workspace folder: {ws.name}"
        if provided:
            ans = {k: v for k, v in provided.items() if v}
            if ans:
                context += "\n\nPreviously provided answers:\n" + json.dumps(ans, indent=2)

        # Get global vault directories and their immediate subdirectories for better suggestions
        global_dirs = []
        for d in ["02_Wiki", "03_Notes", "04_Resources"]:
            base_p = paths.root / d
            if base_p.exists():
                global_dirs.append(f"{d}/")
                # Add one level of subdirectories to be more specific
                try:
                    for subp in base_p.glob("*/"):
                        if subp.name.startswith("."):
                            continue
                        if subp.is_dir():
                            global_dirs.append(f"{d}/{subp.name}/")
                        if len(global_dirs) > 15:
                            break
                except Exception:
                    pass

        if field_id == "exclude_patterns":
            PROMPT = f"""You are a workspace configuration assistant.
Based on the global vault structure, suggest 5 folders to EXCLUDE from this workspace.
ONLY suggest folders that actually exist in the Vault list below.

Vault global directories:
{', '.join(global_dirs)}

Project context:
{context}

Instructions:
- Return ONLY a JSON list of 5 strings.
- Prefix paths with '[Vault] ' for clarity.
- Focus on folders irrelevant to the project context.
"""
        elif field_id in ["domains", "topics"]:
            PROMPT = f"""You are a workspace configuration assistant.
Based on the project context below, suggest 5 highly relevant technical/academic {field_id}.

Project context:
{context}

Instructions:
- Return ONLY a JSON list of 5 strings.
- Suggest concise keywords or short phrases.
- Do NOT include any prefixes.
"""
        else: # description or other
            PROMPT = f"""You are a workspace configuration assistant.
Based on the workspace folder name '{ws.name}', suggest 5 short variations for the project goal ('{field_id}').

Project context:
{context}

Instructions:
- Return ONLY a JSON list of 5 strings.
- Infer the primary research or development goal from the folder name '{ws.name}'.
- Suggest 1-sentence goals/descriptions.
- Do NOT include any prefixes.
"""

        if field_id == "min_confidence":
            return ["0.60", "0.70", "0.80", "0.85", "0.90"]
        with llm.build_client(config) as client:
            raw = client.chat([ChatMessage(role="user", content=PROMPT)], temperature=0.3)
            raw_stripped = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
            suggestions = json.loads(raw_stripped)
            if isinstance(suggestions, list):
                if field_id == "exclude_patterns":
                    # Filter out hallucinations
                    valid_global = {d.strip("/") for d in global_dirs}
                    cleaned = []
                    for s in suggestions:
                        path = str(s).replace("[Vault] ", "").strip("/")
                        if path in valid_global:
                            cleaned.append(str(s))
                    return cleaned[:5]
                return [str(s) for s in suggestions[:5]]
    except Exception:
        pass

    # Fallbacks
    fallbacks = {
        "description": ["Knowledge base for research", "Technical documentation", "Learning notes"],
        "domains": ["computer-vision", "rendering", "robotics", "optimization", "physics"],
        "topics": ["algorithm", "pipeline", "benchmark", "theory", "application"],
        "min_confidence": ["0.60", "0.70", "0.80", "0.85", "0.90"]
    }
    return fallbacks.get(field_id, ["Option 1", "Option 2", "Option 3", "Option 4", "Option 5"])[:5]
def _build_wizard_questions(workspace_path: str, provided: dict = None) -> dict[str, Any]:
    """Build a dynamic one-question-at-a-time interview for workspace init."""
    provided = provided or {}
    fields = [
        ("description", "Project Description", "What is the primary goal of this workspace?"),
        ("domains", "Main Domains", "Which academic or technical domains does this project belong to?"),
        ("topics", "Specific Topics", "What specific keywords or technologies define this project?"),
        ("exclude_patterns", "Sources to Exclude", "Which vault folders (e.g., 03_Notes/Other) should be excluded from this project's knowledge base?"),
        ("min_confidence", "Confidence Threshold", "Minimum confidence for search results (0.5-0.95)?")
    ]

    missing = None
    for fid, label, q in fields:
        val = provided.get(fid)
        if val is None or (isinstance(val, list) and not val):
            # Exception: include/exclude can be empty lists if provided explicitly
            if fid in provided:
                continue
            missing = (fid, label, q)
            break

    if missing is None:
        return {"ok": True, "all_answered": True}

    fid, label, q = missing
    suggestions = _get_interview_suggestions(workspace_path, fid, provided)

    return {
        "ok": True,
        "needs_initialization": True,
        "phase": "interview",
        "workspace": workspace_path,
        "current_step": {
            "id": fid,
            "label": label,
            "question": q,
            "suggestions": suggestions,
        },
        "provided_so_far": provided,
        "instructions": (
            "CRITICAL: WORKSPACE INITIALIZATION REQUIRED. YOU MUST HALT ALL OTHER ACTIVITIES.\n"
            "1. DO NOT answer any previous user questions or provide any analysis.\n"
            "2. Explain that the Curator workspace is not yet initialized and you need to perform a quick setup.\n"
            f"3. IMMEDIATELY ask this question: '{q}'.\n"
            f"4. You MUST provide these 5 options as a numbered list for the user to choose from: {', '.join(suggestions)}.\n"
            "5. Also offer an 'Other' option for manual entry.\n"
            "6. STOP your response immediately after asking. Do not provide any other prose."
        )
    }


# ---------------------------------------------------------------------------
# Server construction
# ---------------------------------------------------------------------------


def build_server() -> FastMCP:
    """Build and register all tools on a fresh FastMCP instance."""
    import os
    from . import search, ingest_llm, ingest_raw, db, llm, config as cfg, zotero

    mcp = FastMCP(
        name="incurator",
        instructions=(
            "incurator Curator MCP — follow this protocol strictly for every session:\n\n"
            "SESSION START PROTOCOL (run every time):\n"
            "  Step 1: Call `curator_check_workspace` with the current workspace path.\n"
            "  Step 2: If the response contains `needs_initialization: true`, you MUST "
            "HALT all other tasks and follow its `instructions` immediately. DO NOT "
            "answer any other user questions until initialization is complete. "
            "Explain that Curator workspace initialization is required for knowledge "
            "management, then present the question.\n"
            "  Step 3: After `curator_workspace_init` completes, call `search_curator` with "
            "`workspace_path` to retrieve prior knowledge. "
            "Do NOT call `curator_curate_workspace` or `curator_reindex` separately — "
            "`curator_workspace_init` already runs both inline.\n\n"
            "SEARCH PROTOCOL:\n"
            "  - Always pass `workspace_path` to `search_curator`.\n"
            "  - If response has `needs_curation: true`, call `curator_curate_workspace` "
            "then retry `search_curator`.\n"
            "  - If response has `needs_initialization: true`, follow its `instructions` to start the interview.\n\n"
            "KNOWLEDGE UPDATE PROTOCOL:\n"
            "  - Edit only EXH- nodes via `curator_update_node` (reindex runs automatically).\n"
            "  - Add new insights via `curator_add_knowledge` (reindex runs automatically).\n"
            "  - Call `curator_reindex` only after manually editing vault files outside MCP.\n\n"
            "Layer prefixes: CTX- (01_Contexts), ATM- (02_Atoms), CON- (03_Concepts), EXH- (04_Exhibitions)."
        ),
    )

    try:
        if os.environ.get("CURATOR_DISABLE_INGEST_WORKER") != "1":
            from .ingest_worker import IngestWorker

            worker_paths = _resolve_paths()
            db.init_db(worker_paths.state_db)
            worker = IngestWorker(
                worker_paths,
                lambda: cfg.load_config(worker_paths),
                poll_seconds=10.0,
            )
            worker.start()
            mcp._incurator_ingest_worker = worker  # keep a strong reference
    except Exception:
        pass

    def _source_dict(paths: cfg.WikiPaths, row: dict[str, Any]) -> dict[str, Any]:
        source_id = int(row["id"])
        pages = db.list_source_pdf_pages(paths.state_db, source_id)
        generated = db.list_source_pages(paths.state_db, source_id)
        out = source_tools.source_status(paths, row, cfg.load_config(paths))
        out["pdf_page_count"] = len(pages)
        out["page_count"] = len(pages)
        out["generated_pages"] = generated
        return out

    def _get_source_row(
        paths: cfg.WikiPaths,
        source_id: int | None = None,
        relpath: str = "",
        source_path: str = "",
    ) -> dict[str, Any] | None:
        relpath = relpath or _source_path_to_relpath(paths, source_path)
        with db.connect(paths.state_db) as conn:
            if source_id is not None:
                row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
            elif relpath:
                row = conn.execute(
                    """
                    SELECT * FROM sources
                    WHERE relpath = ?
                       OR external_path = ?
                       OR import_origin = ?
                       OR logical_source_id = ?
                    """,
                    (relpath, relpath, relpath, relpath),
                ).fetchone()
            else:
                row = None
        return dict(row) if row else None

    def _source_path_to_relpath(paths: cfg.WikiPaths, source_path: str = "") -> str:
        if not source_path:
            return ""
        raw = str(source_path)
        path = Path(raw).expanduser()
        if path.is_absolute():
            try:
                return str(path.resolve().relative_to(paths.root.resolve()))
            except ValueError:
                return raw
        return raw

    class _McpIngestCallbacks(ingest_llm.IngestCallbacks):
        def __init__(self) -> None:
            self.events: list[dict[str, Any]] = []

        def on_start(self, source_id: int, source_title: str, context_id: str) -> None:
            self.events.append({"kind": "start", "source_id": source_id, "title": source_title, "context_id": context_id})

        def on_fragment_written(self, change) -> None:
            self.events.append({"kind": "page", "path": change.path, "operation": change.operation})

        def on_theme_written(self, change) -> None:
            self.events.append({"kind": "page", "path": change.path, "operation": change.operation})

        def on_error(self, error: str) -> None:
            self.events.append({"kind": "error", "error": error})

    # ------------------------------------------------------------------
    # Source tools — raw-source status, import, ingest, page search/provenance
    # ------------------------------------------------------------------


    @mcp.tool()
    def curator_search_zotero_items(
        query: str,
        workspace_path: str = "",
        custom_paths: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search Zotero items by title or author."""
        if not custom_paths:
            return {"ok": False, "error": "custom_paths (zoteroBasePath) is required"}

        try:
            from .zotero_integration import search_zotero_items
            import os
            candidates = [
                p.strip()
                for p in str(custom_paths).split(",")
                if p.strip()
            ]
            checked: list[str] = []
            for candidate in candidates:
                base = os.path.expanduser(candidate)
                zotero_db = base if base.endswith(".sqlite") else os.path.join(base, "zotero.sqlite")
                checked.append(zotero_db)
                items = search_zotero_items(zotero_db, query, limit=limit)
                if items:
                    return {"ok": True, "items": items, "db_path": zotero_db}
            return {"ok": True, "items": [], "checked": checked}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @mcp.tool()
    def curator_get_zotero_item_metadata(
        item_key: str,
        workspace_path: str = "",
        custom_paths: str = "",
        citation_style: str = "",
    ) -> dict[str, Any]:
        """Fetch full metadata for a Zotero item."""
        if not custom_paths:
            return {"ok": False, "error": "custom_paths (zoteroBasePath) is required"}

        try:
            from .zotero_integration import get_zotero_item_metadata
            import os
            zotero_db = os.path.join(os.path.expanduser(custom_paths), "zotero.sqlite")
            metadata = get_zotero_item_metadata(zotero_db, item_key, citation_style=citation_style)
            return {"ok": True, "metadata": metadata}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @mcp.tool()
    def curator_get_zotero_annotations(

        attachment_key: str,
        workspace_path: str = "",
        custom_paths: str = "",
    ) -> dict[str, Any]:
        """Fetch all PDF annotations for a given Zotero attachment key."""
        paths = _resolve_paths(workspace_path)
        config = cfg.load_config(paths)
        zotero_db = config.get("zotero", {}).get("db_path", os.path.expanduser("~/Zotero/zotero.sqlite"))

        # If custom paths provided, check if we can find a sqlite db there
        if custom_paths:
            for p in custom_paths.split(","):
                p = p.strip()
                if not p: continue
                db_cand = os.path.join(os.path.expanduser(p), "zotero.sqlite")
                if os.path.exists(db_cand):
                    zotero_db = db_cand
                    break

        try:
            annotations = zotero.get_zotero_annotations(zotero_db, attachment_key)
            return {"ok": True, "annotations": annotations}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    @mcp.tool()
    def curator_resolve_zotero_pdf(
        attachment_key: str,
        workspace_path: str = "",
        custom_paths: str = "",
    ) -> dict[str, Any]:
        """Resolve the absolute path of a Zotero PDF attachment."""
        paths = _resolve_paths(workspace_path)
        config = cfg.load_config(paths)

        candidates = [os.path.expanduser("~/Zotero")]
        if custom_paths:
            for p in custom_paths.split(","):
                p = p.strip()
                if not p: continue
                p = os.path.expanduser(p)
                candidates.append(p)
        if "external" in config and "zotero" in config["external"]:
            roots = config["external"]["zotero"].get("roots", [])
            for r in roots:
                candidates.append(os.path.expanduser(r))

        zotero_db = config.get("zotero", {}).get("db_path", os.path.expanduser("~/Zotero/zotero.sqlite"))
        if custom_paths:
            for cand in candidates:
                db_cand = os.path.join(cand, "zotero.sqlite")
                if os.path.exists(db_cand):
                    zotero_db = db_cand
                    break

        # 1. Check DB for path
        db_path = zotero.get_zotero_attachment_path_from_db(zotero_db, attachment_key)

        if db_path:
            # Linked attachment
            if db_path.startswith("attachments:"):
                rel_path = db_path[len("attachments:"):]
                for cand in candidates:
                    # cand could be the base path itself, or we might need to check standard places
                    # Usually linked attachments base path is in one of the roots or candidates
                    check_path = os.path.join(cand, rel_path)
                    if os.path.exists(check_path):
                        return {"ok": True, "path": check_path}
            # Absolute path
            elif os.path.isabs(db_path) and os.path.exists(db_path):
                return {"ok": True, "path": db_path}
            # Storage path
            elif db_path.startswith("storage:"):
                rel_path = db_path[len("storage:"):]
                for cand in candidates:
                    check_path = os.path.join(cand, "storage", attachment_key, rel_path)
                    if os.path.exists(check_path):
                        return {"ok": True, "path": check_path}

        # 2. Fallback: Check storage directories directly (legacy behavior)
        for cand in candidates:
            item_dir = os.path.join(cand, "storage", attachment_key)
            if not os.path.isdir(item_dir):
                continue
            for f in os.listdir(item_dir):
                if f.lower().endswith(".pdf"):
                    return {"ok": True, "path": os.path.join(item_dir, f)}

        return {"ok": False, "error": "PDF not found"}

    @mcp.tool()
    def check_source_status(file_hash: str, workspace_path: str = "") -> dict[str, Any]:
        """Return source registration and pipeline status by SHA-256 content hash."""
        paths = _resolve_paths(workspace_path)
        with db.connect(paths.state_db) as conn:
            row = conn.execute(
                "SELECT * FROM sources WHERE content_hash = ? ORDER BY id DESC LIMIT 1",
                (file_hash,),
            ).fetchone()
        if row is None:
            return {
                "registered": False,
                "source_id": None,
                "l1_complete": False,
                "l2_complete": False,
                "l3_complete": False,
                "jobs_pending": [],
            }
        source = _source_dict(paths, dict(row))
        return {
            "registered": True,
            "source_id": int(row["id"]),
            "relpath": row["relpath"],
            "l1_complete": source.get("l1_complete", False),
            "l2_complete": source.get("l2_complete", False),
            "l3_complete": source.get("l3_complete", False),
            "jobs_pending": source.get("jobs_pending", []),
            "source": source,
        }

    @mcp.tool()
    def check_ingest_status(workspace_path: str = "") -> dict[str, Any]:
        """Return current background job queue status for plugin polling.

        Use this to update the status bar or progress panel after wiki add or
        import_source. Poll every 5 seconds until running == 0.
        Returns: ok, running (list), queued (list), done_today (count), idle (bool).
        """
        paths = _resolve_paths(workspace_path)
        if not paths.state_db.exists():
            return {"ok": True, "running": [], "queued": [], "done_today": 0, "idle": True}
        running = db.list_ingest_jobs(paths.state_db, states=("running",), limit=10)
        queued = db.list_ingest_jobs(paths.state_db, states=("queued",), limit=10)
        done_today = db.get_jobs_done_today(paths.state_db)

        def _job_summary(job: dict) -> dict:
            return {
                "job_id": job.get("id"),
                "source_id": job.get("source_id"),
                "source_name": job.get("source_name") or "",
                "job_type": job.get("job_type") or "",
                "phase": job.get("phase") or "",
                "progress": job.get("progress") or 0.0,
                "progress_current": job.get("progress_current") or 0,
                "progress_total": job.get("progress_total") or 0,
                "started_at": job.get("started_at") or "",
                "retry_count": job.get("retry_count") or 0,
            }

        return {
            "ok": True,
            "running": [_job_summary(j) for j in running],
            "queued": [_job_summary(j) for j in queued],
            "done_today": len(done_today),
            "idle": len(running) == 0 and len(queued) == 0,
        }

    @mcp.tool()
    def fetch_document_section(
        source_key: str,
        toc_id: str = "",
        section_id: str = "",
        page: int = 0,
        workspace_path: str = "",
    ) -> dict[str, Any]:
        """Fetch a raw source section for instant L1/ephemeral RAG."""
        paths = _resolve_paths(workspace_path)
        row = _get_source_row(paths, source_path=source_key)
        source_path = Path(source_key).expanduser()
        if row is not None:
            source_path = source_tools._row_path(paths, row)
        elif not source_path.is_absolute():
            source_path = paths.root / source_key
        if not source_path.exists():
            return {"ok": False, "error": f"Source not found: {source_key}"}
        try:
            parsed = source_tools.parse_source(source_path)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        wanted = section_id or toc_id
        text = parsed.text
        if page and parsed.file_type == "pdf":
            pages = parsed.metadata.get("pages") or []
            for item in pages:
                if int(item.get("page") or item.get("page_number") or 0) == int(page):
                    text = str(item.get("text") or "")
                    break
        elif wanted:
            pattern = re.compile(
                rf"(?ms)^<!--\s*section:\s*{re.escape(wanted)}\b.*?-->\s*(.*?)(?=^<!--\s*section:|\Z)"
            )
            match = pattern.search(text)
            if match:
                text = match.group(1).strip()
            else:
                heading = re.compile(
                    rf"(?ms)^#+\s+.*{re.escape(wanted)}.*$\n(.*?)(?=^#+\s+|\Z)"
                )
                match = heading.search(text)
                if match:
                    text = match.group(1).strip()

        return {
            "ok": True,
            "source_id": int(row["id"]) if row else None,
            "source_key": source_key,
            "toc_id": wanted,
            "page": page or None,
            "title": parsed.title,
            "file_type": parsed.file_type,
            "text": text,
            "char_count": len(text),
        }

    @mcp.tool()
    def curator_source_status(
        source_id: Optional[int] = None,
        relpath: str = "",
        source_path: str = "",
        file_path: str = "",
        path: str = "",
        status_filter: str = "",
        limit: int = 50,
        workspace_path: str = "",
    ) -> dict[str, Any]:
        """Return tracked source status and per-layer pipeline state.

        Args:
            source_id: Optional source row id for a single source.
            relpath: Optional vault-relative source path for a single source.
            status_filter: Optional status filter for list mode.
            limit: Max rows in list mode.
            workspace_path: Optional workspace path to help resolve the vault.
        """
        paths = _resolve_paths(workspace_path)
        stats = db.get_stats(paths.state_db)

        lookup_path = relpath or source_path or file_path or path
        if source_id is not None or lookup_path:
            row = _get_source_row(paths, source_id=source_id, relpath=relpath, source_path=lookup_path)
            if row is None:
                return {
                    "state": "untracked",
                    "error": "Source not found",
                    "source_path": lookup_path,
                    "stats": stats,
                }
            return {"stats": stats, "source": _source_dict(paths, row)}

        query_sql = "SELECT * FROM sources"
        params: tuple = ()
        if status_filter:
            query_sql += " WHERE status = ?"
            params = (status_filter,)
        query_sql += " ORDER BY id ASC LIMIT ?"
        params = (*params, max(1, min(int(limit), 500)))

        with db.connect(paths.state_db) as conn:
            rows = conn.execute(query_sql, params).fetchall()
        return {
            "stats": stats,
            "sources": [_source_dict(paths, dict(row)) for row in rows],
            "count": len(rows),
        }

    @mcp.tool()
    def curator_list_external_resources(workspace_path: str = "") -> dict[str, Any]:
        """Return machine-local external roots used for reference sources.

        These roots come from config, typically the global
        ~/.config/curator/config.yml file. They are not written to the vault by
        this tool.
        """
        paths = _resolve_paths(workspace_path)
        config = cfg.load_config(paths)
        resources = source_tools.external_resources(config)
        return {"resources": resources, "count": len(resources)}

    @mcp.tool()
    def curator_rebind_source(
        source_id: Optional[int] = None,
        logical_source_id: str = "",
        source_path: str = "",
        file_path: str = "",
        path: str = "",
        new_path: str = "",
        apply: bool = False,
        update_hash: bool = True,
        workspace_path: str = "",
    ) -> dict[str, Any]:
        """Rebind a reference source to a new external path after approval.

        Call with apply=false first to obtain a proposal. Mutating rebinding
        requires apply=true and never edits the external file itself.
        """
        paths = _resolve_paths(workspace_path)
        lookup_path = source_path or file_path or path or logical_source_id
        row = _get_source_row(paths, source_id=source_id, source_path=lookup_path)
        if row is None:
            return {
                "ok": False,
                "state": "untracked",
                "error": "Source not found",
                "source_path": lookup_path,
            }
        if not new_path:
            return {
                "ok": False,
                "state": "error",
                "error": "new_path is required",
                "source_id": row["id"],
            }
        try:
            return source_tools.rebind_source(
                paths,
                row,
                Path(new_path),
                apply=apply,
                update_hash=update_hash,
            )
        except Exception as exc:
            return {
                "ok": False,
                "state": "error",
                "error": str(exc),
                "source_id": row["id"],
            }

    @mcp.tool()
    def curator_import_source(
        file_path: str,
        workspace_path: str = "",
        policy: str = "mirror_03_to_04",
        destination: str = "",
        dry_run: bool = False,
        logical_source_id: str = "",
    ) -> dict[str, Any]:
        """Safely import a file into 04_Resources and register it as a source.

        The default `mirror_03_to_04` policy mirrors 03_Notes paths into
        04_Resources; other external files go to 04_Resources/Imports.
        Use `policy="reference"` to register an external source in place.
        """
        paths = _resolve_paths(workspace_path)
        from . import ingest_raw as _ingest_raw

        outcome = _ingest_raw.import_source_file(
            paths,
            Path(file_path),
            policy=policy,
            destination=destination or None,
            dry_run=dry_run,
            logical_source_id=logical_source_id,
        )
        return {
            "ok": outcome.result in {_ingest_raw.AddResult.ADDED, _ingest_raw.AddResult.DEDUPED},
            "result": outcome.result.value,
            "dry_run": dry_run,
            "policy": policy,
            "source_id": outcome.source_id,
            "relpath": outcome.relpath,
            "source_path": str(outcome.source_path),
            "title": outcome.title,
            "file_type": outcome.file_type,
            "bytes": outcome.bytes,
            "word_count": outcome.word_count,
            "message": outcome.message,
        }

    @mcp.tool()
    def curator_ingest_source(
        source_id: Optional[int] = None,
        relpath: str = "",
        source_path: str = "",
        file_path: str = "",
        path: str = "",
        force: bool = False,
        run_l2_l3: bool = True,
        workspace_path: str = "",
    ) -> dict[str, Any]:
        """Run L1 summary generation and optionally L2/L3 ingest for a source.

        L3 clustering is global, so `run_l2_l3=True` can refresh shared Concept
        pages after ingesting this source.
        """
        paths = _resolve_paths(workspace_path)
        lookup_path = relpath or source_path or file_path or path
        row = _get_source_row(paths, source_id=source_id, relpath=relpath, source_path=lookup_path)
        if row is None:
            return {"state": "untracked", "error": "Source not found", "source_path": lookup_path}

        source_id_int = int(row["id"])
        config = cfg.load_config(paths)
        callbacks = _McpIngestCallbacks()
        try:
            client = llm.build_client(config)
        except Exception as exc:
            return {"error": f"Could not start LLM client: {exc}"}

        try:
            if force:
                with db.connect(paths.state_db) as conn:
                    conn.execute(
                        "UPDATE sources SET status = 'force_pending', error_reason = NULL, "
                        "l1_status = 'pending', l2_status = 'pending', "
                        "l3_status = 'pending', l4_status = 'pending', layer_error = NULL "
                        "WHERE id = ?",
                        (source_id_int,),
                    )
                    row["context_id"] = None

            context_id = row.get("context_id")
            if force or not context_id or not (paths.contexts / f"{context_id}.md").exists():
                db.set_source_layer_status(paths.state_db, source_id_int, "l1", "running")
                context_id = ingest_raw.generate_l1_summary(
                    paths,
                    source_id=source_id_int,
                    relpath=str(row["relpath"]),
                    content_hash=str(row["content_hash"]),
                    client=client,
                    config=config,
                    existing_context_id=None if force else row.get("context_id"),
                    thinking=False,
                )
                if not context_id:
                    return {"ok": False, "source_id": source_id_int, "error": "L1 summary failed"}

            ingest_result = None
            l3_pages_written = 0
            if run_l2_l3:
                with db.connect(paths.state_db) as conn:
                    conn.execute(
                        "UPDATE sources SET status = 'pending', error_reason = NULL, "
                        "l2_status = 'pending', l3_status = 'pending', layer_error = NULL "
                        "WHERE id = ?",
                        (source_id_int,),
                    )
                results = ingest_llm.run_l1_to_l3(
                    paths,
                    client,
                    lambda: callbacks,
                    mode="batch",
                    auto_discover=False,
                    thinking_for_extraction=False,
                )
                ingest_result = next(
                    (result for result in results if result.source_id == source_id_int),
                    None,
                )
                l3_pages_written = sum(
                    1
                    for event in callbacks.events
                    if event.get("kind") == "page"
                    and str(event.get("path") or "").startswith("03_Concepts/")
                )
                if ingest_result is not None and ingest_result.ok:
                    try:
                        search.update_index(paths, embed=True)
                    except Exception:
                        pass

            return {
                "ok": (not run_l2_l3) if ingest_result is None else ingest_result.ok,
                "source_id": source_id_int,
                "context_id": context_id,
                "l2": None
                if ingest_result is None
                else {
                    "created": ingest_result.fragments_created,
                    "updated": ingest_result.fragments_updated,
                    "error": ingest_result.error,
                    "skipped": ingest_result.skipped,
                },
                "l3_pages_written": l3_pages_written,
                "events": callbacks.events[-50:],
            }
        finally:
            try:
                client.close()
            except Exception:
                pass

    @mcp.tool()
    def curator_search_sources(
        query: str,
        source_id: Optional[int] = None,
        source_path: str = "",
        file_path: str = "",
        path: str = "",
        relpath: str = "",
        limit: int = 8,
        workspace_path: str = "",
    ) -> dict[str, Any]:
        """Lexically search tracked raw source files with PDF page numbers."""
        paths = _resolve_paths(workspace_path)
        lookup_path = relpath or source_path or file_path or path
        if source_id is None and lookup_path:
            row = _get_source_row(paths, source_path=lookup_path)
            if row is None:
                return {
                    "hits": [],
                    "count": 0,
                    "state": "untracked",
                    "error": "Source not found",
                    "source_path": lookup_path,
                }
            source_id = int(row["id"])
        hits = search.search_source_pages(
            paths,
            query,
            source_id=source_id,
            limit=max(1, min(int(limit), 50)),
        )
        return {
            "hits": [
                {
                    "source_id": hit.source_id,
                    "relpath": hit.relpath,
                    "file_type": hit.file_type,
                    "page": hit.page_number,
                    "score": hit.score,
                    "title": hit.title,
                    "snippet": hit.snippet,
                }
                for hit in hits
            ],
            "count": len(hits),
        }

    @mcp.tool()
    def curator_search_source(
        query: str,
        source_id: Optional[int] = None,
        source_path: str = "",
        file_path: str = "",
        path: str = "",
        relpath: str = "",
        limit: int = 8,
        workspace_path: str = "",
    ) -> dict[str, Any]:
        """Alias for source-scoped raw search with page provenance."""
        return curator_search_sources(
            query=query,
            source_id=source_id,
            source_path=source_path,
            file_path=file_path,
            path=path,
            relpath=relpath,
            limit=limit,
            workspace_path=workspace_path,
        )

    @mcp.tool()
    def curator_get_source_page(
        source_id: Optional[int] = None,
        source_path: str = "",
        file_path: str = "",
        path: str = "",
        relpath: str = "",
        page: int = 1,
        workspace_path: str = "",
    ) -> dict[str, Any]:
        """Return parsed text and provenance metadata for one source page."""
        paths = _resolve_paths(workspace_path)
        lookup_path = relpath or source_path or file_path or path
        row = _get_source_row(paths, source_id=source_id, relpath=relpath, source_path=lookup_path)
        if row is None:
            return {"error": f"Source not found: {source_id or lookup_path}"}
        source_id_int = int(row["id"])
        from . import parsers

        source_file_path = paths.root / str(row["relpath"])
        if not source_file_path.exists():
            return {"error": f"Source file missing: {row['relpath']}"}
        try:
            parsed = parsers.parse(source_file_path)
        except Exception as exc:
            return {"error": f"Parse failed: {exc}"}

        if parsed.file_type == "pdf":
            pages = parsed.metadata.get("pdf_pages") or []
            if page < 1 or page > len(pages):
                return {"error": f"Page out of range: {page}", "page_count": len(pages)}
            page_meta = dict(pages[page - 1])
            text = str(page_meta.pop("text", "") or "")
            return {
                "source_id": source_id_int,
                "relpath": row["relpath"],
                "file_type": parsed.file_type,
                "title": parsed.title,
                "page": page,
                "page_count": len(pages),
                "metadata": page_meta,
                "text": text,
            }

        return {
            "source_id": source_id_int,
            "relpath": row["relpath"],
            "file_type": parsed.file_type,
            "title": parsed.title,
            "page": None,
            "page_count": 1,
            "metadata": parsed.metadata,
            "text": parsed.text,
        }

    @mcp.tool()
    def curator_get_pdf_page(
        source_id: Optional[int] = None,
        source_path: str = "",
        file_path: str = "",
        path: str = "",
        relpath: str = "",
        page: int = 1,
        workspace_path: str = "",
    ) -> dict[str, Any]:
        """Alias for retrieving one parsed PDF page from a tracked source."""
        return curator_get_source_page(
            source_id=source_id,
            source_path=source_path,
            file_path=file_path,
            path=path,
            relpath=relpath,
            page=page,
            workspace_path=workspace_path,
        )

    @mcp.tool()
    def curator_get_provenance(
        node_id: str = "",
        wiki_path: str = "",
        source_id: Optional[int] = None,
        workspace_path: str = "",
    ) -> dict[str, Any]:
        """Resolve source provenance for a DAG node, wiki path, or source id."""
        paths = _resolve_paths(workspace_path)

        if source_id is not None:
            row = _get_source_row(paths, source_id=source_id)
            if row is None:
                return {"error": f"Source not found: {source_id}"}
            return {
                "source": _source_dict(paths, row),
                "pdf_pages": db.list_source_pdf_pages(paths.state_db, source_id),
            }

        target_path = ""
        if node_id:
            node = _read_node(paths, node_id)
            if "error" in node:
                return node
            target_path = node["path"]
            page = node
        elif wiki_path:
            target_path = _normalize_link(wiki_path)
            disk_path = paths.collections / target_path
            parsed_page = page_writer.read_page(disk_path)
            if parsed_page is None:
                return {"error": f"Page not found: {target_path}"}
            page = {
                "id": disk_path.stem,
                "path": target_path,
                "frontmatter": parsed_page.frontmatter,
                "body": parsed_page.body,
            }
        else:
            return {"error": "Provide node_id, wiki_path, or source_id."}

        fm = page.get("frontmatter", {}) or {}
        source_link = str(fm.get("source_path") or "")
        context_link = str(fm.get("parent_source") or "")
        if not source_link and page.get("id", "").startswith("CTX-"):
            source_link = str(fm.get("source_path") or "")
            context_link = f"01_Contexts/{page['id']}"

        source_relpath = _normalize_link(source_link).removesuffix(".md")
        if source_relpath and not Path(source_relpath).suffix:
            # Existing source_path links often omit .md only for markdown files.
            with db.connect(paths.state_db) as conn:
                row = conn.execute(
                    "SELECT * FROM sources WHERE relpath = ? OR relpath = ?",
                    (source_relpath, f"{source_relpath}.md"),
                ).fetchone()
        elif source_relpath:
            with db.connect(paths.state_db) as conn:
                row = conn.execute("SELECT * FROM sources WHERE relpath = ?", (source_relpath,)).fetchone()
        else:
            row = None

        if row is None and context_link:
            context_id = _id_from_link(context_link)
            with db.connect(paths.state_db) as conn:
                row = conn.execute("SELECT * FROM sources WHERE context_id = ?", (context_id,)).fetchone()

        source = _source_dict(paths, dict(row)) if row else None
        return {
            "page": {
                "id": page.get("id"),
                "path": target_path,
                "source_path": source_link,
                "parent_source": context_link,
            },
            "source": source,
            "pdf_pages": db.list_source_pdf_pages(paths.state_db, int(row["id"])) if row else [],
        }

    # ------------------------------------------------------------------
    # search — qmd-backed retrieval, with optional layer filter
    # ------------------------------------------------------------------

    @mcp.tool()
    def search_curator(
        query: str,
        mode: str = "hybrid",
        limit: int = 8,
        min_score: float = 0.6,
        workspace_path: str = "",
    ) -> dict[str, Any]:
        """Search the Curator DAG.

        IMPORTANT: If the response contains `needs_curation: true`, call
        `curator_curate_workspace` first, then retry this search.

        Args:
            query: Natural-language query.
            mode: 'hybrid' (BM25 + vector + LLM rerank, best quality), 'lex'
                  (BM25 only, fastest), 'vec' (vector only).
            limit: Max number of hits before min_score filtering.
            min_score: Drop hits below this score (0.6 = default threshold).
            workspace_path: The workspace to scope the search to. Use if WORKSPACE_PATH env var is not set.

        Returns a dict with `hits` (each has `path`, `title`, `score`, `snippet`,
        `body`), `count`, and optionally `needs_curation` with guidance.
        """
        ws_path_str = workspace_path or os.environ.get("WORKSPACE_PATH")
        paths = _resolve_paths(ws_path_str)

        # Auto-sync: if there are pending sources, curate them synchronously first
        from . import db as _db
        if _db.get_pending_count(paths.state_db) > 0:
            subprocess.run(
                ["wiki", "curate", "--no-sync"],
                cwd=str(paths.root),
                check=False,
                capture_output=True,
                env={**os.environ, "VAULT_ROOT": str(paths.root)},
            )

        # Load curate.yml if workspace_path or WORKSPACE_PATH is set
        from . import curate_yml as _cym
        ws_exh = None  # resolved below if workspace is configured
        curate_spec = None
        if ws_path_str:
            ws_path = Path(ws_path_str).expanduser().resolve()
            if not ws_path.exists():
                return {
                    "error": f"WORKSPACE_PATH does not exist: {ws_path_str}",
                    "guidance": "Set WORKSPACE_PATH to a valid workspace directory containing curate.yml.",
                    "hits": [],
                    "count": 0,
                }
            # Check if curate.yml exists — if not, return wizard questions directly
            _curate_file = ws_path / "curate.yml"
            if not _curate_file.exists():
                wiz = _build_wizard_questions(ws_path_str)
                wiz["hits"] = []
                wiz["count"] = 0
                return wiz
            try:
                curate_spec = _cym.load_curate_spec(ws_path)
            except Exception as e:
                return {
                    "error": f"curate.yml invalid: {e}",
                    "guidance": f"Run: wiki workspace init {ws_path_str}",
                    "hits": [],
                    "count": 0,
                }

        if curate_spec is not None:
            # Apply confidence floor
            min_score = max(min_score, curate_spec.min_confidence)
            # Boost query with domain/topic terms
            query = curate_spec.boost_query(query)

            # Resolve workspace Exhibition: pinned in curate.yml takes priority
            from . import ingest_llm as _ingest_llm
            ws_exh = None
            if curate_spec.exhibition:
                candidate = paths.exhibitions / f"{curate_spec.exhibition}.md"
                ws_exh = candidate if candidate.exists() else None

            if ws_exh is None:
                ws_exh = _ingest_llm.find_workspace_exhibition(paths, curate_spec.project)

            # PROACTIVE CURATION: If still no exhibition, run it now instead of asking the user
            if ws_exh is None:
                try:
                    subprocess.run(
                        ["wiki", "curate", "--workspace", ws_path_str, "--no-sync"],
                        cwd=str(paths.root),
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=300,
                        env={**os.environ, "VAULT_ROOT": str(paths.root)},
                    )
                    # Retry lookup
                    ws_exh = _ingest_llm.find_workspace_exhibition(paths, curate_spec.project)
                except Exception:
                    pass

            if ws_exh is None:
                return {
                    "needs_curation": True,
                    "action_required": (
                        "1. Ensure you have run `wiki add` on some sources. "
                        "2. Call `curator_curate_workspace` manually to see detailed errors. "
                        "3. Then retry `search_curator`."
                    ),
                    "workspace_path": ws_path_str,
                    "hits": [],
                    "count": 0,
                }

        # Translate Korean queries to English for BM25/vector search
        from .llm import build_client
        from .query import translate_to_english
        try:
            config = cfg.load_config(paths)
            with build_client(config) as client:
                query = translate_to_english(client, query)
        except Exception:
            pass

        try:
            results = search.query(
                paths,
                query,
                mode=mode,
                limit=limit,
                min_score=min_score,
                hydrate=True,
                rerank=True,
            )
        except search.QmdNotInstalled as e:
            return {"error": str(e), "hits": []}
        except search.SearchBackendError as e:
            return {"error": f"qmd error: {e}", "hits": []}

        hits = []
        for hit in results.hits:
            # Apply curate.yml min_confidence filter on Exhibition pages
            if curate_spec is not None and hit.full_path.startswith("04_Exhibitions/"):
                if round(hit.score, 4) < curate_spec.min_confidence:
                    continue
            hits.append({
                "path": hit.full_path,
                "title": hit.title,
                "score": round(hit.score, 4),
                "snippet": hit.snippet,
                "body": hit.full_content,
                "docid": hit.docid,
            })

        # Append query context to workspace Exhibition (lightweight, no LLM)
        if curate_spec is not None and hits and ws_exh is not None:
            from .query import update_curation_page
            try:
                update_curation_page(paths, ws_exh, query, "", [])
            except Exception:
                pass

        return {
            "hits": hits,
            "count": len(hits),
            "curate_spec_applied": curate_spec.project if curate_spec else None,
        }

    # ------------------------------------------------------------------
    # curator_query — concept-grounded Q&A with trace (v0.2.1)
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_query(
        question: str,
        workspace_path: str = "",
        force_new: bool = False,
    ) -> dict[str, Any]:
        """Answer a question using the Curator knowledge graph (L3 concepts + L4 Exhibitions).

        This is the v0.2.1 primary query entry point for sidebar-style answers.
        It retrieves relevant L3 Concepts, synthesizes an answer with the LLM,
        creates an ephemeral query-generated Exhibition, and returns provenance
        trace data for the "Sources & Trace" plugin panel.

        Use `search_curator` for raw DAG hit retrieval without LLM synthesis.

        Args:
            question: Natural-language question to answer.
            workspace_path: Active workspace path to scope retrieval. Falls back
                to the WORKSPACE_PATH env var when not provided.
            force_new: When true, skip cache lookup and always create a fresh
                Exhibition even if a cached answer exists.

        Returns:
            ok: Whether synthesis succeeded.
            answer: Synthesized markdown answer.
            exhibition_id: EXH-<UUID8> of the generated/reused Exhibition.
            cache_hit: True if a cached Exhibition was returned.
            question: Original question echoed back.
            trace: Provenance — matched concept IDs, source paths, latency.
            error: Error message when ok=false.
        """
        import time as _time

        start = _time.monotonic()
        ws_path_str = workspace_path or os.environ.get("WORKSPACE_PATH", "")
        paths = _resolve_paths(ws_path_str)

        workspace_id = Path(ws_path_str).name if ws_path_str else "default"

        # Resolve workspace project name (for Exhibition scoping)
        workspace_project: str | None = None
        if ws_path_str:
            ws_p = Path(ws_path_str).expanduser().resolve()
            from . import curate_yml as _cym
            try:
                spec = _cym.load_curate_spec(ws_p)
                workspace_project = spec.project
            except Exception:
                workspace_project = ws_p.name

        # Check whether a cached Exhibition already answers this question.
        # Cache key = sha256 prefix of (workspace_id + normalized question).
        import hashlib as _hashlib
        _norm_q = question.strip().lower()
        cache_key = _hashlib.sha256(f"{workspace_id}:{_norm_q}".encode()).hexdigest()[:16]

        if not force_new:
            for _exh_file in sorted(paths.exhibitions.glob("EXH-*.md"), reverse=True):
                _page = page_writer.read_page(_exh_file)
                if _page and _page.frontmatter.get("cache_key") == cache_key:
                    _latency = int((_time.monotonic() - start) * 1000)
                    _exh_id = _page.frontmatter.get("id", _exh_file.stem)
                    _concepts = _page.frontmatter.get("core_concepts") or []
                    return {
                        "ok": True,
                        "answer": _page.body.strip(),
                        "exhibition_id": _exh_id,
                        "cache_hit": True,
                        "question": question,
                        "trace": {
                            "matched_concepts": _concepts,
                            "source_ids": [],
                            "source_paths": [],
                            "latency_ms": _latency,
                            "l3_complete": True,
                        },
                    }

        # Build LLM client and run query pipeline
        from . import llm as _llm
        from . import query as _query

        try:
            config = cfg.load_config(paths)
        except Exception as e:
            return {"ok": False, "question": question, "error": f"Config error: {e}"}

        _con_dir = paths.concepts if hasattr(paths, "concepts") else paths.collections / "03_Concepts"
        l3_complete = any(_con_dir.glob("CON-*.md")) if _con_dir.exists() else False
        if not l3_complete:
            fallback_hits: list[dict[str, Any]] = []
            try:
                raw_results = search.query(
                    paths,
                    question,
                    mode="lex",
                    limit=8,
                    min_score=0.0,
                    hydrate=False,
                    rerank=False,
                )
                fallback_hits = [
                    {
                        "path": hit.full_path,
                        "title": hit.title,
                        "score": hit.score,
                        "snippet": hit.snippet,
                    }
                    for hit in raw_results.hits
                ]
            except Exception:
                fallback_hits = []
            return {
                "ok": True,
                "answer": "",
                "exhibition_id": "",
                "cache_hit": False,
                "question": question,
                "fallback": "l3_incomplete",
                "fallback_hits": fallback_hits,
                "trace": {
                    "matched_concepts": [],
                    "source_ids": [],
                    "source_paths": [hit.get("path", "") for hit in fallback_hits],
                    "latency_ms": int((_time.monotonic() - start) * 1000),
                    "l3_complete": False,
                },
            }

        session_id = f"QRY-{uuid.uuid4().hex[:8]}"

        class _SilentCallbacks(_query.QueryCallbacks):
            pass

        try:
            with _llm.build_client(config) as client:
                result = _query.run_query(
                    paths,
                    client,
                    question,
                    _SilentCallbacks(),
                    mode="hybrid",
                    limit=8,
                    min_score=0.5,
                    rerank=True,
                    save_as=question[:60],
                    temperature=0.3,
                    scope="all",
                    session_id=session_id,
                    workspace_project=workspace_project,
                    ephemeral_exhibition=True,
                )
        except Exception as e:
            return {"ok": False, "question": question, "error": f"Query pipeline error: {e}"}

        latency_ms = int((_time.monotonic() - start) * 1000)

        if not result.ok:
            return {
                "ok": False,
                "question": question,
                "error": result.error or "Query returned no answer",
            }

        # Extract provenance from hits
        matched_concepts: list[str] = []
        source_paths: list[str] = []
        source_ids: list[int] = []
        for hit in result.hits:
            if hit.full_path.startswith("03_Concepts/"):
                con_id = Path(hit.full_path).stem
                if con_id not in matched_concepts:
                    matched_concepts.append(con_id)
            sp = hit.full_path
            if sp not in source_paths:
                source_paths.append(sp)

        exh_id = Path(result.saved_path).stem if result.saved_path else ""

        # Update cache_key on the saved Exhibition so future cache lookups work
        if exh_id and result.saved_path:
            _exh_path = paths.collections / result.saved_path
            if _exh_path.exists():
                _page = page_writer.read_page(_exh_path)
                if _page:
                    _page.frontmatter["cache_key"] = cache_key
                    _page.frontmatter["workspace_id"] = workspace_id
                    if ws_path_str:
                        _page.frontmatter["workspace_path"] = ws_path_str
                    page_writer.write_page(_exh_path, _page.to_markdown())

        return {
            "ok": True,
            "answer": result.answer,
            "exhibition_id": exh_id,
            "cache_hit": False,
            "question": question,
            "trace": {
                "matched_concepts": matched_concepts,
                "source_ids": source_ids,
                "source_paths": source_paths,
                "latency_ms": latency_ms,
                "l3_complete": l3_complete,
            },
        }

    # ------------------------------------------------------------------
    # promote_exhibition — promote query-gen EXH to 02_Wiki/ (v0.2.1)
    # ------------------------------------------------------------------

    @mcp.tool()
    def promote_exhibition(
        exh_id: str,
        workspace_path: str = "",
    ) -> dict[str, Any]:
        """Promote a query-generated Exhibition to 02_Wiki/ as a human-verified artifact.

        This must only be called after explicit user approval. Promotion sets
        `is_verified_by_human=true` on the Exhibition and writes a permanent
        copy to `02_Wiki/<category>/<slug>.md`.

        The plugin must not call this automatically; it always requires a human action.

        Args:
            exh_id: Exhibition ID to promote, e.g. "EXH-12345678".
            workspace_path: Optional workspace path to resolve the vault.

        Returns:
            ok: Whether promotion succeeded.
            exhibition_id: Echoed EXH ID.
            promoted_to: Vault-relative path of the promoted wiki page.
            error: Error message when ok=false.
        """
        paths = _resolve_paths(workspace_path)

        exh_file = paths.exhibitions / f"{exh_id}.md"
        if not exh_file.exists():
            return {"ok": False, "exhibition_id": exh_id, "error": f"Exhibition {exh_id} not found"}

        page = page_writer.read_page(exh_file)
        if page is None:
            return {"ok": False, "exhibition_id": exh_id, "error": f"Cannot read {exh_id}"}

        question = page.frontmatter.get("question") or ""
        answer = page.body.strip()

        # Use LLM to classify category/slug for the wiki page path
        from . import query as _query
        from . import llm as _llm
        category = "General"
        slug = ""
        try:
            config = cfg.load_config(paths)
            with _llm.build_client(config) as client:
                category, slug = _query.classify_wiki_topic(client, question, answer)
        except Exception:
            pass

        if not slug:
            import re as _re
            slug = _re.sub(r"[^\w\s-]", "", question).strip()
            slug = _re.sub(r"\s+", "-", slug)[:60].strip("-") or exh_id.lower()

        # Write to 02_Wiki/
        try:
            wiki_path = _query.save_wiki_page(paths, question, answer, category, slug)
        except Exception as e:
            return {"ok": False, "exhibition_id": exh_id, "error": f"Failed to write wiki page: {e}"}

        # Update Exhibition frontmatter to reflect promotion
        page.frontmatter["exhibition_origin"] = "promoted"
        page.frontmatter["ephemeral"] = False
        page.frontmatter["is_verified_by_human"] = True
        page.frontmatter["promoted_to"] = wiki_path
        page.frontmatter["last_updated"] = page_writer.today_iso()
        page_writer.write_page(exh_file, page.to_markdown())

        return {
            "ok": True,
            "exhibition_id": exh_id,
            "promoted_to": wiki_path,
        }

    # ------------------------------------------------------------------
    # curator_curate_workspace — create or refresh the workspace Exhibition
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_curate_workspace(workspace_path: str = "") -> dict[str, Any]:
        """Create or refresh the L4 Exhibition for a workspace, then reindex.

        Call this when `search_curator` returns `needs_curation: true`, or after
        `curator_update_node` / `curator_add_knowledge` to stage a fresh Exhibition
        from the updated L3 Concepts.

        Args:
            workspace_path: Absolute path to workspace containing curate.yml.
                            Defaults to the WORKSPACE_PATH environment variable.

        Returns `{'ok': True, 'exhibition': 'EXH-xxxx.md'}` on success.
        """
        ws = workspace_path or os.environ.get("WORKSPACE_PATH", "")
        if not ws:
            return {"error": "workspace_path required (or set WORKSPACE_PATH env var)"}

        paths = _resolve_paths(ws)
        result = subprocess.run(
            ["wiki", "curate", "--workspace", ws, "--no-sync"],
            cwd=str(paths.root),
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
            env={**os.environ, "VAULT_ROOT": str(paths.root)},
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip() or "wiki curate failed"}

        from . import ingest_llm as _ingest_llm
        from . import curate_yml as _cym
        spec = _cym.load_curate_spec(Path(ws).expanduser().resolve())
        project = spec.project if spec else ws

        # find_workspace_exhibition is now usually sufficient since project name
        # is synchronized with curate.yml.
        ws_exh = _ingest_llm.find_workspace_exhibition(paths, project)

        # No need to manually update_index here as 'wiki curate' already did it.
        return {"ok": True, "exhibition": ws_exh.name if ws_exh else None}

    # ------------------------------------------------------------------
    # curator_check_workspace — validate workspace configuration health
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_check_workspace(
        workspace_path: str = "",
        ctx: Context = None,
    ) -> dict[str, Any]:
        """Check workspace configuration health and return setup guidance.

        Call this at the start of each session when WORKSPACE_PATH is set.
        Validates that curate.yml exists and is valid, checks whether a workspace
        Exhibition has been generated, and auto-installs agent rules for the
        connecting client (Claude Code, Gemini CLI, etc.) if not yet present.

        Args:
            workspace_path: Absolute path to workspace. Defaults to WORKSPACE_PATH env var.

        Returns a dict with `ok` (bool), `workspace`, `project`, `exhibition`,
        `exhibition_exists`, `agent_rules_installed` (if newly installed), and
        `issues` (list of actionable error messages).
        """
        from . import curate_yml as _cym
        from . import ingest_llm as _ingest_llm

        ws = workspace_path or os.environ.get("WORKSPACE_PATH", "")
        paths = _resolve_paths(ws)
        issues: list[str] = []

        if not ws:
            issues.append(
                "WORKSPACE_PATH is not set. "
                "Start the MCP server with WORKSPACE_PATH=/path/to/workspace, "
                "or call curator_check_workspace('/path/to/workspace')."
            )
            return {"ok": False, "issues": issues}

        ws_path = Path(ws).expanduser().resolve()
        if not ws_path.exists():
            issues.append(
                f"Workspace directory does not exist: {ws}. "
                "Create it with: wiki workspace init /path/to/workspace"
            )
            return {"ok": False, "issues": issues}

        curate_file = ws_path / "curate.yml"
        if not curate_file.exists():
            wiz = _build_wizard_questions(ws)
            wiz["ok"] = True
            return wiz

        try:
            spec = _cym.load_curate_spec(ws_path)
        except Exception as e:
            issues.append(
                f"curate.yml is invalid: {e}. "
                "Run: wiki workspace init /path/to/workspace --force-curate"
            )
            return {"ok": False, "workspace": ws, "issues": issues}

        if spec is None:
            issues.append("curate.yml loaded but returned empty spec.")
            return {"ok": False, "workspace": ws, "issues": issues}

        # Resolve exhibition: pinned in spec or auto-detected
        exh_path = None
        if spec.exhibition:
            candidate = paths.exhibitions / f"{spec.exhibition}.md"
            exh_path = candidate if candidate.exists() else None
            if exh_path is None:
                issues.append(
                    f"Pinned exhibition '{spec.exhibition}' not found. "
                    "Call curator_curate_workspace() to regenerate it."
                )
        else:
            exh_path = _ingest_llm.find_workspace_exhibition(paths, spec.project)

        if exh_path is None:
            issues.append(
                "No workspace Exhibition found. "
                "Call curator_curate_workspace() to generate one from the knowledge graph."
            )

        # Auto-install agent rules for the connecting client
        agent_rules_installed = None
        detected_agent = "codex"
        try:
            from .workspace.provisioner import detect_agent_from_client_info, detect_workspace_scenario, prepare_workspace
            client_name = ""
            if ctx is not None:
                try:
                    client_name = (
                        ctx.session.client_params.clientInfo.name or ""
                    ) if (
                        ctx.session
                        and ctx.session.client_params
                        and ctx.session.client_params.clientInfo
                    ) else ""
                except Exception:
                    client_name = ""
            detected_agent = detect_agent_from_client_info(client_name)
            agent_marker = ws_path / ".agents" / "curator" / "runtime" / f"{detected_agent}.md"

            # Reinstall if marker is missing OR if it contains a stale/wrong vault root.
            # This auto-heals workspaces that were initialised against the wrong vault.
            needs_install = not agent_marker.exists()
            if not needs_install:
                try:
                    if str(paths.root) not in agent_marker.read_text(encoding="utf-8"):
                        needs_install = True
                except Exception:
                    needs_install = True

            if needs_install:
                prepare_workspace(
                    vault_root=paths.root,
                    workspace=ws_path,
                    agent=detected_agent,
                    install_rules=True,
                    force_curate=False,
                )
                agent_rules_installed = detected_agent
        except Exception:
            pass

        try:
            _scenario = detect_workspace_scenario(ws_path, detected_agent)
        except Exception:
            _scenario = "full"

        result: dict[str, Any] = {
            "ok": len(issues) == 0,
            "workspace": ws,
            "project": spec.project,
            "scenario": _scenario,
            "exhibition": exh_path.stem if exh_path else None,
            "exhibition_exists": exh_path is not None,
            "issues": issues,
        }
        if agent_rules_installed is not None:
            result["agent_rules_installed"] = agent_rules_installed
        return result

    # ------------------------------------------------------------------
    # curator_workspace_init — initialize a new workspace
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_workspace_init(
        workspace_path: str,
        project: Optional[str] = None,
        description: Optional[str] = None,
        domains: Optional[list[str]] = None,
        topics: Optional[list[str]] = None,
        include_patterns: Optional[list[str]] = None,
        exclude_patterns: Optional[list[str]] = None,
        min_confidence: Optional[float] = None,
        ctx: Context = None,
    ) -> dict[str, Any]:
        """Initialize a new Curator workspace with curate.yml, agent rules, and an
        auto-generated Artist persona.

        TWO-PHASE USAGE:
          Phase 1 — Discovery: Call with ONLY `workspace_path` (no other args).
            Returns `wizard_questions` — a list of questions to ask the user.
            Present these to the user and collect their answers.
          Phase 2 — Initialization: Call again with all gathered data.
            Writes curate.yml, installs agent rules, generates Artist persona.

        Call this when `curator_check_workspace` or `search_curator` returns
        `needs_initialization: true`.

        Args:
            workspace_path: Absolute path to the directory to initialize.
            project: Short slug for the project (e.g. 'gaussian-splatting').
                     Defaults to the directory name.
            description: Human-readable description (collected from user in Phase 1).
            domains: List of domain keywords (e.g. ['computer-vision', 'rendering']).
            topics: List of specific topic keywords (e.g. ['3DGS', '2DGS', 'NeRF']).
            include_patterns: List of glob patterns to include in the workspace.
            exclude_patterns: List of glob patterns to exclude from the workspace.
            min_confidence: Minimum confidence floor for search results (default 0.60).

        Returns (Phase 1 — no description provided):
            wizard_questions: List of questions to ask the user before Phase 2.

        Returns (Phase 2 — description provided):
            ok: True on success.
            workspace: Resolved absolute path.
            agent: Detected agent runtime.
            created: List of newly created files.
            updated: List of updated files.
            persona: The generated Artist persona dict.
            next_steps: List of actions to take after init.
        """
        from .workspace.provisioner import (
            prepare_workspace,
            CurateTemplateData,
            detect_agent_from_client_info,
            detect_workspace_scenario,
            default_project_name,
            make_rule_integration_prompt,
            make_integration_copy_prompt,
            top_level_target,
        )

        ws_path = Path(workspace_path).expanduser().resolve()

        # ── Phase 1: Dynamic Interview Logic ───────────────────────────────
        provided_answers = {
            "description": description,
            "domains": domains,
            "topics": topics,
            "include_patterns": include_patterns,
            "exclude_patterns": exclude_patterns,
            "min_confidence": min_confidence,
        }
        # Filter out None values to see what we have
        provided_answers = {k: v for k, v in provided_answers.items() if v is not None}

        # If we don't have enough to finish, keep interviewing
        wiz = _build_wizard_questions(workspace_path, provided_answers)
        if not wiz.get("all_answered"):
            return wiz

        # Phase 2: all interview answers collected — now resolve the vault
        paths = _resolve_paths(workspace_path)

        # ── 1. Detect connecting agent runtime ─────────────────────────────
        client_name = ""
        if ctx is not None:
            try:
                client_name = (
                    ctx.session.client_params.clientInfo.name or ""
                ) if (
                    ctx.session
                    and ctx.session.client_params
                    and ctx.session.client_params.clientInfo
                ) else ""
            except Exception:
                pass
        agent = detect_agent_from_client_info(client_name)

        # ── 1b. Agent-only: try LLM integration of Curator into existing rules ──
        _scenario = detect_workspace_scenario(ws_path, agent)
        _llm_integrated = False
        _integration_prompt: str | None = None
        if _scenario == "agent-only":
            try:
                rule_file, _ = top_level_target(agent)
                rule_path = ws_path / rule_file
                if rule_path.exists():
                    existing = rule_path.read_text(encoding="utf-8")
                    if existing.strip():
                        prompt_text = make_rule_integration_prompt(existing, agent, str(ws_path))
                        from .llm import build_client, ChatMessage
                        _config = cfg.load_config(paths)
                        with build_client(_config) as _client:
                            modified = _client.chat(
                                [ChatMessage(role="user", content=prompt_text)],
                                temperature=0.2,
                            )
                        modified = modified.strip()
                        if modified and modified != existing.strip():
                            rule_path.write_text(modified + "\n", encoding="utf-8")
                            _llm_integrated = True
            except Exception:
                pass
            if not _llm_integrated:
                try:
                    rule_file, _ = top_level_target(agent)
                    _integration_prompt = make_integration_copy_prompt(agent, rule_file)
                except ValueError:
                    pass

        # ── 1c. Patterns are treated as vault-relative ───────────────────
        def _process_patterns(patterns: list[str] | None) -> list[str]:
            if not patterns:
                return []
            cleaned = []
            for p in patterns:
                # Strip wizard labels if any
                p = p.replace("[Vault] ", "").strip()
                if not p:
                    continue
                cleaned.append(p)
            return cleaned

        # ── 2. Scaffold curate.yml + agent rules ────────────────────────────
        project_name = project or default_project_name(ws_path)

        # If no include_patterns provided, default to the standard knowledge directories
        final_includes = _process_patterns(include_patterns)
        if not final_includes:
            final_includes = ["02_Wiki/**", "03_Notes/**", "04_Resources/**"]

        data = CurateTemplateData(
            project=project_name,
            description=description or f"Knowledge workspace for {ws_path.name}",
            min_confidence=min_confidence if min_confidence is not None else 0.60,
            include_patterns=final_includes,
            exclude_patterns=_process_patterns(exclude_patterns),
        )
        try:
            prep = prepare_workspace(
                vault_root=paths.root,
                workspace=ws_path,
                agent=agent,
                curate_data=data,
                install_rules=True,
                install_managed_block=not _llm_integrated,
            )
        except Exception as e:
            return {"error": f"Workspace scaffolding failed: {e}"}

        created = [str(p.relative_to(ws_path)) for p in prep.created]
        updated = [str(p.relative_to(ws_path)) for p in prep.updated]

        # ── 3. Auto-generate Artist persona via LLM ─────────────────────────
        # Build a concise project description for the LLM to work from.
        meta_parts = [f"Project: {project_name}"]
        if description:
            meta_parts.append(f"Description: {description}")
        if domains:
            meta_parts.append(f"Domains: {', '.join(domains)}")
        if topics:
            meta_parts.append(f"Topics: {', '.join(topics)}")
        project_context = "\n".join(meta_parts)

        PERSONA_GEN_PROMPT = (
            "You are a knowledge-base configuration assistant.\n\n"
            "Given the following project metadata, generate an Artist persona JSON "
            "for a Curator workspace. Return ONLY valid JSON — no prose, no fences.\n\n"
            "Required JSON schema:\n"
            "{\n"
            '  "domain": "primary domain slug, e.g. computer-vision",\n'
            '  "subdomain": "more specific focus (optional, can be empty string)",\n'
            '  "goal": "2-4 sentences describing this workspace\'s knowledge goal",\n'
            '  "exhibition_intent": "researcher | engineer | learner",\n'
            '  "disambiguation_keywords": ["3-8 workspace-specific terms"],\n'
            '  "confidence": {"high_threshold": 0.85, "low_threshold": 0.55}\n'
            "}\n\n"
            "exhibition_intent meanings:\n"
            "  researcher — next papers/hypotheses to validate\n"
            "  engineer   — specific code/system implementation steps\n"
            "  learner    — concepts to review and practice exercises\n\n"
            f"Project metadata:\n{project_context}\n\n"
            "Return ONLY the JSON object."
        )

        persona: dict | None = None
        persona_error: str | None = None
        try:
            from .llm import build_client, ChatMessage
            _config = cfg.load_config(paths)
            with build_client(_config) as _client:
                raw = _client.chat(
                    [ChatMessage(role="user", content=PERSONA_GEN_PROMPT)],
                    temperature=0.3,
                )
            # Strip markdown fences if present
            raw_stripped = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
            persona = json.loads(raw_stripped)
            if not isinstance(persona, dict):
                raise ValueError("LLM returned non-object JSON")
        except Exception as e:
            persona_error = str(e)
            persona = None

        # ── 4. Write persona into curate.yml ────────────────────────────────
        if persona is not None:
            import yaml as _yaml
            curate_file = ws_path / "curate.yml"
            try:
                raw_yml = _yaml.safe_load(curate_file.read_text(encoding="utf-8")) or {}
                persona["updated_at"] = datetime.now(timezone.utc).isoformat()
                raw_yml["persona"] = persona
                curate_file.write_text(
                    _yaml.safe_dump(raw_yml, sort_keys=False, default_flow_style=False),
                    encoding="utf-8",
                )
                if "curate.yml" not in updated:
                    updated.append("curate.yml")
            except Exception as e:
                persona_error = f"Persona generated but could not be saved: {e}"

        # ── 5. Trigger initial curation (Automatic Curation) ───────────────
        initial_exhibition: str | None = None
        curation_error: str | None = None
        try:
            result = subprocess.run(
                [sys.executable, "-m", "curator.cli", "curate", "--workspace", str(ws_path), "--no-sync"],
                cwd=str(paths.root),
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
                env={**os.environ, "VAULT_ROOT": str(paths.root)},
            )
            if result.returncode != 0:
                curation_error = result.stderr.strip() or result.stdout.strip() or f"Exit code {result.returncode}"

            # Re-load spec to get the newly written exhibition ID
            from . import curate_yml as _cym
            from . import ingest_llm as _ingest_llm
            spec = _cym.load_curate_spec(ws_path)
            if spec and spec.exhibition:
                initial_exhibition = spec.exhibition
            else:
                # Fallback lookup
                ws_exh = _ingest_llm.find_workspace_exhibition(paths, spec.project if spec else project_name)
                if ws_exh:
                    initial_exhibition = ws_exh.stem
        except Exception as e:
            curation_error = str(e)

        # ── 6. Return result ────────────────────────────────────────────────
        # Only surface steps that genuinely require another MCP call.
        # Curation and reindex were already attempted inline above.
        next_steps = [
            f"search_curator('<query>', workspace_path='{ws_path}') — Search the knowledge base",
            f"curator_update_artist_persona('{ws_path}', '<description>') — Refine workspace persona",
        ]
        if not initial_exhibition:
            next_steps.insert(
                0,
                f"curator_curate_workspace('{ws_path}') — Generate L4 Exhibition (initial attempt failed or no concepts matched yet)",
            )
        if persona_error:
            next_steps.insert(
                0,
                f"ERROR: Persona auto-generation failed ({persona_error}). Run curator_update_artist_persona to set it manually.",
            )

        result: dict[str, Any] = {
            "ok": True,
            "workspace": str(ws_path),
            "agent": agent,
            "scenario": prep.scenario,
            "created": created,
            "updated": updated,
            "persona": persona,
            "recommended_next_steps": next_steps,
        }
        if persona_error:
            result["persona_error"] = persona_error
        if curation_error:
            result["curation_error"] = curation_error
        if _llm_integrated:
            result["rule_integration"] = "llm_auto"
        if _integration_prompt:
            result["integration_prompt"] = _integration_prompt
        return result

    # ------------------------------------------------------------------
    # curator_get_node — fetch any DAG node by ID
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_get_node(node_id: str, workspace_path: str = "") -> dict[str, Any]:
        """Fetch a single DAG node (Context/Atom/Concept/Exhibition) by ID.

        Args:
            node_id: e.g. 'EXH-abcdef01', 'ATM-9f8e7d6c'. Prefix determines
                     the layer.
            workspace_path: Optional workspace path to help resolve the vault.

        Returns the node's frontmatter + body, or `{'error': ...}` if missing.
        """
        paths = _resolve_paths(workspace_path)
        return _read_node(paths, node_id)

    # ------------------------------------------------------------------
    # curator_traverse_evidence — walk SYN → CON → ATM
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_traverse_evidence(cur_id: str, workspace_path: str = "") -> dict[str, Any]:
        """Walk an Exhibition's evidence chain down to its constituent Atoms.

        Returns the full EXH page plus every CON it depends on and every ATM
        each CON depends on, including confidence/contradiction flags. Use
        this to verify an Exhibition claim before citing it (especially when
        confidence_score < 0.90).

        Args:
            cur_id: The ID of the Exhibition (EXH-) or Concept (CON-) to traverse.
            workspace_path: Optional workspace path to help resolve the vault.
        """
        paths = _resolve_paths(workspace_path)
        cur = _read_node(paths, cur_id)
        if "error" in cur:
            return cur
        if cur["layer"] != "exhibition":
            return {"error": f"{cur_id} is a {cur['layer']}, not an exhibition."}

        concepts: list[dict[str, Any]] = []
        atoms: list[dict[str, Any]] = []
        seen_atoms: set[str] = set()

        for raw_link in cur["frontmatter"].get("core_concepts", []) or []:
            if not isinstance(raw_link, str):
                continue
            con_id = _id_from_link(raw_link)
            con = _read_node(paths, con_id)
            if "error" in con:
                concepts.append({"id": con_id, "error": con["error"]})
                continue
            concepts.append(con)

            for atm_id in _concept_atom_ids(con):
                if atm_id in seen_atoms:
                    continue
                seen_atoms.add(atm_id)
                atoms.append(_read_node(paths, atm_id))

        return {
            "exhibition": cur,
            "confidence_score": cur["frontmatter"].get("confidence_score"),
            "concepts": concepts,
            "atoms": atoms,
            "flagged_atom_count": sum(
                1 for a in atoms if a.get("frontmatter", {}).get("is_flagged_for_agent")
            ),
        }

    # ------------------------------------------------------------------
    # curator_find_contradictions — atoms with conflicting claims
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_find_contradictions(
        node_id: Optional[str] = None,
        workspace_path: str = "",
    ) -> dict[str, Any]:
        """List Atoms that are flagged for human review or carry `contradicts`
        entries.

        Each entry includes a `dismissed` field indicating whether the pair has
        been dismissed as a false positive via `curator_dismiss_contradiction`.

        Args:
            node_id: Optional. If given, returns contradictions only for the
                     subgraph reachable from this node (EXH/CON/ATM). Else
                     returns all flagged atoms in the vault.
            workspace_path: Optional workspace path to help resolve the vault.
        """
        paths = _resolve_paths(workspace_path)
        from . import contradiction as _cd
        dismissed_list = _cd.load_dismissed(paths)

        def _enrich(entry: dict[str, Any]) -> dict[str, Any]:
            atm_id = entry["id"]
            # Check if this atom is part of any dismissed pair
            for dismissed_entry in dismissed_list:
                if atm_id in dismissed_entry["pair"]:
                    entry["dismissed"] = True
                    entry["dismissed_reason"] = dismissed_entry.get("reason", "")
                    return entry
            entry["dismissed"] = False
            return entry

        flagged: list[dict[str, Any]] = []

        if node_id is None:
            atoms_dir = paths.atoms
            if not atoms_dir.exists():
                return {"flagged_atoms": [], "count": 0, "dismissed_count": 0}
            for md in sorted(atoms_dir.glob("ATM-*.md")):
                parsed = page_writer.read_page(md)
                if parsed is None:
                    continue
                fm = parsed.frontmatter
                if fm.get("is_flagged_for_agent") or fm.get("contradicts"):
                    entry = {
                        "id": fm.get("id") or md.stem,
                        "path": f"02_Atoms/{md.name}",
                        "is_flagged_for_agent": bool(fm.get("is_flagged_for_agent")),
                        "contradicts": fm.get("contradicts") or [],
                        "claim_type": fm.get("claim_type"),
                        "title_preview": (parsed.body.splitlines()[0] if parsed.body else "").lstrip("# ").strip(),
                    }
                    flagged.append(_enrich(entry))
            dismissed_count = sum(1 for e in flagged if e.get("dismissed"))
            return {"flagged_atoms": flagged, "count": len(flagged), "dismissed_count": dismissed_count}

        # Node-scoped: traverse to atoms and filter
        info = _layer_for_id(node_id)
        if info is None:
            return {"error": f"Unknown ID prefix in '{node_id}'"}

        if info[0] == "atom":
            atom = _read_node(paths, node_id)
            if "error" in atom:
                return atom
            fm = atom["frontmatter"]
            if fm.get("is_flagged_for_agent") or fm.get("contradicts"):
                entry = {
                    "id": node_id,
                    "path": atom["path"],
                    "is_flagged_for_agent": bool(fm.get("is_flagged_for_agent")),
                    "contradicts": fm.get("contradicts") or [],
                }
                flagged.append(_enrich(entry))
            return {"flagged_atoms": flagged, "count": len(flagged), "dismissed_count": sum(1 for e in flagged if e.get("dismissed"))}

        # EXH or CON: walk down to atoms via traversal logic
        atom_ids: set[str] = set()
        if info[0] == "exhibition":
            chain = curator_traverse_evidence(node_id)
            for atm in chain.get("atoms", []):
                if "id" in atm:
                    atom_ids.add(atm["id"])
        elif info[0] == "concept":
            con = _read_node(paths, node_id)
            atom_ids.update(_concept_atom_ids(con))

        for aid in atom_ids:
            atm = _read_node(paths, aid)
            if "error" in atm:
                continue
            fm = atm["frontmatter"]
            if fm.get("is_flagged_for_agent") or fm.get("contradicts"):
                entry = {
                    "id": aid,
                    "path": atm["path"],
                    "is_flagged_for_agent": bool(fm.get("is_flagged_for_agent")),
                    "contradicts": fm.get("contradicts") or [],
                }
                flagged.append(_enrich(entry))
        dismissed_count = sum(1 for e in flagged if e.get("dismissed"))
        return {"flagged_atoms": flagged, "count": len(flagged), "dismissed_count": dismissed_count}

    # ------------------------------------------------------------------
    # curator_dismiss_contradiction — mark a pair as false positive
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_dismiss_contradiction(
        atom_a: str,
        atom_b: str,
        reason: str = "",
        workspace_path: str = "",
    ) -> dict[str, Any]:
        """Dismiss a deep-check contradiction as a false positive.

        Future `wiki sync` runs will skip this pair permanently.
        Also clears `is_flagged_for_agent` on both Atom files.

        Args:
            atom_a: ATM-id or path like '02_Atoms/ATM-xxx.md'.
            atom_b: ATM-id or path like '02_Atoms/ATM-yyy.md'.
            reason: Optional explanation (logged to contradiction_dismissed.json).
            workspace_path: Optional workspace path to help resolve the vault.

        Returns `{'ok': True, 'dismissed': [atom_a_id, atom_b_id]}`.
        """
        paths = _resolve_paths(workspace_path)
        from . import contradiction as _cd
        try:
            a = _cd.normalize_id(atom_a)
            b = _cd.normalize_id(atom_b)
            _cd.add_dismissed(paths, a, b, reason=reason)
            _cd.clear_flagged(paths, a, b)
            return {"ok": True, "dismissed": [a, b]}
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # curator_resolve_contradiction — LLM-powered L2 Atom resolution
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_resolve_contradiction(
        atom_a: str,
        atom_b: str,
        apply: bool = False,
        workspace_path: str = "",
    ) -> dict[str, Any]:
        """Analyze and optionally resolve a contradiction between two L2 Atoms.

        This is the sole MCP tool authorized to write L2 Atom body content,
        specifically for resolving a flagged contradiction.

        Args:
            atom_a: ATM-id or '02_Atoms/ATM-xxx.md'.
            atom_b: ATM-id or '02_Atoms/ATM-yyy.md'.
            apply:  False (default) — return the proposal for review.
                    True — apply the proposal and mark resolved.
            workspace_path: Optional workspace path to help resolve the vault.

        Workflow:
            1. Call with apply=False to get the LLM proposal.
            2. Review `atom_a_body_revised` and `atom_b_body_revised`.
            3. Call again with apply=True to write the changes.

        Returns a dict with `reasoning`, `atom_a_body_revised`,
        `atom_b_body_revised`, and `applied` (bool).
        """
        paths = _resolve_paths(workspace_path)
        from . import contradiction as _cd
        from .prompts import build_contradiction_resolution_messages
        from .llm import build_client, LLMError

        a_id = _cd.normalize_id(atom_a)
        b_id = _cd.normalize_id(atom_b)

        page_a = page_writer.read_page(paths.atoms / f"{a_id}.md")
        page_b = page_writer.read_page(paths.atoms / f"{b_id}.md")
        if page_a is None:
            return {"error": f"Atom not found: {a_id}"}
        if page_b is None:
            return {"error": f"Atom not found: {b_id}"}

        try:
            _config = cfg.load_config(paths)
            _client = build_client(_config)
        except Exception as exc:
            return {"error": f"Could not start LLM client: {exc}"}

        try:
            messages = build_contradiction_resolution_messages(
                path_a=f"02_Atoms/{a_id}.md",
                content_a=page_a.to_markdown(),
                path_b=f"02_Atoms/{b_id}.md",
                content_b=page_b.to_markdown(),
                conflict_reasoning="",
            )
            raw = _client.chat(messages, thinking=False, json_mode=True, temperature=0.3)
            proposal = json.loads(raw)
        except (LLMError, json.JSONDecodeError, Exception) as exc:
            return {"error": f"LLM resolution failed: {exc}"}
        finally:
            try:
                _client.close()
            except Exception:
                pass

        if apply:
            _cd.apply_resolution(paths, a_id, b_id, proposal)
            return {
                "reasoning": proposal.get("reasoning", ""),
                "atom_a_body_revised": proposal.get("atom_a_body_revised", ""),
                "atom_b_body_revised": proposal.get("atom_b_body_revised", ""),
                "applied": True,
            }

        return {
            "reasoning": proposal.get("reasoning", ""),
            "atom_a_body_revised": proposal.get("atom_a_body_revised", ""),
            "atom_b_body_revised": proposal.get("atom_b_body_revised", ""),
            "applied": False,
        }

    # ------------------------------------------------------------------
    # curator_layer_index — high-level routing table
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_layer_index(workspace_path: str = "") -> dict[str, Any]:
        """Return per-layer page counts and a sample of recent IDs.

        Layers: context (CTX-), atom (ATM-), concept (CON-), exhibition (EXH-).
        Cheap overview suitable as the agent's first call when entering a
        fresh vault — tells it what's available before any search.

        Args:
            workspace_path: Optional workspace path to help resolve the vault.
        """
        paths = _resolve_paths(workspace_path)
        out: dict[str, Any] = {"vault_root": str(paths.root), "layers": {}}
        for layer, (subdir, _prefix) in _LAYERS.items():
            d = paths.collections / subdir
            if not d.exists():
                out["layers"][layer] = {"count": 0, "samples": []}
                continue
            files = sorted(
                (p for p in d.glob("*.md") if not p.name.startswith(".")),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            out["layers"][layer] = {
                "count": len(files),
                "samples": [p.stem for p in files[:5]],
            }
        return out

    # ------------------------------------------------------------------
    # curator_status — vault info + qmd readiness
    # ------------------------------------------------------------------

    @mcp.tool()
    def get_available_models() -> dict[str, Any]:
        """Return the shared cloud model catalogue for client settings UI."""
        from . import models as model_catalogue

        return {
            "ok": True,
            "providers": model_catalogue.get_available_models(),
        }

    @mcp.tool()
    def curator_status(workspace_path: str = "") -> dict[str, Any]:
        """Return vault root, qmd binary readiness, and total page counts.

        Args:
            workspace_path: Optional workspace path to help resolve the vault.
        """
        paths = _resolve_paths(workspace_path)
        qmd_bin = search.get_qmd_binary()
        total = 0
        for subdir, _prefix in _LAYERS.values():
            d = paths.collections / subdir
            if d.exists():
                total += sum(1 for p in d.glob("*.md") if not p.name.startswith("."))
        return {
            "vault_root": str(paths.root),
            "collections": str(paths.collections),
            "total_pages": total,
            "qmd_binary": str(qmd_bin) if qmd_bin else None,
            "qmd_ready": search.is_available(),
            "qmd_version": search.get_version(),
        }

    # ------------------------------------------------------------------
    # curator_update_node — overwrite a node and propagate
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_update_node(
        node_id: str,
        new_content: str,
        workspace_path: str = ""
    ) -> dict[str, Any]:
        """Overwrite an L4 Exhibition and propagate changes backward through the DAG.

        Only EXH- (Exhibition) nodes may be edited directly by agents. L1/L2/L3 nodes
        are pipeline-generated and must be updated via backward propagation from L4.

        Args:
            node_id: The Exhibition to update (must start with EXH-).
            new_content: Full replacement markdown (frontmatter + body).
            workspace_path: Optional workspace path to help resolve the vault.

        Writes the Exhibition file, then runs upstream backward propagation
        (EXH → CON → ATM) via LLM so referenced Concepts and Atoms are updated
        to reflect the correction. Finally rebuilds routing tables.

        Returns a dict with `updated`, `propagation`, `gaps`, and
        `routing_tables_rebuilt`.
        """
        paths = _resolve_paths(workspace_path)
        info = _layer_for_id(node_id)
        if info is None:
            return {"error": f"Unknown ID prefix in '{node_id}' (expected EXH-)"}
        layer, subdir = info
        if layer != "exhibition":
            return {
                "error": (
                    f"Direct edits to {layer} nodes are not allowed. "
                    "Only L4 Exhibitions (EXH-) may be modified by agents. "
                    "Edit the Exhibition that references this node; "
                    "backward propagation will update L1-L3 automatically."
                )
            }
        page_path = paths.collections / subdir / f"{node_id}.md"
        if not page_path.exists():
            return {"error": f"Page not found: {subdir}/{node_id}.md"}

        page_path.write_text(new_content, encoding="utf-8")

        from . import sync as sync_module

        # Propagate upstream L4 → L3 → L2 via LLM
        propagation_summary: dict[str, Any] = {}
        try:
            from .llm import build_client
            from . import config as _cfg
            _config = _cfg.load_config(paths)
            _client = build_client(_config)
            try:
                prop_result = sync_module.propagate_upstream_from_exhibition(
                    paths, _client, exh_id=node_id
                )
                propagation_summary = {
                    "concepts_updated": prop_result.concepts_updated,
                    "atoms_updated": prop_result.atoms_updated,
                    "contexts_updated": prop_result.contexts_updated,
                    "feedback_required": prop_result.feedback_required,
                    "errors": prop_result.errors,
                }
            finally:
                try:
                    _client.close()
                except Exception:
                    pass
        except Exception as exc:
            propagation_summary = {"error": f"Upstream propagation failed: {exc}"}

        try:
            gaps = sync_module.run_mode_b(paths, node_id)
            sync_module.finalize_routing_tables(paths)
            routing_rebuilt = True
        except Exception as exc:
            return {
                "updated": True,
                "propagation": propagation_summary,
                "error": f"sync failed: {exc}",
                "routing_tables_rebuilt": False,
            }

        try:
            search.update_index(paths, embed=True)
        except Exception:
            pass

        return {
            "updated": True,
            "propagation": propagation_summary,
            "gaps": [{"layer": g.layer, "node_id": g.node_id, "message": g.message} for g in gaps],
            "routing_tables_rebuilt": routing_rebuilt,
        }

    # ------------------------------------------------------------------
    # curator_reindex — rebuild the QMD search index
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_reindex(workspace_path: str = "") -> dict[str, Any]:
        """Rebuild the QMD search index over all Collections pages.

        Call this after manually editing wiki pages or after a bulk import so
        that `search_curator` picks up the new content.

        Args:
            workspace_path: Optional workspace path to help resolve the vault.

        Returns `{'ok': True}` or `{'error': ...}`.
        """
        paths = _resolve_paths(workspace_path)
        try:
            search.update_index(paths, embed=True)
            return {"ok": True}
        except search.SearchBackendError as exc:
            return {"error": str(exc)}


    # ------------------------------------------------------------------
    # curator_add_knowledge — write a new L2 Atom from conversational insight
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_add_knowledge(
        insight: str,
        context: str = "",
        workspace_path: str = ""
    ) -> dict[str, Any]:
        """Promote a conversational insight or discussion to the human-verified Wiki space.

        This tool is used to 'capture' valuable information from a conversation
        and persist it in the project's permanent Wiki (02_Wiki/).

        Args:
            insight: The text of the knowledge to preserve.
            context: Reasoning or source context (e.g. conversation transcript snippet).
            workspace_path: Optional workspace path to help resolve the vault.

        Returns `{'ok': True, 'wiki_path': '...'}`.
        """
        paths = _resolve_paths(workspace_path)
        try:
            from .llm import build_client
            from . import config as _cfg
            _config = _cfg.load_config(paths)
            _client = build_client(_config)
        except Exception as exc:
            return {"error": f"Could not start LLM client: {exc}"}

        try:
            from . import query as query_module
            category, slug = query_module.classify_wiki_topic(_client, insight, context)
            wiki_path = query_module.save_wiki_page(paths, insight, context, category, slug)

            try:
                search.update_index(paths, embed=True)
            except Exception:
                pass

            return {
                "ok": True,
                "wiki_path": wiki_path
            }
        except Exception as exc:
            return {"error": str(exc)}
        finally:
            try:
                _client.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # curator_update_artist_persona / curator_update_curator_persona
    # ------------------------------------------------------------------

    mcp.tool()(curator_update_artist_persona)
    mcp.tool()(curator_update_curator_persona)

    return mcp


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def serve_stdio() -> None:
    """Run the MCP server over stdio. Used by `wiki mcp`."""
    server = build_server()
    server.run()  # FastMCP defaults to stdio transport


# Snippets emitted by `wiki mcp install` so the user can paste into
# Claude Desktop / Claude Code / Gemini CLI configs without us touching
# their global settings files directly.

CLAUDE_SNIPPET_TEMPLATE = '''{{
  "mcpServers": {{
    "incurator": {{
      "command": "wiki",
      "args": ["mcp"],
      "env": {{
        "VAULT_ROOT": "{vault_root}"
      }}
    }}
  }}
}}'''

GEMINI_SNIPPET_TEMPLATE = '''{{
  "mcpServers": {{
    "incurator": {{
      "command": "wiki",
      "args": ["mcp"],
      "env": {{
        "VAULT_ROOT": "{vault_root}"
      }}
    }}
  }}
}}'''


def render_install_snippets(paths: cfg.WikiPaths) -> dict[str, str]:
    """Return ready-to-paste config snippets for supported MCP clients.

    Both Claude Code/Desktop and Gemini CLI use the same MCP-spec
    `mcpServers` shape, so the snippets are identical apart from where
    the user pastes them. Kept as separate template strings so adding
    client-specific fields later (timeout, autoApprove, etc.) doesn't
    couple them.
    """
    vault_root = str(paths.root.resolve())
    return {
        "claude": CLAUDE_SNIPPET_TEMPLATE.format(vault_root=vault_root),
        "gemini": GEMINI_SNIPPET_TEMPLATE.format(vault_root=vault_root),
    }
