"""MCP server — exposes the Curator DAG to workspace agents.

Run via:    wiki mcp           # stdio transport (default)
Install:    wiki mcp install   # prints a config snippet for Claude / Antigravity

The server combines two responsibility layers:

1. **Search delegation** — the `search` tool uses the DB-native hybrid search
   engine in `state.sqlite`: FTS5, chunk vectors, RRF fusion, reranking, and
   durable query traces.

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
from . import constants as consts

import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    from mcp.server.fastmcp import Context, FastMCP
except ImportError as e:  # pragma: no cover - import-time hint
    raise ImportError(
        "The `mcp` package is required. Install with: "
        "uv pip install -e './backend[mcp]'"
    ) from e

from . import config as cfg
from . import page_writer
from . import source_tools


def _zotero_db_candidates(custom_paths: str) -> list[str]:
    """Expand a comma-separated custom_paths string into candidate zotero.sqlite paths.

    Each entry is expanduser'd; a path already ending in `.sqlite` is used as-is,
    otherwise `zotero.sqlite` is appended. Shared by the Zotero MCP tools so the
    resolution rule lives in one place.
    """
    out: list[str] = []
    for raw in str(custom_paths or "").split(","):
        p = raw.strip()
        if not p:
            continue
        base = os.path.expanduser(p)
        out.append(base if base.endswith(".sqlite") else os.path.join(base, consts.FILE_ZOTERO_SQLITE))
    return out


def _zotero_root_candidates(custom_paths: str, config: dict[str, Any] | None = None) -> list[str]:
    """Return Zotero data/attachment roots from configured directories or db files."""
    candidates = [os.path.expanduser("~/Zotero")]
    for raw in str(custom_paths or "").split(","):
        p = raw.strip()
        if not p:
            continue
        expanded = os.path.expanduser(p)
        candidates.append(os.path.dirname(expanded) if expanded.endswith(".sqlite") else expanded)
    if config and "external" in config and "zotero" in config["external"]:
        roots = config["external"]["zotero"].get("roots", [])
        for root in roots:
            candidates.append(os.path.expanduser(root))

    _discover_zotero_base_attachment_path(candidates)

    out: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        norm = os.path.normpath(candidate)
        if norm in seen:
            continue
        seen.add(norm)
        out.append(candidate)
    return out


# ---------------------------------------------------------------------------
# Zotero baseAttachmentPath auto-discovery (ZotMoov / linked attachments)
# ---------------------------------------------------------------------------


def _discover_zotero_base_attachment_path(candidates: list[str]) -> None:
    """Read Zotero prefs.js to discover baseAttachmentPath and ZotMoov dst_dir.

    ZotMoov users store linked PDFs at a custom location that varies per OS:
      - macOS: ~/Library/Mobile Documents/com~apple~CloudDocs/Zotero
      - Linux: ~/Zotero (or another local directory)

    Zotero's prefs.js contains:
      user_pref("extensions.zotero.baseAttachmentPath", "/path/to/...");
      user_pref("extensions.zotmoov.dst_dir", "/path/to/...");

    This function finds the active Zotero profile, extracts these paths,
    and appends them to the candidates list if not already present.
    """
    import re
    import platform

    # Locate Zotero profile directories
    profile_roots: list[str] = []
    if platform.system() == "Darwin":
        profile_roots.append(os.path.expanduser(
            "~/Library/Application Support/Zotero/Profiles"
        ))
    else:  # Linux
        profile_roots.append(os.path.expanduser("~/.zotero/zotero"))

    prefs_files: list[str] = []
    for root in profile_roots:
        if not os.path.isdir(root):
            continue
        for entry in os.listdir(root):
            prefs = os.path.join(root, entry, consts.FILE_ZOTERO_PREFS)
            if os.path.isfile(prefs):
                prefs_files.append(prefs)

    # Parse prefs.js for baseAttachmentPath and zotmoov.dst_dir
    pref_pattern = re.compile(
        rf'user_pref\(\s*"({re.escape(consts.ZOTERO_PREF_ATTACHMENT)}'
        rf'|{re.escape(consts.ZOTERO_PREF_ZOTMOOV)})"\s*,\s*"([^"]+)"\s*\)'
    )
    seen = set(os.path.normpath(c) for c in candidates)
    for prefs_path in prefs_files:
        try:
            with open(prefs_path, "r", encoding="utf-8") as f:
                for line in f:
                    m = pref_pattern.search(line)
                    if m:
                        discovered = m.group(2)
                        norm = os.path.normpath(discovered)
                        if norm not in seen and os.path.isdir(discovered):
                            candidates.append(discovered)
                            seen.add(norm)
        except OSError:
            continue


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
        if (candidate / consts.INTERNAL_DIR / consts.SETTINGS_FILE).exists():
            return cfg.paths_from_config(candidate)
        raise RuntimeError(
            f"VAULT_ROOT is set to '{env_root}' but no vault was found there "
            f"(missing {consts.INTERNAL_DIR}/{consts.SETTINGS_FILE}). "
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
                if (vroot / consts.INTERNAL_DIR / consts.SETTINGS_FILE).exists():
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
    consts.TYPE_L1:    (consts.LAYER_L1,    f"{consts.PREFIX_L1}-"),
    consts.TYPE_L2:       (consts.LAYER_L2,       f"{consts.PREFIX_L2}-"),
    consts.TYPE_L3:    (consts.LAYER_L3,    f"{consts.PREFIX_L3}-"),
    consts.TYPE_L4: (consts.LAYER_L4, f"{consts.PREFIX_L4}-"),
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
        return {"error": f"Unknown ID prefix in '{node_id}' (expected CTX-/ATM-/CON-/SYN-)"}
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
    body = con.get("body", "")
    targets = page_writer.extract_relation_targets(body, prefix=f"{consts.LAYER_L2}/")
    if not targets:
        targets = [
            target
            for target in page_writer.extract_wikilink_targets(body)
            if target.startswith(f"{consts.LAYER_L2}/")
        ]
    for target in targets:
        atom_id = _id_from_link(target)
        if atom_id.startswith(f"{consts.PREFIX_L2}-") and atom_id not in atom_ids:
            atom_ids.append(atom_id)
    return atom_ids


# ---------------------------------------------------------------------------
# Persona update tools (also registered on the MCP server in build_server)
# ---------------------------------------------------------------------------

_ARTIST_PERSONA_KEYS = [
    "domain", "subdomain", "goal", "output_intent",
    "confidence", "disambiguation_keywords", "updated_at",
]

_CURATOR_PERSONA_KEYS = [
    "area", "text", "knowledge_artifacts", "verification_philosophy",
    "output_intent", "confidence", "disambiguation_keywords", "updated_at",
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
    curate_file = ws / consts.FILE_CURATE_YML
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
        for d in [consts.DIR_WIKI, consts.DIR_NOTES, consts.DIR_RESOURCES]:
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
        "topics": ["algorithm", "pipeline", "evaluation", "theory", "application"],
        "min_confidence": ["0.60", "0.70", "0.80", "0.85", "0.90"]
    }
    return fallbacks.get(field_id, ["Option 1", "Option 2", "Option 3", "Option 4", "Option 5"])[:5]
def _build_wizard_questions(workspace_path: str, provided: dict[str, Any] | None = None) -> dict[str, Any]:
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
            "`workspace_path` to retrieve prior knowledge. For a curated evidence pack use "
            "`curator_fetch_context`; for a synthesized answer use `curator_query`.\n\n"
            "SEARCH PROTOCOL:\n"
            "  - Always pass `workspace_path` to `search_curator` / `curator_fetch_context`.\n"
            "  - If response has `needs_initialization: true`, follow its `instructions` to start the interview.\n\n"
            "KNOWLEDGE UPDATE PROTOCOL:\n"
            "  - Propose corrections via `curator_propose_correction` (classified, source-truth-safe).\n"
            "  - Add new insights via `curator_add_knowledge`.\n"
            "  - Call `curator_reindex` only after manually editing vault files outside MCP.\n\n"
            "PDF AGENTIC NAVIGATION:\n"
            "  - If the user asks about a specific chapter or section of a PDF, use `curator_get_pdf_toc` to find the page number, then call `curator_get_pdf_context` with `radius=0` and that `page_num` to fetch it.\n\n"
            "Layer prefixes: CTX- (01_Contexts), ATM- (02_Atoms), CON- (03_Concepts), SYN- (04_Synthesis)."
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
            setattr(mcp, "_incurator_ingest_worker", worker)  # keep a strong reference
    except Exception:
        pass

    def _source_dict(
        paths: cfg.WikiPaths,
        row: dict[str, Any],
        config: dict,
        light: bool = False,
    ) -> dict[str, Any]:
        source_id = int(row["id"])
        pages = db.list_source_pdf_pages(paths.state_db, source_id)
        generated = db.list_source_pages(paths.state_db, source_id)
        
        if light:
            out = dict(row)
            expected_hash = str(row.get("content_hash") or "")
            path = source_tools._row_path(paths, row)
            pending_jobs = db.get_pending_jobs_for_source(paths.state_db, source_id)
            state = source_tools.derive_source_state(row, pending_jobs)
            out.update({
                "state": state,
                "message": "Cached status from database.",
                "current_path": str(path),
                "current_hash": expected_hash,
                "requires_rebind": False,
                "registered": True,
                "source_id": source_id,
                "l1_complete": str(row.get("l1_status") or "") == "done",
                "l2_complete": str(row.get("l2_status") or "") == "done",
                "l3_complete": str(row.get("l3_status") or "") == "done",
                "l4_complete": str(row.get("l4_status") or "") == "done",
                "jobs_pending": pending_jobs,
            })
        else:
            out = source_tools.source_status(paths, row, config)
            
        out["pdf_page_count"] = len(pages)
        out["page_count"] = len(pages)
        out["generated_pages"] = generated
        return out

    def _get_source_row(
        paths: cfg.WikiPaths,
        source_id: int | None = None,
        relpath: str = "",
        source_path: str = "",
        content_hash: str = "",
    ) -> dict[str, Any] | None:
        """Thin wrapper — canonical logic is in db.get_source_row."""
        return db.get_source_row(
            paths.state_db,
            paths.root,
            source_id=source_id,
            relpath=relpath,
            source_path=source_path,
            content_hash=content_hash,
        )

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
            checked: list[str] = []
            for zotero_db in _zotero_db_candidates(custom_paths):
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
            cands = _zotero_db_candidates(custom_paths)
            if not cands:
                return {"ok": False, "error": "custom_paths (zoteroBasePath) is required"}
            metadata = get_zotero_item_metadata(cands[0], item_key, citation_style=citation_style)
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

        # If custom paths provided, use the first candidate db that exists.
        for db_cand in _zotero_db_candidates(custom_paths):
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

        # Auto-discover Zotero's baseAttachmentPath from prefs.js. This is
        # critical for ZotMoov users: macOS may use iCloud while Linux uses
        # local paths.
        candidates = _zotero_root_candidates(custom_paths, config)

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
    def curator_get_provider_config(workspace_path: str = "") -> dict[str, Any]:
        """Get the current LLM provider configuration and available models."""
        paths = _resolve_paths(workspace_path)
        config = cfg.load_config(paths)
        
        models_data = {}
        try:
            models_path = Path(__file__).parent / "data" / "models.json"
            if models_path.exists():
                with open(models_path, "r", encoding="utf-8") as f:
                    models_data = json.load(f)
        except Exception:
            pass
            
        return {"ok": True, "llm": config.get("llm", {}), "models_json": models_data}

    @mcp.tool()
    def curator_set_provider_config(
        primary: str,
        model: str = "",
        host: str = "",
        api_key_env: str = "",
        api_key: str = "",
        base_url: str = "",
        workspace_path: str = ""
    ) -> dict[str, Any]:
        """Set the LLM provider configuration."""
        paths = _resolve_paths(workspace_path)
        config = cfg.load_config(paths)
        llm_cfg = config.get("llm", {})
        llm_cfg["primary"] = cfg.join_provider_model(primary, model)

        if primary == consts.BACKEND_OLLAMA and host:
            llm_cfg.setdefault(consts.BACKEND_OLLAMA, {})["host"] = host
        if primary == consts.BACKEND_DEEPSEEK_API:
            deepseek_cfg = llm_cfg.setdefault(consts.BACKEND_DEEPSEEK_API, {})
            if api_key_env:
                deepseek_cfg["api_key_env"] = api_key_env
            if api_key:
                from . import secret_store

                deepseek_cfg["api_key_secret"] = secret_store.set_secret(
                    secret_store.DEFAULT_DEEPSEEK_SECRET,
                    api_key,
                )
                deepseek_cfg.pop("api_key", None)
            if base_url:
                deepseek_cfg["base_url"] = base_url
            
        config["llm"] = llm_cfg
        
        # Save to global config to match CLI behavior, or vault config if preferred
        # Since MCP server might be used across vaults, modifying vault config is safest:
        cfg.save_config(paths, config)
        return {"ok": True, "llm": config["llm"]}

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
                "job_id":           job.get("id"),
                "source_id":        job.get("source_id"),
                "source_name":      job.get("source_name") or "",
                "job_type":         job.get("job_type") or "",
                "phase":            job.get("phase") or "",
                "progress":         job.get("progress") or 0.0,
                "progress_current": job.get("progress_current") or 0,
                "progress_total":   job.get("progress_total") or 0,
                "started_at":       job.get("started_at") or "",
                "retry_count":      job.get("retry_count") or 0,
            }

        def _done_summary(job: dict) -> dict:
            return {
                "source_name": job.get("source_name") or "",
                "job_type":    job.get("job_type") or "",
                "finished_at": job.get("finished_at") or "",
            }

        return {
            "ok":       True,
            "running":  [_job_summary(j) for j in running],
            "queued":   [_job_summary(j) for j in queued],
            "done":     [_done_summary(j) for j in done_today[:20]],
            "done_today": len(done_today),
            "idle":     len(running) == 0 and len(queued) == 0,
        }

    @mcp.tool()
    def fetch_document_section(
        source_key: str = "",
        toc_id: str = "",
        section_id: str = "",
        page: int = 0,
        page_start: int = 0,
        page_end: int = 0,
        source_id: Optional[int] = None,
        source_path: str = "",
        file_path: str = "",
        path: str = "",
        relpath: str = "",
        workspace_path: str = "",
        content_hash: str = "",
    ) -> dict[str, Any]:
        """Fetch a raw source section for instant L1/ephemeral RAG.

        ``content_hash`` (SHA-256 hex) can be used instead of a path to identify
        the source — useful when the plugin knows the file hash but not its vault
        path (G08-1).  When ``page`` / ``page_start`` / ``page_end`` are given for
        a PDF, per-page text is cached at
        ``.cache/pdf_pages/<content_hash>/<pagenum>.txt`` so repeated cross-page
        lookups skip re-parsing the PDF (fog-of-war page cache).
        """
        paths = _resolve_paths(workspace_path)
        lookup_path = relpath or source_path or file_path or path
        lookup_key = source_key or lookup_path
        row = _get_source_row(
            paths,
            source_id=source_id,
            relpath=relpath,
            source_path=lookup_key,
            content_hash=content_hash,
        )
        if not lookup_key and row is None:
            return {"ok": False, "error": "Source not found: missing source_key, source_id, or path"}
        source_path_obj = Path(lookup_key).expanduser() if lookup_key else Path()
        if row is not None:
            source_path_obj = source_tools._row_path(paths, row)
        elif lookup_key and not source_path_obj.is_absolute():
            source_path_obj = paths.root / lookup_key
        wanted = section_id or toc_id
        if row is not None and wanted:
            from . import plugin_api

            durable = plugin_api.durable_l1_section(paths, row, wanted)
            if durable is not None:
                return durable
        if not source_path_obj.exists():
            return {"ok": False, "error": f"Source not found: {lookup_key}"}

        # Fast path for PDF page requests: use per-page cache + bounded parse (G12-2).
        # Keyed on content_hash so the cache is stable across path moves.
        hash_for_cache = content_hash or (str(row.get("content_hash") or "") if row else "")
        # Reject non-hex values to prevent path traversal via a crafted hash.
        if hash_for_cache and not all(c in "0123456789abcdefABCDEF" for c in hash_for_cache):
            hash_for_cache = ""
        req_page = page or page_start or 0
        req_end = page_end or req_page or 0
        if (
            hash_for_cache
            and source_path_obj.suffix.lower() == ".pdf"
            and req_page > 0
            and not (section_id or toc_id)
        ):
            pages_needed: set[int] = (
                set(range(req_page, req_end + 1)) if req_end >= req_page else {req_page}
            )
            cache_dir = paths.root / ".cache" / "pdf_pages" / hash_for_cache
            cached_pages: dict[int, str] = {}
            missing_pages: set[int] = set()
            try:
                for pn in pages_needed:
                    cache_file = cache_dir / f"{pn}.txt"
                    if cache_file.exists():
                        cached_pages[pn] = cache_file.read_text(encoding="utf-8")
                    else:
                        missing_pages.add(pn)
            except OSError:
                missing_pages = pages_needed
                cached_pages = {}
            # Snapshot pages that were already in cache before any fetch.
            hit_pages: set[int] = set(cached_pages.keys())
            if missing_pages:
                from .parsers.pdf import parse_page_window
                fetched_pages = parse_page_window(source_path_obj, missing_pages)
                try:
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    for pn, txt in fetched_pages.items():
                        (cache_dir / f"{pn}.txt").write_text(txt, encoding="utf-8")
                except OSError:
                    pass
                for pn, txt in fetched_pages.items():
                    cached_pages[pn] = txt
            pages_text = [cached_pages.get(pn, "") for pn in sorted(pages_needed)]
            combined = "\n\n".join(t for t in pages_text if t)
            return {
                "ok": True,
                "source_id": int(row["id"]) if row else None,
                "source_key": lookup_key,
                "relpath": row.get("relpath") if row else None,
                "toc_id": None,
                "page": req_page,
                "page_start": req_page,
                "page_end": req_end or req_page,
                "page_count": None,
                "title": source_path_obj.stem,
                "file_type": "pdf",
                "metadata": {"pages": sorted(pages_needed)},
                "text": combined,
                "char_count": len(combined),
                "context_source": (
                    "pdf_page_cache"
                    if not missing_pages
                    else "pdf_page_cache_partial"
                ),
                "cache_hits": sorted(hit_pages),
                "cache_misses": sorted(missing_pages),
            }

        try:
            from .ingest_raw import _extract_structural_sections, _resolve_reference_source
            resolved_path = _resolve_reference_source(paths, source_path_obj)
            parsed = source_tools.parse_source(resolved_path)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        text = parsed.text
        page_count = 1
        metadata: dict[str, Any] = dict(parsed.metadata or {})
        legacy_page_lookup = not source_key and not wanted and bool(source_id is not None or lookup_path)
        requested_page = int(page or page_start or (1 if legacy_page_lookup else 0))
        if wanted:
            sections = _extract_structural_sections(parsed)
            for section in sections:
                sid = str(section.get("id") or "")
                title = str(section.get("title") or "")
                if sid == wanted or title == wanted:
                    text = str(section.get("text") or "").strip()
                    metadata = {
                        "section_id": sid,
                        "section_title": title,
                        "page": int(section.get("page") or 1),
                    }
                    requested_page = int(section.get("page") or requested_page or 0)
                    break
        if parsed.file_type == "pdf":
            pages = parsed.metadata.get("pdf_pages") or []
            page_count = len(pages)
            if (requested_page or page_end) and not wanted:
                start_page = requested_page or 1
                end_page = int(page_end or start_page)
                if start_page < 1 or (page_count and start_page > page_count):
                    return {"ok": False, "error": f"Page out of range: {start_page}", "page_count": page_count}
                selected: list[str] = []
                selected_meta: dict[str, Any] = {}
                for item in pages:
                    item_page = int(item.get("page") or item.get("page_number") or 0)
                    if start_page <= item_page <= end_page:
                        page_meta = dict(item)
                        selected.append(str(page_meta.pop("text", "") or ""))
                        if item_page == start_page:
                            selected_meta = page_meta
                text = "\n\n".join(part for part in selected if part)
                metadata = selected_meta
        elif wanted and not metadata.get("section_id"):
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
            "source_key": lookup_key,
            "relpath": row.get("relpath") if row else None,
            "toc_id": wanted,
            "page": requested_page or None,
            "page_start": int(page_start or requested_page or 0) or None,
            "page_end": int(page_end or requested_page or 0) or None,
            "page_count": page_count,
            "title": parsed.title,
            "file_type": parsed.file_type,
            "metadata": metadata,
            "text": text,
            "char_count": len(text),
            "context_source": "ephemeral_parse",
            "degraded_reason": (
                "durable_exact_text_unavailable"
                if row is not None and wanted and str(row.get("l1_status") or "") == "done"
                else None
            ),
        }

    @mcp.tool()
    def check_source_status(
        file_hash: str = "",
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
        config = cfg.load_config(paths)
        stats = db.get_stats(paths.state_db)

        if file_hash:
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
                    "l4_complete": False,
                    "jobs_pending": [],
                }
            source = _source_dict(paths, dict(row), config)
            return {
                "registered": True,
                "source_id": int(row["id"]),
                "relpath": row["relpath"],
                "source_path": row["relpath"],
                "l1_complete": source.get("l1_complete", False),
                "l2_complete": source.get("l2_complete", False),
                "l3_complete": source.get("l3_complete", False),
                "l4_complete": source.get("l4_complete", False),
                "jobs_pending": source.get("jobs_pending", []),
                "source": source,
            }

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
            return {"stats": stats, "source": _source_dict(paths, row, config)}

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
            "sources": [_source_dict(paths, dict(row), config, light=True) for row in rows],
            "count": len(rows),
        }

    @mcp.tool()
    def curator_list_external_resources(workspace_path: str = "") -> dict[str, Any]:
        """Return machine-local external roots used for reference sources.

        These roots come from config, typically the machine-local
        .cache/config/config.yml file at the repository root. They are not
        written to the vault by this tool.
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
    def curator_register_source(
        source_id: Optional[int] = None,
        relpath: str = "",
        source_path: str = "",
        file_path: str = "",
        path: str = "",
        force: bool = False,
        build: bool = True,
        workspace_path: str = "",
    ) -> dict[str, Any]:
        """Register a source and generate its L1 Context instantly (no LLM).

        This is the fast ingest boundary: structural L1 only, **no LLM client
        is started**, so it works even when no model backend is available.
        If `build=True`, L2/L3 are enqueued to the background worker
        (non-blocking) and surface later via curator_source_status.

        The plugin calls this on PDF-open to make a document searchable in
        seconds without waiting for atom/concept extraction.
        """
        paths = _resolve_paths(workspace_path)
        lookup_path = relpath or source_path or file_path or path
        row = _get_source_row(paths, source_id=source_id, relpath=relpath, source_path=lookup_path)
        if row is None:
            return {"state": "untracked", "error": "Source not found", "source_path": lookup_path}

        source_id_int = int(row["id"])

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
            context_id = ingest_raw.generate_l1_structural_context(
                paths,
                source_id=source_id_int,
                relpath=str(row["relpath"]),
                content_hash=str(row["content_hash"]),
                existing_context_id=None if force else row.get("context_id"),
            )
            if not context_id:
                return {"ok": False, "source_id": source_id_int, "error": "L1 generation failed"}

        # Make the new L1 immediately searchable (BM25; skip slow embeddings).
        warnings: list[str] = []
        try:
            search.update_index(paths, embed=False)
        except (OSError, sqlite3.Error, search.SearchBackendError) as exc:
            warnings.append(f"Search index refresh skipped: {type(exc).__name__}: {exc}")

        job_ids: list[int] = []
        if build:
            from .ingest_worker import enqueue_l2_l3_for_sources
            job_ids = enqueue_l2_l3_for_sources(paths, [source_id_int])

        return {
            "ok": True,
            "source_id": source_id_int,
            "context_id": context_id,
            "l2_l3_queued": bool(job_ids),
            "job_ids": job_ids,
            "warnings": warnings,
        }

    @mcp.tool()
    def curator_build_source(
        source_id: Optional[int] = None,
        relpath: str = "",
        source_path: str = "",
        file_path: str = "",
        path: str = "",
        wait: bool = False,
        workspace_path: str = "",
    ) -> dict[str, Any]:
        """Build L2 Atoms + L3 Concepts for a source (the deep, LLM-heavy pass).

        Requires L1 to exist (run curator_register_source first). With
        `wait=False` (default) the work is enqueued to the background worker
        and this returns immediately. With `wait=True` it runs synchronously
        and may take minutes — the LLM client is built only in that case.
        """
        paths = _resolve_paths(workspace_path)
        lookup_path = relpath or source_path or file_path or path
        row = _get_source_row(paths, source_id=source_id, relpath=relpath, source_path=lookup_path)
        if row is None:
            return {"state": "untracked", "error": "Source not found", "source_path": lookup_path}

        source_id_int = int(row["id"])
        context_id = row.get("context_id")
        if not context_id or not (paths.contexts / f"{context_id}.md").exists():
            return {
                "ok": False,
                "source_id": source_id_int,
                "error": "L1 Context missing — call curator_register_source first.",
            }

        db.set_source_layer_status(paths.state_db, source_id_int, "l2", "pending")
        db.set_source_layer_status(paths.state_db, source_id_int, "l3", "pending")

        if not wait:
            from .ingest_worker import enqueue_l2_l3_for_sources
            job_ids = enqueue_l2_l3_for_sources(paths, [source_id_int])
            return {
                "ok": True,
                "source_id": source_id_int,
                "queued": True,
                "job_ids": job_ids,
            }

        # Synchronous build — the only path that needs an LLM client.
        config = cfg.load_config(paths)
        callbacks = _McpIngestCallbacks()
        try:
            client = llm.build_client(config)
        except Exception as exc:
            return {"error": f"Could not start LLM client: {exc}"}
        try:
            results = ingest_llm.run_l1_to_l3(
                paths,
                client,
                lambda: callbacks,
                mode="batch",
                auto_discover=False,
            )
            ingest_result = next(
                (result for result in results if result.source_id == source_id_int),
                None,
            )
            l3_pages_written = sum(
                1
                for event in callbacks.events
                if event.get("kind") == "page"
                and str(event.get("path") or "").startswith(f"{consts.LAYER_L3}/")
            )
            if ingest_result is not None and ingest_result.ok:
                try:
                    search.update_index(paths, embed=True)
                except Exception:
                    pass
            return {
                "ok": True if ingest_result is None else ingest_result.ok,
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
        """DEPRECATED: use curator_register_source (L1) + curator_build_source (L2/L3).

        Kept as a thin compatibility alias. Registers + instant L1, then builds
        L2/L3 synchronously when run_l2_l3=True (legacy blocking behaviour).
        """
        reg = curator_register_source(
            source_id=source_id,
            relpath=relpath,
            source_path=source_path,
            file_path=file_path,
            path=path,
            force=force,
            build=False,
            workspace_path=workspace_path,
        )
        if not reg.get("ok") or not run_l2_l3:
            return reg
        return curator_build_source(
            source_id=reg.get("source_id"),
            wait=True,
            workspace_path=workspace_path,
        )

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
    def curator_get_pdf_toc(file_path: str) -> list[dict]:
        """Extract the Table of Contents (Outline) from a PDF.
        
        Useful when you need to know which page a specific chapter starts on.
        Returns a list of dictionaries with 'level', 'title', and 'page' (1-based).
        """
        from .parsers import pdf
        try:
            return pdf._extract_pdf_toc(Path(file_path))
        except Exception as e:
            return [{"error": str(e)}]

    @mcp.tool()
    def curator_get_pdf_context(
        file_path: str,
        query: str = "",
        page_num: int = 0,
        radius: int = 2,
        max_pages: int = 8,
        workspace_path: str = "",
    ) -> dict[str, Any]:
        """Extract relevant PDF text for use as LLM context.

        Unlike curator_ingest_source (which creates L1-L4 DAG nodes), this tool
        performs lightweight on-demand text extraction for immediate chat context.
        Works for both tracked and untracked PDFs — no ingestion required.

        Args:
            file_path: Absolute filesystem path to the PDF.
            query: Optional query string to score pages by relevance.
            page_num: Current page number (1-based). 0 = no current page.
            radius: Pages around page_num to include in the window (default 2).
            max_pages: Maximum pages to return (default 8).
            workspace_path: Vault root override.

        Returns dict with:
            ok, source_tracked, source_id, total_pages, title,
            pages ([{page_num, text, score}]), outline ([{title, page_num, level}]),
            is_empty_pdf
        """
        from . import plugin_api

        paths = _resolve_paths(workspace_path)
        return plugin_api.pdf_context(
            paths,
            file_path=file_path,
            query_text=query,
            page_num=page_num,
            radius=radius,
            max_pages=max_pages,
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
        config = cfg.load_config(paths)

        if source_id is not None:
            row = _get_source_row(paths, source_id=source_id)
            if row is None:
                return {"error": f"Source not found: {source_id}"}
            return {
                "source": _source_dict(paths, row, config),
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
        if not source_link and page.get("id", "").startswith(f"{consts.PREFIX_L1}-"):
            source_link = str(fm.get("source_path") or "")
            context_link = f"{consts.LAYER_L1}/{page['id']}"

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

        source = _source_dict(paths, dict(row), config) if row else None
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
    # search — DB-native retrieval, with optional layer filter
    # ------------------------------------------------------------------

    @mcp.tool()
    def search_curator(
        query: str,
        mode: str = "hybrid",
        limit: int = 8,
        min_score: float = 0.6,
        workspace_path: str = "",
    ) -> dict[str, Any]:
        """Search the Curator DAG over authoritative DB-native search rows.

        Args:
            query: Natural-language query.
            mode: 'hybrid' (BM25 + vector + LLM rerank, best quality), 'lex'
                  (BM25 only, fastest), 'vec' (vector only).
            limit: Max number of hits before min_score filtering.
            min_score: Drop hits below this score (0.6 = default threshold).
            workspace_path: The workspace to scope the search to. Use if WORKSPACE_PATH env var is not set.

        Returns a dict with `hits` (each has `path`, `title`, `score`, `snippet`,
        `body`), `count`. For an answer (not raw hits) use `curator_query`; for the
        curated evidence pack use `curator_fetch_context`.
        """
        ws_path_str = workspace_path or os.environ.get("WORKSPACE_PATH") or ""
        paths = _resolve_paths(ws_path_str)

        # Load curate.yml if workspace_path or WORKSPACE_PATH is set
        from . import curate_yml as _cym
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
            _curate_file = ws_path / consts.FILE_CURATE_YML
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

        base_query = query
        if curate_spec is not None:
            # Apply confidence floor + boost query with domain/topic terms (KRS lens).
            min_score = max(min_score, curate_spec.min_confidence)
            query = curate_spec.boost_query(query)

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
            if len(results) == 0 and query != base_query:
                results = search.query(
                    paths,
                    base_query,
                    mode=mode,
                    limit=limit,
                    min_score=min_score,
                    hydrate=True,
                    rerank=True,
                )
        except search.SearchBackendError as e:
            return {"error": f"search error: {e}", "hits": []}

        hits = [
            {
                "path": hit.full_path,
                "title": hit.title,
                "score": round(hit.score, 4),
                "snippet": hit.snippet,
                "body": hit.full_content,
                "docid": hit.docid,
            }
            for hit in results.hits
        ]

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
        """Answer a question using the Curator knowledge graph and dynamic curation lens.

        This is the v0.3.1 primary query entry point for sidebar-style answers.
        It retrieves relevant evidence, synthesizes an answer with the LLM, and
        returns provenance trace data for the "Sources & Trace" plugin panel.

        Use `search_curator` for raw DAG hit retrieval without LLM synthesis.

        Args:
            question: Natural-language question to answer.
            workspace_path: Active workspace path to scope retrieval. Falls back
                to the WORKSPACE_PATH env var when not provided.
            force_new: Ignored in v0.3.1; queries are sessionless.

        Returns:
            ok: Whether synthesis succeeded.
            answer: Synthesized markdown answer.
            question: Original question echoed back.
            trace: Provenance — matched concept IDs, source paths, latency.
            error: Error message when ok=false.
        """
        import time as _time

        start = _time.monotonic()
        ws_path_str = workspace_path or os.environ.get("WORKSPACE_PATH", "")
        paths = _resolve_paths(ws_path_str)

        # Build LLM client and run query pipeline
        from . import llm as _llm
        from .retrieval import QueryOrchestrator, QueryRequest

        try:
            config = cfg.load_config(paths)
        except Exception as e:
            return {"ok": False, "question": question, "error": f"Config error: {e}"}

        _con_dir = paths.concepts if hasattr(paths, "concepts") else paths.collections / consts.LAYER_L3
        l3_complete = any(_con_dir.glob(f"{consts.PREFIX_L3}-*.md")) if _con_dir.exists() else False
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

        try:
            with _llm.build_client(config) as client:
                result = QueryOrchestrator(paths, client).run(
                    QueryRequest(
                        question=question,
                        workspace_path=ws_path_str,
                        mode="auto",
                    )
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

        trace = db.get_query_trace(paths.state_db, result.trace_id)
        context_trace = {}
        if trace is not None:
            context_trace = (trace.get("retrieval_trace") or {}).get("context_service", {})
        context_pack_id = context_trace.get("pack_id", None) or None
        context_snapshot = context_trace.get("snapshot", None) if context_pack_id is not None else None
        context_budget = context_trace.get("budget", None) if context_pack_id is not None else None
        source_paths: list[str] = []
        if result.source_span_ids:
            for span in db.get_source_spans_by_ids(paths.state_db, result.source_span_ids):
                relpath = span.get("relpath", "")
                if relpath and relpath not in source_paths:
                    source_paths.append(relpath)

        return {
            "ok": True,
            "answer": result.answer,
            "question": question,
            "trace": {
                "matched_concepts": [],
                "source_ids": [],
                "source_paths": source_paths,
                "synthesis_node_ids": result.synthesis_node_ids,
                "community_report_ids": result.community_report_ids,
                "memory_path_ids": result.memory_path_ids,
                "insight_candidate_ids": result.insight_candidate_ids,
                "prompt_trace_ids": result.prompt_trace_ids,
                "source_span_ids": result.source_span_ids,
                "trace_id": result.trace_id,
                "route": result.route,
                "pack_id": context_pack_id,
                "snapshot": context_snapshot,
                "budget": context_budget,
                "latency_ms": latency_ms,
                "l3_complete": l3_complete,
            },
        }

    # ------------------------------------------------------------------
    # promote_answer — promote a sessionless Q&A answer to 02_Wiki/
    # ------------------------------------------------------------------

    @mcp.tool()
    def promote_answer(
        question: str,
        answer: str,
        workspace_path: str = "",
        source_span_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Promote a sessionless Q&A answer into 02_Wiki/ as a human-verified artifact.

        v0.3.1: queries are sessionless (no Exhibition file), so promotion takes the
        question + answer text directly and writes only `02_Wiki/<category>/<slug>.md`
        (source truth is never touched). Must only be called after explicit user
        approval; the plugin must not call this automatically.

        Args:
            question: The question that produced the answer.
            answer: The answer text to promote.
            workspace_path: Optional workspace path to resolve the vault.
            source_span_ids: Optional `source_span_ids` from the answer's query
                trace. When provided, a deterministic `## Sources` section of
                `[[04_Resources/…]]` links to the original source documents is
                appended, so those sources appear in Obsidian's Graph view and
                Backlinks pane via the visible `02_Wiki/` note.

        Returns:
            ok: Whether promotion succeeded.
            promoted_to: Vault-relative path of the promoted wiki page.
            error: Error message when ok=false.
        """
        paths = _resolve_paths(workspace_path)
        if not (question.strip() and answer.strip()):
            return {"ok": False, "error": "question and answer are required"}

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
            slug = _re.sub(r"\s+", "-", slug)[:60].strip("-") or "note"

        source_links = _query.resolve_source_links(paths, source_span_ids or [])
        try:
            wiki_path = _query.save_wiki_page(
                paths, question, answer, category, slug, source_links=source_links
            )
        except Exception as e:
            return {"ok": False, "error": f"Failed to write wiki page: {e}"}

        return {"ok": True, "promoted_to": wiki_path}

    # ------------------------------------------------------------------
    # curator_check_workspace — validate workspace configuration health
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_check_workspace(
        workspace_path: str = "",
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Check workspace configuration health and return setup guidance.

        Call this at the start of each session when WORKSPACE_PATH is set.
        Validates that curate.yml exists and is valid, and auto-installs agent rules for the
        connecting client (Claude Code, Antigravity, etc.) if not yet present.

        Args:
            workspace_path: Absolute path to workspace. Defaults to WORKSPACE_PATH env var.

        Returns a dict with `ok` (bool), `workspace`, `project`,
        `agent_rules_installed` (if newly installed), and
        `issues` (list of actionable error messages).
        """
        from . import curate_yml as _cym

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

        curate_file = ws_path / consts.FILE_CURATE_YML
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

        # Auto-install agent rules for the connecting client
        agent_rules_installed = None
        detected_agent = consts.BACKEND_CODEX_CLI
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
        ctx: Context | None = None,
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
            final_includes = [f"{consts.DIR_WIKI}/**", f"{consts.DIR_NOTES}/**", f"{consts.DIR_RESOURCES}/**"]

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
            '  "output_intent": "researcher | engineer | learner",\n'
            '  "disambiguation_keywords": ["3-8 workspace-specific terms"],\n'
            '  "confidence": {"high_threshold": 0.85, "low_threshold": 0.55}\n'
            "}\n\n"
            "output_intent meanings:\n"
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
            curate_file = ws_path / consts.FILE_CURATE_YML
            try:
                raw_yml = _yaml.safe_load(curate_file.read_text(encoding="utf-8")) or {}
                persona["updated_at"] = datetime.now(timezone.utc).isoformat()
                raw_yml["persona"] = persona
                curate_file.write_text(
                    _yaml.safe_dump(raw_yml, sort_keys=False, default_flow_style=False),
                    encoding="utf-8",
                )
                if consts.FILE_CURATE_YML not in updated:
                    updated.append(consts.FILE_CURATE_YML)
            except Exception as e:
                persona_error = f"Persona generated but could not be saved: {e}"

        # ── 5. Trigger an initial DAG build (L1→L3 + shared L4 Synthesis) ──────
        # v0.3.1: there is no per-workspace Exhibition to stage; curation is a
        # dynamic query-time lens. `wiki build` refines the shared DAG so queries
        # have evidence to ground on.
        curation_error: str | None = None
        try:
            build_result = subprocess.run(
                [sys.executable, "-m", "curator.cli", "build", "--no-sync"],
                cwd=str(paths.root),
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
                env={**os.environ, "VAULT_ROOT": str(paths.root)},
            )
            if build_result.returncode != 0:
                curation_error = (
                    build_result.stderr.strip()
                    or build_result.stdout.strip()
                    or f"Exit code {build_result.returncode}"
                )
        except Exception as e:
            curation_error = str(e)

        # ── 6. Return result ────────────────────────────────────────────────
        next_steps = [
            f"search_curator('<query>', workspace_path='{ws_path}') — Search the knowledge base",
            f"curator_fetch_context('<query>', workspace_path='{ws_path}') — Curated evidence pack",
            f"curator_update_artist_persona('{ws_path}', '<description>') — Refine workspace persona",
        ]
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
        """Fetch a single DAG node (Context/Atom/Concept/Synthesis) by ID.

        Args:
            node_id: e.g. 'SYN-abcdef01', 'ATM-9f8e7d6c'. Prefix determines
                     the layer.
            workspace_path: Optional workspace path to help resolve the vault.

        Returns the node's frontmatter + body, or `{'error': ...}` if missing.
        """
        paths = _resolve_paths(workspace_path)
        return _read_node(paths, node_id)

    # ------------------------------------------------------------------
    # curator_traverse_evidence — walk SYN -> CON/REP -> ATM/source spans
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_traverse_evidence(cur_id: str, workspace_path: str = "") -> dict[str, Any]:
        """Walk a Synthesis node's evidence chain down to its supporting evidence.

        Returns the full SYN page plus referenced Concepts, Reports, Atoms, and
        source span ids where available. Use this to verify a Synthesis claim before citing it (especially when
        confidence_score < 0.90).

        Args:
            cur_id: The ID of the Synthesis node (SYN-) to traverse.
            workspace_path: Optional workspace path to help resolve the vault.
        """
        paths = _resolve_paths(workspace_path)
        cur = _read_node(paths, cur_id)
        if "error" in cur:
            return cur
        if cur["layer"] != consts.TYPE_L4:
            return {"error": f"{cur_id} is a {cur['layer']}, not a synthesis node."}

        concepts: list[dict[str, Any]] = []
        atoms: list[dict[str, Any]] = []
        broken_atom_refs: list[dict[str, str]] = []
        seen_atoms: set[str] = set()

        for raw_ref in cur["frontmatter"].get("concept_ids", []) or []:
            con_id = _id_from_link(str(raw_ref))
            con = _read_node(paths, con_id)
            if "error" in con:
                concepts.append({"id": con_id, "error": con["error"]})
                continue
            concepts.append(con)

            for atm_id in _concept_atom_ids(con):
                if atm_id in seen_atoms:
                    continue
                seen_atoms.add(atm_id)
                atom = _read_node(paths, atm_id)
                if "error" in atom:
                    broken_atom_refs.append({"concept_id": con_id, "atom_id": atm_id, "error": atom["error"]})
                    continue
                atoms.append(atom)

        return {
            "synthesis": cur,
            "confidence_score": cur["frontmatter"].get("confidence_score"),
            "source_span_ids": cur["frontmatter"].get("source_span_ids", []) or [],
            "community_report_ids": cur["frontmatter"].get("community_report_ids", []) or [],
            "concepts": concepts,
            "atoms": atoms,
            "broken_atom_refs": broken_atom_refs,
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
            for md in sorted(atoms_dir.glob(f"{consts.PREFIX_L2}-*.md")):
                parsed = page_writer.read_page(md)
                if parsed is None:
                    continue
                fm = parsed.frontmatter
                if fm.get("is_flagged_for_agent") or fm.get("contradicts"):
                    entry = {
                        "id": fm.get("id") or md.stem,
                        "path": f"{consts.LAYER_L2}/{md.name}",
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

        if info[0] == consts.TYPE_L2:
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
        if info[0] == consts.TYPE_L4:
            chain = curator_traverse_evidence(node_id)
            for atm in chain.get("atoms", []):
                if "id" in atm:
                    atom_ids.add(atm["id"])
        elif info[0] == consts.TYPE_L3:
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
                path_a=f"{consts.LAYER_L2}/{a_id}.md",
                content_a=page_a.to_markdown(),
                path_b=f"{consts.LAYER_L2}/{b_id}.md",
                content_b=page_b.to_markdown(),
                conflict_reasoning="",
            )
            raw = _client.chat(messages, json_mode=True, temperature=0.3)
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

        Layers: context (CTX-), atom (ATM-), concept (CON-), synthesis (SYN-).
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
    # curator_status — vault info + search readiness
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_get_version() -> str:
        """Return the current version of the Incurator backend."""
        try:
            import importlib.metadata
            return importlib.metadata.version("incurator")
        except Exception:
            from curator import __version__
            return __version__

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
        """Return vault root, DB-native search readiness, and total page counts.

        Args:
            workspace_path: Optional workspace path to help resolve the vault.
        """
        import shutil as _shutil
        import sys as _sys
        paths = _resolve_paths(workspace_path)
        search_version = search.get_version()

        # Locate wiki binary: which → alongside Python → argv[0]
        wiki_bin = _shutil.which("wiki")
        if not wiki_bin:
            _py_dir = Path(_sys.executable).parent
            for _name in ("wiki", "wiki.exe"):
                _p = _py_dir / _name
                if _p.exists():
                    wiki_bin = str(_p)
                    break
        if not wiki_bin and _sys.argv and _sys.argv[0]:
            _a = Path(_sys.argv[0])
            if _a.name.startswith("wiki"):
                wiki_bin = str(_a)

        layer_counts = {
            "contexts": 0,
            "atoms": 0,
            "concepts": 0,
            "synthesis": 0,
        }

        for layer_key, (subdir, _prefix) in _LAYERS.items():
            d = paths.collections / subdir
            if d.exists():
                try:
                    count = sum(
                        1 for e in os.scandir(d)
                        if e.is_file() and e.name.endswith(".md") and not e.name.startswith(".")
                    )
                except Exception:
                    count = 0
                if consts.LAYER_L1 in subdir:
                    layer_counts["contexts"] = count
                elif consts.LAYER_L2 in subdir:
                    layer_counts["atoms"] = count
                elif consts.LAYER_L3 in subdir:
                    layer_counts["concepts"] = count
                elif consts.LAYER_L4 in subdir:
                    layer_counts["synthesis"] = count

        # Discover Zotero roots (attachment paths)
        zotero_roots: list[str] = []
        try:
            _discover_zotero_base_attachment_path(zotero_roots)
        except Exception:
            pass

        return {
            "vault_root":   str(paths.root),
            "collections":  str(paths.collections),
            "total_pages":  sum(layer_counts.values()),
            "layer_counts": layer_counts,
            "wiki_binary":  wiki_bin,
            "search_engine": "native",
            "search_ready": True,
            "search_version": search_version,
            "zotero_roots": zotero_roots,
        }

    @mcp.tool()
    def curator_add_all(workspace_path: str = "") -> dict[str, Any]:
        """Run a global discovery of raw sources, generating L1 Contexts."""
        from . import ingest_llm, ingest_raw
        paths = _resolve_paths(workspace_path)
        try:
            discovered, removed = ingest_llm._auto_discover_pending(paths)
            with db.connect(paths.state_db) as conn:
                rows = conn.execute(
                    "SELECT id, relpath, content_hash, context_id FROM sources "
                    "WHERE status IN ('pending', 'force_pending', 'curated') "
                    "ORDER BY id ASC"
                ).fetchall()

            summarized = 0
            for row in rows:
                context_id = row["context_id"]
                if context_id and (paths.contexts / f"{context_id}.md").exists():
                    continue
                db.set_source_layer_status(paths.state_db, row["id"], "l1", "running")
                created_context_id = ingest_raw.generate_l1_structural_context(
                    paths,
                    source_id=row["id"],
                    relpath=row["relpath"],
                    content_hash=row["content_hash"],
                    existing_context_id=context_id,
                )
                if created_context_id:
                    summarized += 1
                else:
                    db.set_source_layer_status(
                        paths.state_db,
                        row["id"],
                        "l1",
                        "error",
                        error="summary_failed",
                    )

            return {
                "ok": True,
                "discovered": discovered,
                "removed": removed,
                "summarized": summarized,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @mcp.tool()
    def curator_build_all(workspace_path: str = "") -> dict[str, Any]:
        """Run a global extraction of L2 Atoms and L3 Concepts from registered L1 Contexts."""
        from . import ingest_llm, config as cfg
        from .llm import build_client
        paths = _resolve_paths(workspace_path)
        config_dict = cfg.load_config(paths)
        try:
            with build_client(config_dict) as client:
                results = ingest_llm.run_l1_to_l3(
                    paths, client, ingest_llm.IngestCallbacks, mode="batch"
                )
            return {
                "ok": True,
                "sources": len(results),
                "atoms_created": sum(r.fragments_created for r in results),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @mcp.tool()
    def curator_sync(workspace_path: str = "") -> dict[str, Any]:
        """Run a bidirectional synchronization to repair the DAG integrity."""
        from . import sync as sync_mod
        from . import config as cfg
        from .llm import build_client

        paths = _resolve_paths(workspace_path)
        config_dict = cfg.load_config(paths)
        try:
            with build_client(config_dict) as client:
                res = sync_mod.run_incremental_sync(paths, client, config_dict)
            return {
                "ok": True,
                "repaired": res.get("repaired", 0),
                "messages": res.get("messages", []),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @mcp.tool()
    def curator_lint(workspace_path: str = "") -> dict[str, Any]:
        """Run vault linting to find broken links and contradictions."""
        from . import lint as lint_mod
        
        paths = _resolve_paths(workspace_path)
        try:
            report = lint_mod.run_lint(paths, progress_callback=None)
            return {
                "ok": True,
                "health_score": report.health_score,
                "errors": len(report.errors),
                "warnings": len(report.warnings),
                "infos": len(report.infos),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------
    # curator_update_node — overwrite a node and propagate
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_update_node(
        node_id: str,
        new_content: str,
        workspace_path: str = "",
        propagate_sources: bool = True,
    ) -> dict[str, Any]:
        """Direct generated-node overwrite is disabled in v0.3.1.

        Use `curator_propose_correction` for reviewed corrections or
        `curator_promote_insight` / `promote_answer` for durable human-approved
        insights. This tool is retained only to return a non-mutating error to
        older clients.
        """
        return {
            "ok": False,
            "updated": False,
            "error": (
                "Direct Curator node overwrites were removed in v0.3.1. "
                "Use curator_propose_correction for corrections or promote_answer/"
                "curator_promote_insight for reviewed durable knowledge."
            ),
        }

    # ------------------------------------------------------------------
    # curator_reindex — rebuild the DB-native search index
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_reindex(workspace_path: str = "") -> dict[str, Any]:
        """Rebuild DB-native search rows, FTS tables, chunks, and embeddings.

        Call this after manually editing wiki pages or after a bulk import so
        that `search_curator` picks up the new content.

        Args:
            workspace_path: Optional workspace path to help resolve the vault.

        Returns `{'ok': True}` or `{'error': ...}`.
        """
        paths = _resolve_paths(workspace_path)
        try:
            result = search.update_index(paths, embed=True)
            return {
                "ok": True,
                "updated": result.updated,
                "embedded": result.embedded,
                "degraded": result.degraded,
                "warning": result.warning,
            }
        except search.SearchBackendError as exc:
            return {"ok": False, "error": str(exc)}


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
    # v0.3.1 curation-native tools (SYSTEM_BEHAVIOR §20)
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_validate_curate_spec(workspace_path: str) -> dict[str, Any]:
        """Validate a workspace curate.yml and return its compiled policy summary."""
        from . import curate_yml
        try:
            spec = curate_yml.load_curate_spec(Path(workspace_path))
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if spec is None:
            return {"ok": False, "error": "no curate.yml in workspace"}
        errors = curate_yml.validate_curate_spec(spec)
        policy = curate_yml.compile_curate_policy(spec, Path(workspace_path))
        return {
            "ok": not errors,
            "errors": errors,
            "spec_hash": curate_yml.curate_spec_hash(Path(workspace_path)),
            "policy": {
                "workspace_id": policy.workspace_id,
                "default_route": policy.default_route,
                "allowed_routes": sorted(policy.allowed_routes),
                "prompt_profile": policy.prompt_profile,
                "require_source_spans": policy.require_source_spans,
                "backprop_enabled": policy.backprop_enabled,
            },
        }

    @mcp.tool()
    def curator_plan_workspace(workspace_path: str) -> dict[str, Any]:
        """Compile the workspace curate.yml into a recorded curation plan."""
        from . import curate_yml
        paths = _resolve_paths(workspace_path)
        try:
            spec = curate_yml.load_curate_spec(Path(workspace_path))
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if spec is None:
            return {"ok": False, "error": "no curate.yml in workspace"}
        policy = curate_yml.compile_curate_policy(spec, Path(workspace_path))
        plan_id = db.record_curation_plan(
            paths.state_db,
            workspace_id=policy.workspace_id,
            workspace_path=workspace_path,
            project=policy.project,
            curate_spec_hash=curate_yml.curate_spec_hash(Path(workspace_path)),
            route=policy.default_route,
            source_policy={"include": list(policy.source_include), "exclude": list(policy.source_exclude)},
            retrieval_policy={"allowed_routes": sorted(policy.allowed_routes),
                              "exploration_enabled": policy.exploration_enabled},
            prompt_profile=policy.prompt_profile,
        )
        return {"ok": True, "plan_id": plan_id, "workspace_id": policy.workspace_id,
                "route": policy.default_route}

    @mcp.tool()
    def curator_fetch_context(query: str, workspace_path: str = "") -> dict[str, Any]:
        """Fetch curated prior knowledge (evidence pack) for a query + workspace.

        This is curation as a dynamic, workspace-KRS-biased lens over the refined
        DAG — NOT a frozen Exhibition. Returns cited evidence (source spans,
        knowledge, community reports, memory paths) WITHOUT a backend-synthesized
        answer, so a reasoning agent's own LLM can ground on it. Use this (not
        curator_query) when your agent does its own synthesis.
        """
        from .llm import build_client
        from . import config as _cfg
        from .retrieval import QueryOrchestrator, QueryRequest
        paths = _resolve_paths(workspace_path)
        client = build_client(_cfg.load_config(paths))
        try:
            return QueryOrchestrator(paths, client).fetch_context(
                QueryRequest(question=query, workspace_path=workspace_path, mode="auto")
            )
        finally:
            try:
                client.close()
            except Exception:
                pass

    @mcp.tool()
    def curator_explore(query: str, workspace_path: str = "") -> dict[str, Any]:
        """Explore-mode query: discover connections + provisional insight candidates."""
        from .llm import build_client
        from . import config as _cfg
        from .retrieval import QueryOrchestrator, QueryRequest
        paths = _resolve_paths(workspace_path)
        client = build_client(_cfg.load_config(paths))
        try:
            res = QueryOrchestrator(paths, client).run(
                QueryRequest(question=query, workspace_path=workspace_path, mode="explore")
            )
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            try:
                client.close()
            except Exception:
                pass
        return {
            "ok": res.ok, "answer": res.answer, "route": res.route, "trace_id": res.trace_id,
            "synthesis_node_ids": res.synthesis_node_ids,
            "memory_path_ids": res.memory_path_ids,
            "insight_candidate_ids": res.insight_candidate_ids,
            "prompt_trace_ids": res.prompt_trace_ids, "warnings": res.warnings,
            "error": res.error,
        }

    @mcp.tool()
    def curator_get_prompt_trace(trace_id: str, workspace_path: str = "") -> dict[str, Any]:
        """Return a recorded prompt run (PTR-…) for debugging prompt behavior."""
        paths = _resolve_paths(workspace_path)
        run = db.get_prompt_run(paths.state_db, trace_id)
        if run is None:
            return {"ok": False, "error": f"unknown prompt trace: {trace_id}"}
        return {"ok": True, "trace": run}

    @mcp.tool()
    def curator_list_insight_candidates(
        workspace_path: str = "", status: str = "pending"
    ) -> dict[str, Any]:
        """List provisional insight candidates (derived insights / corrections)."""
        paths = _resolve_paths(workspace_path)
        ws_id = Path(workspace_path).name if workspace_path else None
        return {"ok": True, "candidates": db.list_insight_candidates(
            paths.state_db, workspace_id=ws_id, status=status)}

    @mcp.tool()
    def curator_promote_insight(insight_id: str, workspace_path: str = "") -> dict[str, Any]:
        """Promote an insight candidate to a durable 02_Wiki/ note (human approval)."""
        from . import insight_lifecycle
        paths = _resolve_paths(workspace_path)
        try:
            rel = insight_lifecycle.promote_insight(paths, insight_id)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "promoted_to": rel, "insight_id": insight_id}

    @mcp.tool()
    def curator_propose_correction(
        node_id: str, correction: str, workspace_path: str = "", previous: str = ""
    ) -> dict[str, Any]:
        """Propose a correction to a generated node; classified before any patch.

        Source truth is never rewritten. Derived insights become provisional
        candidates; corrections target generated nodes only.
        """
        from .llm import build_client
        from . import config as _cfg, backprop_classifier as bpc, insight_lifecycle
        paths = _resolve_paths(workspace_path)
        client = build_client(_cfg.load_config(paths))
        try:
            event = bpc.BackpropEvent(
                previous_artifact=previous, updated_artifact=correction,
                affected_node_ids=[node_id] if node_id else [],
                workspace_id=Path(workspace_path).name if workspace_path else "",
            )
            classification = bpc.classify_feedback(paths.state_db, event, client)
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            try:
                client.close()
            except Exception:
                pass
        plan = insight_lifecycle.plan_action(classification)
        candidate_id = ""
        if plan.creates_candidate:
            candidate_id = insight_lifecycle.create_insight_from_classification(
                paths.state_db, classification, statement=correction,
                workspace_id=event.workspace_id, source_event_id=classification.trace_id,
            )
        return {
            "ok": classification.ok,
            "classification": classification.classification,
            "recommended_action": plan.action,
            "patch_node_ids": plan.patch_node_ids,
            "requires_human_review": plan.requires_human_review,
            "insight_candidate_id": candidate_id,
            "trace_id": classification.trace_id,
            "reason": classification.reason,
        }

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
    """Run the MCP server over stdio. Used by `wiki mcp`.

    The MCP server is the long-lived backend the plugin connects to, so it
    auto-starts Ollama (non-interactive, best-effort) for local chat/fallback
    profiles. Search defaults to llama-cpp GGUFs and unloads configured Ollama
    models before loading them when VRAM is tight. Failure is non-fatal.
    """
    try:
        from . import config as _cfg
        from . import model_setup

        paths = _cfg.WikiPaths(Path(os.environ["VAULT_ROOT"])) if os.environ.get("VAULT_ROOT") else None
        host = consts.DEFAULT_OLLAMA_HOST
        if paths is not None:
            host = (_cfg.load_config(paths).get("llm", {}).get("ollama", {}) or {}).get("host") or host
        model_setup.ensure_ollama_serving(host)
    except Exception:
        pass  # never block the daemon on model provisioning
    server = build_server()
    server.run()  # FastMCP defaults to stdio transport


# Snippets emitted by `wiki mcp install` so the user can paste into
# Claude Desktop / Claude Code / Antigravity configs without us touching
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

ANTIGRAVITY_SNIPPET_TEMPLATE = '''{{
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

    Both Claude Code/Desktop and Antigravity use the same MCP-spec
    `mcpServers` shape, so the snippets are identical apart from where
    the user pastes them. Kept as separate template strings so adding
    client-specific fields later (timeout, autoApprove, etc.) doesn't
    couple them.
    """
    vault_root = str(paths.root.resolve())
    return {
        consts.CLOUD_CLAUDE: CLAUDE_SNIPPET_TEMPLATE.format(vault_root=vault_root),
        consts.CLOUD_ANTIGRAVITY: ANTIGRAVITY_SNIPPET_TEMPLATE.format(vault_root=vault_root),
    }
