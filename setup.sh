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

echo "=== Writing Incurator build manifest ==="
python "$ROOT_DIR/scripts/build/write_build_manifest.py"
echo ""

echo "=== Building Incurator Obsidian Plugin (Frontend) ==="
cd "$ROOT_DIR/plugin"
if command -v npm &> /dev/null; then
    npm install
    npm run build
    echo "✓ Plugin build complete."

    # Deploy to vault: read last_root from global config cache
    LAST_ROOT_FILE="$ROOT_DIR/.cache/config/last_root"
    if [ -f "$LAST_ROOT_FILE" ]; then
        VAULT_ROOT="$(cat "$LAST_ROOT_FILE" | tr -d '\r\n')"
        PLUGIN_DEST="$VAULT_ROOT/.obsidian/plugins/incurator-obsidian-agent"
        if [ -d "$VAULT_ROOT" ]; then
            mkdir -p "$PLUGIN_DEST"
            for f in main.js manifest.json styles.css; do
                [ -f "$ROOT_DIR/plugin/$f" ] && cp "$ROOT_DIR/plugin/$f" "$PLUGIN_DEST/$f"
            done
            echo "✓ Plugin deployed to $PLUGIN_DEST"
            echo "ℹ️  Reload the Incurator plugin in Obsidian to apply the update."
        else
            echo "⚠️  last_root vault not found at $VAULT_ROOT — skipping deploy."
        fi
    else
        echo "ℹ️  No last_root found — run 'wiki init <vault>' once to register your vault."
    fi
else
    echo "⚠️  npm not found. Skipping plugin build."
fi
echo ""

echo "=== Installing Incurator backend into the repo-root service/runtime venv ==="
cd "$ROOT_DIR"
echo "=== Installing dependencies via uv or pip ==="
if command -v uv &> /dev/null; then
    uv pip install --python "$VIRTUAL_ENV/bin/python" -e "$ROOT_DIR/backend"
else
    pip install -e "$ROOT_DIR/backend"
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
echo "=== Setup complete ==="
