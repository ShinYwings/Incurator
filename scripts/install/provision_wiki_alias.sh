#!/usr/bin/env bash
# Provision a `wiki` alias pointing at THIS repository's runtime venv launcher.
#
# Why this exists: before v0.42.0 setup.sh provisioned no entry point at all, so
# users hand-rolled one. A hand-rolled alias carried between machines is how a
# macOS install ended up with `VIRTUAL_ENV=/home/<user>/…` — a path that cannot
# exist on macOS — which silently degraded `wiki` to whatever else was on PATH
# (a stale Anaconda editable install reporting an ancient version while running
# current code).
#
# Contract:
#   * the alias target is derived from the repo root passed in, never hardcoded;
#   * re-running REPLACES the previous Incurator block instead of appending a
#     duplicate, so a wrong alias self-heals on the next setup;
#   * zsh and bash rc files are both handled;
#   * a different `wiki` earlier on PATH is reported loudly rather than lost to.
#
# Usage: provision_wiki_alias.sh <repo-root> [rc-file ...]
#        With no rc files, the user's ~/.zshrc and ~/.bashrc are used (only
#        those that already exist).
set -euo pipefail

BEGIN_MARK="# >>> Added by Incurator >>>"
END_MARK="# <<< Added by Incurator <<<"
LEGACY_MARK="# Added by Incurator"

repo_root="${1:-}"
if [ -z "$repo_root" ]; then
    echo "provision_wiki_alias.sh: repo root is required" >&2
    exit 2
fi
# Normalize so the written alias never contains a relative or trailing-slash path.
repo_root="$(cd "$repo_root" && pwd)"
wiki_bin="$repo_root/.venv/bin/wiki"
shift || true

rc_files=("$@")
if [ ${#rc_files[@]} -eq 0 ]; then
    for candidate in "$HOME/.zshrc" "$HOME/.bashrc"; do
        [ -f "$candidate" ] && rc_files+=("$candidate")
    done
fi

if [ ${#rc_files[@]} -eq 0 ]; then
    echo "ℹ️  No ~/.zshrc or ~/.bashrc found — skipping alias provisioning."
    echo "    Run the backend directly with: $wiki_bin"
    exit 0
fi

# Strip every previous Incurator block: the delimited form written by this
# script AND the legacy single-comment form ("# Added by Incurator" followed by
# an alias line), which is what earlier hand-rolled setups left behind.
strip_previous() {
    awk -v begin_mark="$BEGIN_MARK" -v end_mark="$END_MARK" -v legacy="$LEGACY_MARK" '
        # Delimited block: skip until the closing marker.
        index($0, begin_mark) == 1 { in_block = 1; next }
        in_block { if (index($0, end_mark) == 1) in_block = 0; next }
        # Legacy form: drop the comment and any immediately following alias line.
        index($0, legacy) == 1 { drop_next_alias = 1; next }
        drop_next_alias && $0 ~ /^[[:space:]]*alias[[:space:]]+wiki=/ { drop_next_alias = 0; next }
        { drop_next_alias = 0; print }
    ' "$1"
}

for rc in "${rc_files[@]}"; do
    [ -f "$rc" ] || continue
    tmp="$(mktemp "${TMPDIR:-/tmp}/incurator-rc.XXXXXX")"
    strip_previous "$rc" > "$tmp"

    # Drop trailing blank lines the strip may have left, then append one block.
    printf '%s\n' "$(cat "$tmp")" > "$tmp.trimmed"
    {
        cat "$tmp.trimmed"
        echo ""
        echo "$BEGIN_MARK"
        echo "alias wiki=\"$wiki_bin\""
        echo "$END_MARK"
    } > "$tmp"
    rm -f "$tmp.trimmed"

    # Preserve the original mode, and replace atomically so an interrupted run
    # cannot leave a half-written shell rc (which would break the user's shell).
    if command -v stat >/dev/null 2>&1; then
        mode="$(stat -f '%Lp' "$rc" 2>/dev/null || stat -c '%a' "$rc" 2>/dev/null || echo "")"
        [ -n "$mode" ] && chmod "$mode" "$tmp" 2>/dev/null || true
    fi
    mv "$tmp" "$rc"
    echo "✓ wiki alias provisioned in $rc -> $wiki_bin"
done

# PATH conflict: an entry earlier on PATH still wins for non-interactive shells
# and for anything that resolves the bare name itself, so say so explicitly.
# INCURATOR_ORIGINAL_PATH lets setup.sh pass the PATH from before it prepended
# its own venv, which would otherwise mask exactly the conflict we are hunting.
scan_path="${INCURATOR_ORIGINAL_PATH:-$PATH}"
other="$(PATH="$scan_path" command -v wiki 2>/dev/null || true)"
if [ -n "$other" ] && [ "$other" != "$wiki_bin" ]; then
    echo ""
    echo "⚠️  ANOTHER 'wiki' IS EARLIER ON YOUR PATH:"
    echo "      $other"
    echo "    This repository's launcher is:"
    echo "      $wiki_bin"
    echo "    The new alias fixes interactive shells, but anything that resolves"
    echo "    the bare name 'wiki' from PATH — scripts, non-interactive shells —"
    echo "    still gets the other one. Note that an editable install keeps running"
    echo "    current repo code while reporting the version it was installed at, so"
    echo "    a stale version string there does NOT mean stale behavior."
    echo "    Remove it, or put $repo_root/.venv/bin first on PATH."
fi
