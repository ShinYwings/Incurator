"""Hatchling build hook: auto-install local runtime helpers after pip install."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from hatchling.builders.hooks.plugin.interface import BuildHookInterface
except ImportError:
    class BuildHookInterface:
        pass


def _repo_root(root: str | Path | None = None) -> Path:
    if root is not None:
        resolved = Path(root).resolve()
        if resolved.name == "backend":
            return resolved.parent
        return resolved
    return Path(__file__).resolve().parents[2]


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        _install_ollama()
        _install_node()
        _install_agy()
        _install_codex()


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

def _install_ollama() -> None:
    if shutil.which("ollama"):
        print("[incurator] Ollama already available.", flush=True)
        return

    print("[incurator] Ollama not found - installing...", flush=True)

    if sys.platform.startswith("linux"):
        result = subprocess.run(
            "curl -fsSL https://ollama.com/install.sh | sh",
            shell=True, check=False,
        )
        if result.returncode == 0:
            print("[incurator] Ollama installed.", flush=True)
        else:
            print("[incurator] Ollama install failed. Try manually: https://ollama.com/download", flush=True)

    elif sys.platform == "darwin":
        if shutil.which("brew"):
            result = subprocess.run(["brew", "install", "ollama"], check=False)
            if result.returncode == 0:
                print("[incurator] Ollama installed via Homebrew.", flush=True)
            else:
                print("[incurator] brew install failed. Download from: https://ollama.com/download", flush=True)
        else:
            print("[incurator] Install Ollama from: https://ollama.com/download", flush=True)

    else:
        print("[incurator] Install Ollama from: https://ollama.com/download", flush=True)


# ---------------------------------------------------------------------------
# Node.js >= 22 (required by plugin and CLI helper tooling)
# ---------------------------------------------------------------------------

def _node_version() -> tuple[int, int] | None:
    """Return (major, minor) of the current node, or None if not found."""
    node = shutil.which("node")
    if not node:
        node_bin = _get_nvm_node_bin()
        if node_bin:
            node = str(Path(node_bin) / "node")
    if not node:
        return None
    try:
        out = subprocess.run(
            [node, "--version"], capture_output=True, text=True, timeout=5
        ).stdout.strip().lstrip("v")
        parts = out.split(".")
        return int(parts[0]), int(parts[1])
    except Exception:
        return None


def _get_nvm_node_bin() -> str | None:
    node_base = Path.home() / ".nvm" / "versions" / "node"
    if node_base.exists():
        for d in sorted(node_base.iterdir(), reverse=True):
            if d.is_dir() and (d / "bin" / "node").exists():
                return str(d / "bin")
    return None


def _install_node() -> None:
    ver = _node_version()
    if ver and ver[0] >= 22:
        bin_dir = _get_nvm_node_bin() or str(Path(shutil.which("node")).parent)
        _prepend_path(bin_dir)
        print(f"[incurator] Node.js v{ver[0]}.{ver[1]} already available.", flush=True)
        return

    nvm_sh = Path.home() / ".nvm" / "nvm.sh"
    if not nvm_sh.exists():
        print("[incurator] NVM not found - installing...", flush=True)
        subprocess.run(
            "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash",
            shell=True, check=False,
        )

    bin_dir = _get_nvm_node_bin()
    if not bin_dir:
        print("[incurator] Installing Node.js LTS via NVM...", flush=True)
        if nvm_sh.exists():
            subprocess.run(
                f"bash -c 'source {nvm_sh} && nvm install --lts'",
                shell=True, check=False,
            )
        bin_dir = _get_nvm_node_bin()

    if bin_dir:
        _prepend_path(bin_dir)
        print(f"[incurator] Node.js ready: {bin_dir}", flush=True)
    else:
        print("[incurator] Node.js setup failed. Install manually: https://nodejs.org", flush=True)


# ---------------------------------------------------------------------------
# Antigravity CLI (agy) - Official Google CLI
# ---------------------------------------------------------------------------

def _install_agy() -> None:
    home_local_bin = Path.home() / ".local" / "bin"
    if shutil.which("agy") or (home_local_bin / "agy").exists() or (home_local_bin / "agy.exe").exists():
        print("[incurator] ✅ Antigravity CLI (agy) already available.", flush=True)
        return

    print("[incurator] ⏳ Installing Antigravity CLI (agy)...", flush=True)
    if sys.platform == "win32":
        res = subprocess.run(
            'powershell -c "irm https://antigravity.google/cli/install.ps1 | iex"',
            shell=True, check=False
        )
    else:
        res = subprocess.run(
            "curl -fsSL https://antigravity.google/cli/install.sh | bash",
            shell=True, check=False
        )

    if res.returncode == 0:
        print("[incurator] ✅ Antigravity CLI installed.", flush=True)
    else:
        print("[incurator] ❌ Antigravity CLI install failed. Try manually from https://antigravity.google/product/antigravity-cli", flush=True)


# ---------------------------------------------------------------------------
# Codex CLI - OpenAI CLI
# ---------------------------------------------------------------------------

def _install_codex() -> None:
    if shutil.which("codex"):
        print("[incurator] ✅ Codex CLI already available.", flush=True)
        return

    npm = shutil.which("npm")
    if not npm:
        print("[incurator] npm not found - skipping Codex CLI install.", flush=True)
        return

    print("[incurator] ⏳ Installing Codex CLI via npm...", flush=True)
    res = subprocess.run([npm, "install", "-g", "@openai/codex"], check=False)
    if res.returncode == 0:
        print("[incurator] ✅ Codex CLI installed.", flush=True)
    else:
        print("[incurator] ❌ Codex CLI install failed. Try manually: npm install -g @openai/codex", flush=True)


def _prepend_path(bin_dir: str) -> None:
    existing = os.environ.get("PATH", "")
    if bin_dir not in existing.split(os.pathsep):
        os.environ["PATH"] = bin_dir + os.pathsep + existing


if __name__ == "__main__":
    _install_ollama()
    _install_node()
    _install_agy()
    _install_codex()
