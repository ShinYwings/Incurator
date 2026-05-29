#!/bin/bash
set -euo pipefail

: "${OBSIDIAN_PLUGIN_DIR:=/home/shin/Workspace/second_brain/.obsidian/plugins/incurator-obsidian-agent}"
export OBSIDIAN_PLUGIN_DIR

echo "Deploying Incurator Obsidian plugin to: ${OBSIDIAN_PLUGIN_DIR}"
cd "$(dirname "$0")"
npm run build
