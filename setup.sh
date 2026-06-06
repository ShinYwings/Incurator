#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Setting up Python Virtual Environment ==="
export VIRTUAL_ENV="$ROOT_DIR/.venv"
export PATH="$VIRTUAL_ENV/bin:$PATH"

if [ ! -d "$VIRTUAL_ENV" ]; then
    if command -v uv &> /dev/null; then
        uv venv "$VIRTUAL_ENV"
    else
        python3 -m venv "$VIRTUAL_ENV"
    fi
fi

echo "=== Writing Incurator build fingerprint ==="
python "$ROOT_DIR/scripts/build/write_build_manifest.py"
echo ""

echo "=== Building Incurator Obsidian Plugin (Frontend) ==="
cd "$ROOT_DIR/plugin"
if command -v npm &> /dev/null; then
    npm install
    npm run build
    echo "✓ Plugin build complete."
else
    echo "⚠️  npm not found. Skipping plugin build."
fi
echo ""

echo "=== Installing Incurator backend ==="
cd "$ROOT_DIR"
echo "=== Installing dependencies via uv or pip ==="
if command -v uv &> /dev/null; then
    uv pip install -e ./backend
else
    pip install -e ./backend
fi

echo ""
echo "=== Running post-installation build hook ==="
python scripts/build/hatch_build.py

echo ""
echo "=== Provisioning search models (Ollama embedder + llama-cpp reranker) ==="
# Idempotent + safe to re-run on update. Degrades gracefully: search still works
# (FTS5/RRF) even if a model is unavailable. Skip with INCURATOR_SKIP_MODELS=1.
if [ "${INCURATOR_SKIP_MODELS:-0}" != "1" ]; then
    if command -v wiki &> /dev/null; then
        wiki models ensure || echo "⚠️  Some model steps degraded — search still works. Re-run: wiki models ensure"
    else
        echo "ℹ️  'wiki' not on PATH yet; after it is, run: wiki models ensure"
    fi
else
    echo "ℹ️  INCURATOR_SKIP_MODELS=1 set — skipping model provisioning. Run later: wiki models ensure"
fi

echo ""
echo "ℹ️  Note: Obsidian plugin installation is now handled interactively via 'wiki init'."

echo ""
echo "=== Setup complete ==="
