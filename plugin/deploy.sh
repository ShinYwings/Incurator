#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

# 변수가 없으면 에러를 뿜는 대신 로컬 빌드 안내 메시지를 출력합니다.
if [ -z "${OBSIDIAN_PLUGIN_DIR:-}" ]; then
  echo "OBSIDIAN_PLUGIN_DIR is not set. Building in the local directory..."
else
  echo "Deploying Incurator Obsidian plugin to: ${OBSIDIAN_PLUGIN_DIR}"
  export OBSIDIAN_PLUGIN_DIR
fi

# esbuild가 알아서 로컬 또는 지정된 경로로 빌드합니다.
npm run build