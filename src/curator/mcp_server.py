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

import os
from pathlib import Path
from typing import Any, Optional

try:
    from mcp.server.fastmcp import FastMCP
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
            "No InCurator vault found. Set WIKI_ROOT to your vault root, or "
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
# Server construction
# ---------------------------------------------------------------------------


def build_server() -> FastMCP:
    """Build and register all tools on a fresh FastMCP instance."""
    paths = _resolve_paths()
    mcp = FastMCP(
        name="incurator",
        instructions=(
            "InCurator Curator MCP. Tools fall into two groups:\n"
            "  - `search`: BM25/vector/hybrid search across the Curator DAG via qmd.\n"
            "  - `curator_*`: walk the DAG by ID (EXH→CON→ATM evidence chains, "
            "contradiction lookup, layer-aware retrieval).\n"
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
        scope: str = "all",
        mode: str = "hybrid",
        limit: int = 8,
        min_score: float = 0.0,
    ) -> dict[str, Any]:
        """Search the Curator DAG.

        Args:
            query: Natural-language query.
            scope: 'all' | 'contexts' | 'atoms' | 'concepts' | 'exhibitions'.
            mode: 'hybrid' (BM25 + vector + LLM rerank, best quality), 'lex'
                  (BM25 only, fastest), 'vec' (vector only).
            limit: Max number of hits before min_score filtering.
            min_score: Drop hits below this score (0.0 = keep all).

        Returns a dict with `hits` — each hit has `path`, `title`, `score`,
        `snippet`, and `body` (full markdown of the page).
        """
        # Auto-sync: if there are pending sources, curate them synchronously first
        from . import db as _db
        if _db.get_pending_count(paths.state_db) > 0:
            import subprocess
            subprocess.run(
                ["wiki", "curate", "--batch"],
                cwd=str(paths.root),
                check=False,
            )

        # v0.1.0: Apply curate.yml filters from WORKSPACE_PATH env var if present
        from . import curate_yml as _cym
        from pathlib import Path as _Path
        import os as _os
        ws_path_str = _os.environ.get("WORKSPACE_PATH")
        curate_spec = None
        if ws_path_str:
            try:
                curate_spec = _cym.load_curate_spec(_Path(ws_path_str).expanduser().resolve())
            except (ValueError, Exception):
                curate_spec = None

        if curate_spec is not None:
            # Apply scope from curate.yml only if caller left scope at default "all"
            if scope == "all" and curate_spec.scope != "all":
                scope = curate_spec.scope
            # Apply confidence floor
            min_score = max(min_score, curate_spec.min_confidence)
            # Boost query with domain/topic terms
            query = curate_spec.boost_query(query)

        # Automatically generate / translate arguments if the query is in Korean (non-ASCII)
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

        layer_prefix = {
            "contexts":    "01_Contexts/",
            "atoms":       "02_Atoms/",
            "concepts":    "03_Concepts/",
            "exhibitions": "04_Exhibitions/",
        }.get(scope)

        hits = []
        for hit in results.hits:
            if layer_prefix and not hit.full_path.startswith(layer_prefix):
                continue
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
        return {
            "hits": hits,
            "count": len(hits),
            "curate_spec_applied": curate_spec.project if curate_spec else None,
        }

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

        Args:
            node_id: Optional. If given, returns contradictions only for the
                     subgraph reachable from this node (EXH/CON/ATM). Else
                     returns all flagged atoms in the vault.
        """
        flagged: list[dict[str, Any]] = []

        if node_id is None:
            atoms_dir = paths.atoms
            if not atoms_dir.exists():
                return {"flagged_atoms": [], "count": 0}
            for md in sorted(atoms_dir.glob("ATM-*.md")):
                parsed = page_writer.read_page(md)
                if parsed is None:
                    continue
                fm = parsed.frontmatter
                if fm.get("is_flagged_for_agent") or fm.get("contradicts"):
                    flagged.append({
                        "id": fm.get("id") or md.stem,
                        "path": f"02_Atoms/{md.name}",
                        "is_flagged_for_agent": bool(fm.get("is_flagged_for_agent")),
                        "contradicts": fm.get("contradicts") or [],
                        "claim_type": fm.get("claim_type"),
                        "title_preview": (parsed.body.splitlines()[0] if parsed.body else "").lstrip("# ").strip(),
                    })
            return {"flagged_atoms": flagged, "count": len(flagged)}

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
                flagged.append({
                    "id": node_id,
                    "path": atom["path"],
                    "is_flagged_for_agent": bool(fm.get("is_flagged_for_agent")),
                    "contradicts": fm.get("contradicts") or [],
                })
            return {"flagged_atoms": flagged, "count": len(flagged)}

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
                flagged.append({
                    "id": aid,
                    "path": atm["path"],
                    "is_flagged_for_agent": bool(fm.get("is_flagged_for_agent")),
                    "contradicts": fm.get("contradicts") or [],
                })
        return {"flagged_atoms": flagged, "count": len(flagged)}

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
        """Overwrite a DAG node's markdown file and propagate changes through the DAG.

        Args:
            node_id: The node to update (CTX-/ATM-/CON-/EXH-).
            new_content: Full replacement markdown (frontmatter + body).

        For **EXH nodes** (Exhibitions): writes the file, then runs upstream backward
        propagation (EXH → CON → ATM) via LLM so referenced Concepts and Atoms are
        updated to reflect the correction. Finally rebuilds routing tables.

        For **ATM/CON/CTX nodes**: writes the file and runs Mode B structural
        verification (bidirectional), then rebuilds routing tables.

        Returns a dict with `updated`, `propagation` (EXH only), `gaps`, and
        `routing_tables_rebuilt`.
        """
        info = _layer_for_id(node_id)
        if info is None:
            return {"error": f"Unknown ID prefix in '{node_id}' (expected CTX-/ATM-/CON-/EXH-)"}
        layer, subdir = info
        page_path = paths.collections / subdir / f"{node_id}.md"
        if not page_path.exists():
            return {"error": f"Page not found: {subdir}/{node_id}.md"}

        page_path.write_text(new_content, encoding="utf-8")

        from . import sync as sync_module

        # EXH correction: propagate upstream L4 → L3 → L2 via LLM
        propagation_summary: dict[str, Any] = {}
        if layer == "exhibition":
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

        # Structural verification (Mode B) for all node types
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

        result: dict[str, Any] = {
            "updated": True,
            "gaps": [{"layer": g.layer, "node_id": g.node_id, "message": g.message} for g in gaps],
            "routing_tables_rebuilt": routing_rebuilt,
        }
        if propagation_summary:
            result["propagation"] = propagation_summary
        return result

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
                     (e.g. 'derived from query about transformers').

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
