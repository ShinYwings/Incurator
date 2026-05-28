"""Hatchling build hook: auto-install Ollama and Node.js after pip install."""

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
    """Resolve the repository root for Hatch and direct script execution."""
    if root is not None:
        resolved = Path(root).resolve()
        if resolved.name == "backend":
            return resolved.parent
        return resolved
    return Path(__file__).resolve().parents[2]


def _qmd_dir(root: str | Path | None = None) -> Path:
    repo = _repo_root(root)
    candidate = repo / "backend" / "src" / "qmd"
    if candidate.exists():
        return candidate
    return repo / "src" / "qmd"


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        _install_ollama()
        _install_node()
        _build_qmd(_qmd_dir(self.root))


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
            shell=True,
            check=False,
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
# Node.js / npm  (via NVM, installed into the user's home directory)
# ---------------------------------------------------------------------------

def _get_nvm_npm() -> str | None:
    nvm_dir = Path.home() / ".nvm"
    node_base = nvm_dir / "versions" / "node"
    if node_base.exists():
        for d in sorted(node_base.iterdir(), reverse=True):
            if d.is_dir() and (d / "bin" / "npm").exists():
                return str(d / "bin" / "npm")

    npm_on_path = shutil.which("npm")
    if npm_on_path:
        return npm_on_path

    return None


def _install_node() -> None:
    nvm_dir = Path.home() / ".nvm"
    nvm_sh = nvm_dir / "nvm.sh"

    if not nvm_sh.exists():
        print("[incurator] NVM not found - installing...", flush=True)
        try:
            subprocess.run(
                "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash",
                shell=True, check=False,
            )
        except Exception:
            pass

    npm = _get_nvm_npm()
    if not npm:
        print("[incurator] No Node installed via NVM - installing Node LTS...", flush=True)
        if nvm_sh.exists():
            subprocess.run(
                f"bash -c 'source {nvm_sh} && nvm install --lts'",
                shell=True, check=False,
            )
        npm = _get_nvm_npm()

    if npm:
        bin_dir = str(Path(npm).parent)
        _prepend_path(bin_dir)
        print(f"[incurator] Node from NVM ready: {bin_dir}", flush=True)
    else:
        print("[incurator] NVM setup failed. Install Node.js manually: https://nodejs.org", flush=True)


# ---------------------------------------------------------------------------
# qmd search engine  (bundled TypeScript - built with npm)
# ---------------------------------------------------------------------------

def _build_qmd(qmd_dir: Path) -> None:
    dist_bin = qmd_dir / "dist" / "cli" / "qmd.js"
    if dist_bin.exists():
        print("[incurator] qmd search engine already built.", flush=True)
        return

    if not qmd_dir.exists():
        print("[incurator] bundled qmd source not found - skipping qmd build.", flush=True)
        return

    npm = _get_nvm_npm()
    if not npm:
        print("[incurator] npm not available - skipping qmd build.", flush=True)
        return

    print(f"[incurator] Building qmd ({qmd_dir})...", flush=True)

    res = subprocess.run([npm, "install"], cwd=str(qmd_dir), check=False)
    if res.returncode != 0:
        print("[incurator] qmd: npm install failed.", flush=True)
        return

    res = subprocess.run([npm, "run", "build"], cwd=str(qmd_dir), check=False)
    if res.returncode == 0:
        print("[incurator] qmd built successfully.", flush=True)
    else:
        print("[incurator] qmd: npm run build failed.", flush=True)


def _prepend_path(bin_dir: str) -> None:
    existing = os.environ.get("PATH", "")
    if bin_dir not in existing.split(os.pathsep):
        os.environ["PATH"] = bin_dir + os.pathsep + existing


if __name__ == "__main__":
    _install_ollama()
    _install_node()
    _build_qmd(_qmd_dir())
