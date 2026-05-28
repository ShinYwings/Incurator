#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Installing Incurator backend ==="
bash "$ROOT_DIR/backend/install.sh"

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
else
  echo ""
  echo "ℹ️  Set OBSIDIAN_PLUGIN_DIR to auto-deploy to the vault."
  echo "   Example:"
  echo "   OBSIDIAN_PLUGIN_DIR=/home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent \\"
  echo "     bash setup.sh"
fi

echo ""
echo "=== Setup complete ==="
