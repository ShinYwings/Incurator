#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
cd "$ROOT_DIR/backend"

echo "=== Installing dependencies via uv or pip ==="
if command -v uv &> /dev/null; then
    uv pip install -e .
else
    pip install -e .
fi

echo ""
echo "=== Running post-installation build hook ==="
python ../scripts/build/hatch_build.py

echo ""
echo "ℹ️  Note: Obsidian plugin installation is now handled interactively via 'wiki init'."

echo ""
echo "=== Setup complete ==="
