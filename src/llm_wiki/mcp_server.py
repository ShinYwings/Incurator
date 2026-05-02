"""MCP server — exposes the Curator DAG to workspace agents.

Run via:    wiki mcp           # stdio transport (default)
Install:    wiki mcp install   # prints a config snippet for Claude / Gemini

The server combines two responsibility layers:

1. **Search delegation** — the `search` tool shells out to the bundled
   `src/qmd/bin/qmd` to leverage qmd's BM25 + vector + LLM-rerank pipeline.
   No HTTP daemon required; qmd is invoked per-call and qmd's own model
   caching keeps latency low.

2. **Curator-specific traversal** — tools like `curator_traverse_evidence`,
   `curator_get_atom`, `curator_find_contradictions` walk the DAG by ID
   using the on-disk markdown source-of-truth, so the agent can follow
   SYN → CON → ATM chains, surface contradictions, and respect confidence
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
            "No LLM-Wiki vault found. Set WIKI_ROOT to your vault root, or "
            "run `wiki mcp` from inside an initialised project."
        )
    return cfg.paths_from_config(discovered)


# ---------------------------------------------------------------------------
# DAG helpers — read-only access to the on-disk Curator collections
# ---------------------------------------------------------------------------


_LAYERS = {
    "summary":   ("01_Summaries", "SUM-"),
    "atom":      ("02_Atoms",     "ATM-"),
    "concept":   ("03_Concepts",  "CON-"),
    "synthesis": ("04_Synthesis", "SYN-"),
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
        return {"error": f"Unknown ID prefix in '{node_id}' (expected SUM-/ATM-/CON-/SYN-)"}
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
    """'02_Atoms/ATM-abc12345' → 'ATM-abc12345'."""
    s = _normalize_link(link)
    return s.rsplit("/", 1)[-1]


# ---------------------------------------------------------------------------
# Server construction
# ---------------------------------------------------------------------------


def build_server() -> FastMCP:
    """Build and register all tools on a fresh FastMCP instance."""
    paths = _resolve_paths()
    mcp = FastMCP(
        name="llm-wiki",
        instructions=(
            "LLM-Wiki Curator MCP. Tools fall into two groups:\n"
            "  - `search`: BM25/vector/hybrid search across the Curator DAG via qmd.\n"
            "  - `curator_*`: walk the DAG by ID (SYN→CON→ATM evidence chains, "
            "contradiction lookup, layer-aware retrieval).\n"
            "Layer prefixes: 01_Summaries (SUM-), 02_Atoms (ATM-), "
            "03_Concepts (CON-), 04_Synthesis (SYN-)."
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
            scope: 'all' | 'summaries' | 'atoms' | 'concepts' | 'synthesis'.
            mode: 'hybrid' (BM25 + vector + LLM rerank, best quality), 'lex'
                  (BM25 only, fastest), 'vec' (vector only).
            limit: Max number of hits before min_score filtering.
            min_score: Drop hits below this score (0.0 = keep all).

        Returns a dict with `hits` — each hit has `path`, `title`, `score`,
        `snippet`, and `body` (full markdown of the page).
        """
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
            "summaries": "01_Summaries/",
            "atoms":     "02_Atoms/",
            "concepts":  "03_Concepts/",
            "synthesis": "04_Synthesis/",
        }.get(scope)

        hits = []
        for hit in results.hits:
            if layer_prefix and not hit.full_path.startswith(layer_prefix):
                continue
            hits.append({
                "path": hit.full_path,
                "title": hit.title,
                "score": round(hit.score, 4),
                "snippet": hit.snippet,
                "body": hit.full_content,
                "docid": hit.docid,
            })
        return {"hits": hits, "count": len(hits)}

    # ------------------------------------------------------------------
    # curator_get_node — fetch any DAG node by ID
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_get_node(node_id: str) -> dict[str, Any]:
        """Fetch a single DAG node (Summary/Atom/Concept/Synthesis) by ID.

        Args:
            node_id: e.g. 'SYN-abcdef01', 'ATM-9f8e7d6c'. Prefix determines
                     the layer.

        Returns the node's frontmatter + body, or `{'error': ...}` if missing.
        """
        return _read_node(paths, node_id)

    # ------------------------------------------------------------------
    # curator_traverse_evidence — walk SYN → CON → ATM
    # ------------------------------------------------------------------

    @mcp.tool()
    def curator_traverse_evidence(syn_id: str) -> dict[str, Any]:
        """Walk a Synthesis's evidence chain down to its constituent Atoms.

        Returns the full SYN page plus every CON it depends on and every ATM
        each CON depends on, including confidence/contradiction flags. Use
        this to verify a Synthesis claim before citing it (especially when
        confidence_score < 0.90).
        """
        syn = _read_node(paths, syn_id)
        if "error" in syn:
            return syn
        if syn["layer"] != "synthesis":
            return {"error": f"{syn_id} is a {syn['layer']}, not a synthesis."}

        concepts: list[dict[str, Any]] = []
        atoms: list[dict[str, Any]] = []
        seen_atoms: set[str] = set()

        for raw_link in syn["frontmatter"].get("core_concepts", []) or []:
            if not isinstance(raw_link, str):
                continue
            con_id = _id_from_link(raw_link)
            con = _read_node(paths, con_id)
            if "error" in con:
                concepts.append({"id": con_id, "error": con["error"]})
                continue
            concepts.append(con)

            for atm_link in con["frontmatter"].get("dependencies", []) or []:
                if not isinstance(atm_link, str):
                    continue
                atm_id = _id_from_link(atm_link)
                if atm_id in seen_atoms:
                    continue
                seen_atoms.add(atm_id)
                atoms.append(_read_node(paths, atm_id))

        return {
            "synthesis": syn,
            "confidence_score": syn["frontmatter"].get("confidence_score"),
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
                     subgraph reachable from this node (SYN/CON/ATM). Else
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

        # SYN or CON: walk down to atoms via traversal logic
        atom_ids: set[str] = set()
        if info[0] == "synthesis":
            chain = curator_traverse_evidence(node_id)
            for atom in chain.get("atoms", []):
                if "id" in atom:
                    atom_ids.add(atom["id"])
        elif info[0] == "concept":
            con = _read_node(paths, node_id)
            for atm_link in con.get("frontmatter", {}).get("dependencies", []) or []:
                if isinstance(atm_link, str):
                    atom_ids.add(_id_from_link(atm_link))

        for aid in atom_ids:
            atom = _read_node(paths, aid)
            if "error" in atom:
                continue
            fm = atom["frontmatter"]
            if fm.get("is_flagged_for_agent") or fm.get("contradicts"):
                flagged.append({
                    "id": aid,
                    "path": atom["path"],
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
    "llm-wiki": {{
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
    "llm-wiki": {{
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
