"""MCP server — exposes the Curator DAG to workspace agents.

Run via:    wiki mcp           # stdio transport (default)
Install:    wiki mcp install   # prints a config snippet for Claude / Gemini

The server combines two responsibility layers:

1. **Search delegation** — the `search` tool shells out to the bundled
   `src/qmd/bin/qmd` to leverage qmd's BM25 + vector + LLM-rerank pipeline.
   No HTTP daemon required; qmd is invoked per-call and qmd's own model
   caching keeps latency low.

2. **Curator-specific traversal** — tools like `curator_traverse_evidence`,
   `curator_get_node`, `curator_find_contradictions` walk the DAG by ID
   using the on-disk markdown source-of-truth, so the agent can follow
   EXH → CON → ATM chains, surface contradictions, and respect confidence
   thresholds.

Vault resolution:
    1. `WIKI_ROOT` env var
    2. cfg.find_wiki_root() walking up from `cwd`
    Server raises a clear error early if neither resolves.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from mcp.server.fastmcp import Context, FastMCP
except ImportError as e:  # pragma: no cover - import-time hint
    raise ImportError(
        "The `mcp` package is required. Install with: "
        "uv pip install -e '.[mcp]'"
    ) from e

from . import config as cfg
from . import page_writer
from . import search


# ---------------------------------------------------------------------------
# Vault resolution (run once at import / server-start)
# ---------------------------------------------------------------------------


def _resolve_paths() -> cfg.WikiPaths:
    """Locate the vault and return WikiPaths or raise a clear error."""
    env_root = os.environ.get("WIKI_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if (candidate / cfg.INTERNAL_DIR / cfg.CONFIG_FILE).exists():
            return cfg.paths_from_config(candidate)
        raise RuntimeError(
            f"WIKI_ROOT={candidate} does not contain {cfg.INTERNAL_DIR}/{cfg.CONFIG_FILE}. "
            f"Run `wiki init` there or point WIKI_ROOT at an initialised vault."
        )
    discovered = cfg.find_wiki_root()
    if discovered is None:
        raise RuntimeError(
            "No incurator vault found. Set WIKI_ROOT to your vault root, or "
            "run `wiki mcp` from inside an initialised project."
        )
    return cfg.paths_from_config(discovered)


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
    "domain", "subdomain", "text", "exhibition_intent",
    "disambiguation_keywords", "confidence", "updated_at",
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
        paths = _resolve_paths()
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
        import re as _re
        match = _re.search(r"\{.*\}", response, _re.DOTALL)
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


def curator_update_curator_persona(request: str) -> dict:
    """Update the vault-level Curator persona based on a natural-language request.

    request: natural language description of what to change

    Returns: {"updated_fields": [...], "before": {...}, "after": {...}}
    """
    from .llm import build_client, ChatMessage

    try:
        paths = _resolve_paths()
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
        import re as _re
        match = _re.search(r"\{.*\}", response, _re.DOTALL)
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
# Server construction
# ---------------------------------------------------------------------------


def build_server() -> FastMCP:
    """Build and register all tools on a fresh FastMCP instance."""
    paths = _resolve_paths()
    mcp = FastMCP(
        name="incurator",
        instructions=(
            "incurator Curator MCP. Workflow for a workspace session:\n"
            "  1. Call `curator_check_workspace` first — validates curate.yml and returns "
            "workspace status, including whether an Exhibition exists.\n"
            "  2. If `needs_curation` is true, call `curator_curate_workspace` to generate "
            "the L4 Exhibition from the knowledge graph, then retry `search_curator`.\n"
            "  3. Use `search_curator` for BM25/vector/hybrid search. Results are Exhibition-first.\n"
            "  4. Walk evidence with `curator_traverse_evidence` (EXH→CON→ATM).\n"
            "  5. Correct knowledge by editing L4 Exhibitions only via `curator_update_node` "
            "(EXH- IDs only — backward propagation updates L1-L3 automatically).\n"
            "  6. Add new insights with `curator_add_knowledge`.\n"
            "Layer prefixes: 01_Contexts (CTX-), 02_Atoms (ATM-), "
            "03_Concepts (CON-), 04_Exhibitions (EXH-)."
        ),
    )

    # ------------------------------------------------------------------
    # search — qmd-backed retrieval, with optional layer filter
    # ------------------------------------------------------------------

    @mcp.tool()
    def search_curator(
        query: str,
        mode: str = "hybrid",
        limit: int = 8,
        min_score: float = 0.6,
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

        Returns a dict with `hits` (each has `path`, `title`, `score`, `snippet`,
        `body`), `count`, and optionally `needs_curation` with guidance.
        """
        # Auto-sync: if there are pending sources, curate them synchronously first
        from . import db as _db
        if _db.get_pending_count(paths.state_db) > 0:
            import subprocess
            subprocess.run(
                ["wiki", "curate", "--no-sync"],
                cwd=str(paths.root),
                check=False,
                capture_output=True,
            )

        # Load curate.yml if WORKSPACE_PATH is set
        from . import curate_yml as _cym
        from pathlib import Path as _Path
        import os as _os
        ws_path_str = _os.environ.get("WORKSPACE_PATH")
        ws_exh = None  # resolved below if workspace is configured
        curate_spec = None
        if ws_path_str:
            ws_path = _Path(ws_path_str).expanduser().resolve()
            if not ws_path.exists():
                return {
                    "error": f"WORKSPACE_PATH does not exist: {ws_path_str}",
                    "guidance": "Set WORKSPACE_PATH to a valid workspace directory containing curate.yml.",
                    "hits": [],
                    "count": 0,
                }
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
            if ws_exh is None:
                return {
                    "needs_curation": True,
                    "message": (
                        "No workspace Exhibition found for this workspace. "
                        "Call curator_curate_workspace() to generate it, then retry search_curator."
                    ),
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
        import subprocess as _subprocess
        import os as _os
        ws = workspace_path or _os.environ.get("WORKSPACE_PATH", "")
        if not ws:
            return {"error": "workspace_path required (or set WORKSPACE_PATH env var)"}
        result = _subprocess.run(
            ["wiki", "curate", "--workspace", ws, "--no-sync"],
            cwd=str(paths.root),
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip() or "wiki curate failed"}
        from . import ingest_llm as _ingest_llm
        from . import curate_yml as _cym
        from pathlib import Path as _Path
        spec = _cym.load_curate_spec(_Path(ws).expanduser().resolve())
        project = spec.project if spec else ws
        ws_exh = _ingest_llm.find_workspace_exhibition(paths, project)
        # Rebuild search index so the new Exhibition is immediately searchable
        try:
            search.update_index(paths, embed=True)
        except Exception:
            pass
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
        import os as _os
        from pathlib import Path as _Path
        from . import curate_yml as _cym
        from . import ingest_llm as _ingest_llm

        ws = workspace_path or _os.environ.get("WORKSPACE_PATH", "")
        issues: list[str] = []

        if not ws:
            issues.append(
                "WORKSPACE_PATH is not set. "
                "Start the MCP server with WORKSPACE_PATH=/path/to/workspace, "
                "or call curator_check_workspace('/path/to/workspace')."
            )
            return {"ok": False, "issues": issues}

        ws_path = _Path(ws).expanduser().resolve()
        if not ws_path.exists():
            issues.append(
                f"Workspace directory does not exist: {ws}. "
                "Create it with: wiki workspace init /path/to/workspace"
            )
            return {"ok": False, "issues": issues}

        curate_file = ws_path / "curate.yml"
        if not curate_file.exists():
            issues.append(
                f"curate.yml not found in {ws}. "
                "Run: wiki workspace init /path/to/workspace"
            )
            return {"ok": False, "workspace": ws, "issues": issues}

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
        try:
            from .workspace.provisioner import detect_agent_from_client_info, prepare_workspace
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
            if not agent_marker.exists():
                prepare_workspace(
                    wiki_root=paths.root,
                    workspace=ws_path,
                    agent=detected_agent,
                    install_rules=True,
                    force_curate=False,
                )
                agent_rules_installed = detected_agent
        except Exception:
            pass

        result: dict[str, Any] = {
            "ok": len(issues) == 0,
            "workspace": ws,
            "project": spec.project,
            "exhibition": exh_path.stem if exh_path else None,
            "exhibition_exists": exh_path is not None,
            "issues": issues,
        }
        if agent_rules_installed is not None:
            result["agent_rules_installed"] = agent_rules_installed
        return result

    # ------------------------------------------------------------------
    # curator_get_node — fetch any DAG node by ID
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_get_node(node_id: str) -> dict[str, Any]:
        """Fetch a single DAG node (Context/Atom/Concept/Exhibition) by ID.

        Args:
            node_id: e.g. 'EXH-abcdef01', 'ATM-9f8e7d6c'. Prefix determines
                     the layer.

        Returns the node's frontmatter + body, or `{'error': ...}` if missing.
        """
        return _read_node(paths, node_id)

    # ------------------------------------------------------------------
    # curator_traverse_evidence — walk SYN → CON → ATM
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_traverse_evidence(cur_id: str) -> dict[str, Any]:
        """Walk an Exhibition's evidence chain down to its constituent Atoms.

        Returns the full EXH page plus every CON it depends on and every ATM
        each CON depends on, including confidence/contradiction flags. Use
        this to verify an Exhibition claim before citing it (especially when
        confidence_score < 0.90).
        """
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
    ) -> dict[str, Any]:
        """List Atoms that are flagged for human review or carry `contradicts`
        entries.

        Each entry includes a `dismissed` field indicating whether the pair has
        been dismissed as a false positive via `curator_dismiss_contradiction`.

        Args:
            node_id: Optional. If given, returns contradictions only for the
                     subgraph reachable from this node (EXH/CON/ATM). Else
                     returns all flagged atoms in the vault.
        """
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
    ) -> dict[str, Any]:
        """Dismiss a deep-check contradiction as a false positive.

        Future `wiki sync` runs will skip this pair permanently.
        Also clears `is_flagged_for_agent` on both Atom files.

        Args:
            atom_a: ATM-id or path like '02_Atoms/ATM-xxx.md'.
            atom_b: ATM-id or path like '02_Atoms/ATM-yyy.md'.
            reason: Optional explanation (logged to contradiction_dismissed.json).

        Returns `{'ok': True, 'dismissed': [atom_a_id, atom_b_id]}`.
        """
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
    ) -> dict[str, Any]:
        """Analyze and optionally resolve a contradiction between two L2 Atoms.

        This is the sole MCP tool authorized to write L2 Atom body content,
        specifically for resolving a flagged contradiction.

        Args:
            atom_a: ATM-id or '02_Atoms/ATM-xxx.md'.
            atom_b: ATM-id or '02_Atoms/ATM-yyy.md'.
            apply:  False (default) — return the proposal for review.
                    True — apply the proposal and mark resolved.

        Workflow:
            1. Call with apply=False to get the LLM proposal.
            2. Review `atom_a_body_revised` and `atom_b_body_revised`.
            3. Call again with apply=True to write the changes.

        Returns a dict with `reasoning`, `atom_a_body_revised`,
        `atom_b_body_revised`, and `applied` (bool).
        """
        from . import contradiction as _cd
        import json as _json
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
            proposal = _json.loads(raw)
        except (LLMError, _json.JSONDecodeError, Exception) as exc:
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
    def curator_layer_index() -> dict[str, Any]:
        """Return per-layer page counts and a sample of recent IDs.

        Layers: context (CTX-), atom (ATM-), concept (CON-), exhibition (EXH-).
        Cheap overview suitable as the agent's first call when entering a
        fresh vault — tells it what's available before any search.
        """
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
    def curator_status() -> dict[str, Any]:
        """Return vault root, qmd binary readiness, and total page counts."""
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
    def curator_update_node(node_id: str, new_content: str) -> dict[str, Any]:
        """Overwrite an L4 Exhibition and propagate changes backward through the DAG.

        Only EXH- (Exhibition) nodes may be edited directly by agents. L1/L2/L3 nodes
        are pipeline-generated and must be updated via backward propagation from L4.

        Args:
            node_id: The Exhibition to update (must start with EXH-).
            new_content: Full replacement markdown (frontmatter + body).

        Writes the Exhibition file, then runs upstream backward propagation
        (EXH → CON → ATM) via LLM so referenced Concepts and Atoms are updated
        to reflect the correction. Finally rebuilds routing tables.

        Returns a dict with `updated`, `propagation`, `gaps`, and
        `routing_tables_rebuilt`.
        """
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
                    paths, _client, node_id
                )
                propagation_summary = {
                    "concepts_updated": prop_result.concepts_updated,
                    "atoms_updated": prop_result.atoms_updated,
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
    def curator_reindex() -> dict[str, Any]:
        """Rebuild the QMD search index over all Collections pages.

        Call this after manually editing wiki pages or after a bulk import so
        that `search_curator` picks up the new content.

        Returns `{'ok': True}` or `{'error': ...}`.
        """
        try:
            search.update_index(paths, embed=True)
            return {"ok": True}
        except search.SearchBackendError as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # curator_curate_context — re-curate a single L1 Context
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_curate_context(context_id: str) -> dict[str, Any]:
        """Re-run the LLM curation pipeline for a single L1 Context.

        Resets the source status to 'pending' in the DB, then invokes
        `wiki add` (which covers L1-L3 compilation) as a subprocess.

        Args:
            context_id: The CTX- ID of the context to re-curate.

        Returns `{'queued': True, 'source_id': <int>}` on success, or
        `{'error': ...}` on failure.
        """
        import subprocess
        from . import db

        db_path = paths.root / ".curator" / "state.sqlite"
        with db.connect(db_path) as conn:
            row = conn.execute(
                "SELECT id FROM sources WHERE context_id = ?", (context_id,)
            ).fetchone()
        if row is None:
            return {"error": f"No source found with context_id '{context_id}'"}

        source_id = row["id"]
        with db.connect(db_path) as conn:
            conn.execute(
                "UPDATE sources SET status = 'pending' WHERE id = ?", (source_id,)
            )

        try:
            subprocess.Popen(
                ["wiki", "add"],
                cwd=str(paths.root),
                start_new_session=True,
            )
        except Exception as exc:
            return {"error": f"Failed to launch wiki curate: {exc}"}

        return {"queued": True, "source_id": source_id}

    # ------------------------------------------------------------------
    # curator_add_knowledge — write a new L2 Atom from conversational insight
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_add_knowledge(insight: str, context: str = "") -> dict[str, Any]:
        """Create a new L2 Atom from a conversational insight or synthesized answer.

        Feeds new knowledge discovered during an agent conversation back into
        the L1-L3 pipeline so it is available for future Exhibition staging.

        Args:
            insight: The text of the insight or knowledge to preserve as an Atom.
            context: Optional context about the source of this insight
                     (e.g. 'derived from a discussion about project X').

        Returns `{'atom_id': '...', 'ok': True}` or `{'error': ...}`.
        """
        try:
            from .llm import build_client
            from . import config as _cfg
            _config = _cfg.load_config(paths)
            _client = build_client(_config)
        except Exception as exc:
            return {"error": f"Could not start LLM client: {exc}"}

        try:
            from . import ingest_llm as _ingest
            from datetime import datetime, timezone
            today = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            source_hint = context or "mcp:curator_add_knowledge"
            combined = f"{insight}\n\n{context}".strip() if context else insight
            atom_id = _ingest.add_atom_from_insight(paths, _client, combined, today, source_hint)
            if atom_id is None:
                return {"error": "Atom generation failed — LLM returned no candidates"}
            return {"atom_id": atom_id, "ok": True}
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
        "WIKI_ROOT": "{wiki_root}"
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
        "WIKI_ROOT": "{wiki_root}"
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
    wiki_root = str(paths.root.resolve())
    return {
        "claude": CLAUDE_SNIPPET_TEMPLATE.format(wiki_root=wiki_root),
        "gemini": GEMINI_SNIPPET_TEMPLATE.format(wiki_root=wiki_root),
    }
