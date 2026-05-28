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

echo ""
echo "=== Setup complete ==="
