#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Setting up Python Virtual Environment ==="
# Capture PATH *before* prepending our own venv, so the alias step can still see
# a competing `wiki` that would otherwise be masked by the line below.
export INCURATOR_ORIGINAL_PATH="$PATH"
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
    # Apply semver-compatible security fixes to plugin/package-lock.json on every
    # setup, so a known-vulnerable transitive dep never quietly rides along in a
    # build. NEVER `--force`: that pulls breaking major bumps in unreviewed.
    #
    # Both `|| true` guards are load-bearing under `set -euo pipefail`:
    # `npm audit fix` exits non-zero when advisories remain that it cannot fix
    # semver-compatibly, and `npm audit` exits non-zero whenever any advisory is
    # open at all. Neither is a reason to abort a developer's setup — an upstream
    # advisory with no published fix is not something this run can act on.
    echo "--- Applying semver-compatible npm security fixes ---"
    npm audit fix || true
    if npm audit >/dev/null 2>&1; then
        echo "✓ npm audit: 0 vulnerabilities."
    else
        echo "⚠️  npm audit still reports unfixed advisories."
        echo "    Run 'cd plugin && npm audit' for detail; a major-version bump"
        echo "    needs a real review, so it is deliberately not applied here."
    fi
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
            echo "⚠️  RELOAD REQUIRED: Obsidian is still running the previous Incurator bundle until you reload the app."
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
# `[mcp]` is a RUNTIME feature, not a dev tool: it is how the Obsidian plugin's
# chat and external agents reach the knowledge base at all. Leaving it out made
# `wiki mcp install` fail on a fresh setup with "The `mcp` package is required",
# and the sidechat silently had no curator tools to call. Dev-only check tools
# still belong in .venv-dev, never here.
#
# --python pins the target interpreter to the repo-root venv so nothing is ever
# installed into an ambient environment. Nothing is created under backend/
# because this is `uv pip install` (the pip-compatible interface) rather than
# `uv add`/`uv sync`/`uv lock` — those are the project commands that would write
# a backend/uv.lock and a backend/.venv. The absolute path is for robustness
# against the caller's cwd, not the reason no lockfile appears.
if command -v uv &> /dev/null; then
    uv pip install --python "$VIRTUAL_ENV/bin/python" -e "$ROOT_DIR/backend[mcp]"
else
    pip install -e "$ROOT_DIR/backend[mcp]"
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
echo "=== Provisioning the 'wiki' shell alias ==="
# Idempotent: re-running replaces the previous Incurator block rather than
# appending, so a wrong alias (e.g. one carried over from another machine)
# self-heals here. Skip with INCURATOR_SKIP_ALIAS=1.
if [ "${INCURATOR_SKIP_ALIAS:-0}" != "1" ]; then
    bash "$ROOT_DIR/scripts/install/provision_wiki_alias.sh" "$ROOT_DIR" \
        || echo "⚠️  Alias provisioning degraded — run the backend directly: $ROOT_DIR/.venv/bin/wiki"
else
    echo "ℹ️  INCURATOR_SKIP_ALIAS=1 set — skipping. Backend launcher: $ROOT_DIR/.venv/bin/wiki"
fi

echo ""
echo "=== Setup complete ==="
