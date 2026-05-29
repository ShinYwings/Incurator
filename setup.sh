#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BUILD_PLUGIN=0
if [[ "${1:-}" == "--plugin" ]] || [[ "${1:-}" == "--all" ]] || [ -n "${OBSIDIAN_PLUGIN_DIR:-}" ]; then
  BUILD_PLUGIN=1
fi

echo "=== Installing Incurator backend ==="
bash "$ROOT_DIR/backend/install.sh"

if [ "$BUILD_PLUGIN" -eq 1 ]; then
  echo ""
  echo "=== Installing Obsidian plugin dependencies ==="
  cd "$ROOT_DIR/plugin"
  npm install

  echo ""
  echo "=== Building Obsidian plugin ==="
  npm run build

  if [ -n "${OBSIDIAN_PLUGIN_DIR:-}" ]; then
    echo ""
    echo "=== Deploying to Obsidian vault ==="
    OBSIDIAN_PLUGIN_DIR="$OBSIDIAN_PLUGIN_DIR" npm run build
    echo "  → $OBSIDIAN_PLUGIN_DIR"
  fi
else
  echo ""
  echo "ℹ️  Skipping Obsidian plugin build."
  echo "   (Run with '--plugin' or set OBSIDIAN_PLUGIN_DIR to build and deploy the plugin)"
fi

echo ""
echo "=== Setup complete ==="
