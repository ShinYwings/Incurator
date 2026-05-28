#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

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
echo "=== Installation complete ==="
