#!/bin/bash
set -euo pipefail

if [ -z "${OBSIDIAN_PLUGIN_DIR:-}" ]; then
  echo "Error: OBSIDIAN_PLUGIN_DIR environment variable is not set."
  echo "Please set it to your target vault's plugin directory."
  echo "Example: OBSIDIAN_PLUGIN_DIR=/path/to/vault/.obsidian/plugins/incurator-obsidian-agent ./deploy.sh"
  exit 1
fi

export OBSIDIAN_PLUGIN_DIR

echo "Deploying Incurator Obsidian plugin to: ${OBSIDIAN_PLUGIN_DIR}"
cd "$(dirname "$0")"
npm run build
