# incurator

The Python backend of Incurator: an LLM-maintained personal knowledge base
(Zettelkasten) that ingests external sources through a four-layer curation
pipeline and exposes the result to both humans and agents.

This package is the `incurator` distribution. It is one half of a monorepo —
the other half is the Obsidian plugin under `plugin/`. For the project overview,
installation walkthrough, and user guides, see
[the repository documentation](https://github.com/shinywings/Incurator/blob/master/docs/README.md).

## Pipeline

Sources are parsed, deduplicated by content hash, and lifted through four
layers, each of which is stored in `state.sqlite` and rendered to a derived
markdown corpus:

| Layer | Prefix | What it holds |
|-------|--------|---------------|
| L1 Contexts | `CTX-` | Source spans, with provenance back to the file and page |
| L2 Atoms | `ATM-` | Atomic facts extracted from a span |
| L3 Concepts | `CON-` | Cross-source thematic groupings |
| L4 Synthesis | `SYN-` | Shared stored synthesis across the graph |

Retrieval is DB-native: SQLite FTS5/BM25 plus chunk vectors, fused with
reciprocal rank fusion and reranked by an LLM. There is no external search
binary.

## Install

```bash
uv pip install -e ./backend
```

Providers are pluggable — Ollama, Antigravity, Claude, and OpenAI-compatible
endpoints are all supported, with failover between them.

## Entry point

The package installs a `wiki` command:

```bash
wiki init <path>        # Initialize a Curator vault
wiki update             # One-shot pipeline: add -> build -> embed -> sync
wiki query "<question>" # Search and synthesize an answer with citations
wiki status             # Show config and stats
```

`wiki --help` lists the full command surface.

## License

MIT.
