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


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        _install_ollama()
        _install_node()
        _build_qmd(Path(self.root) / "src" / "qmd")


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

def _install_ollama() -> None:
    if shutil.which("ollama"):
        print("[llm-wiki] Ollama already available.", flush=True)
        return

    print("[llm-wiki] Ollama not found — installing…", flush=True)

    if sys.platform.startswith("linux"):
        result = subprocess.run(
            "curl -fsSL https://ollama.com/install.sh | sh",
            shell=True,
        )
        if result.returncode == 0:
            print("[llm-wiki] Ollama installed.", flush=True)
        else:
            print("[llm-wiki] Ollama install failed. Try manually: https://ollama.com/download", flush=True)

    elif sys.platform == "darwin":
        if shutil.which("brew"):
            result = subprocess.run(["brew", "install", "ollama"], check=False)
            if result.returncode == 0:
                print("[llm-wiki] Ollama installed via Homebrew.", flush=True)
            else:
                print("[llm-wiki] brew install failed. Download from: https://ollama.com/download", flush=True)
        else:
            print("[llm-wiki] Install Ollama from: https://ollama.com/download", flush=True)

    else:
        print("[llm-wiki] Install Ollama from: https://ollama.com/download", flush=True)


# ---------------------------------------------------------------------------
# Node.js / npm  (via nodeenv, installed into the Python venv)
# ---------------------------------------------------------------------------

def _install_node() -> None:
    if shutil.which("npm"):
        print("[llm-wiki] npm already available.", flush=True)
        return  # system npm already present

    node_dir = Path(sys.prefix) / "node"
    npm_bin = node_dir / "bin" / "npm"

    if npm_bin.exists():
        _prepend_path(str(node_dir / "bin"))
        print("[llm-wiki] npm already available (via nodeenv).", flush=True)
        return  # already installed in venv

    try:
        import nodeenv  # noqa: F401
    except ImportError:
        print("[llm-wiki] nodeenv not found — skipping Node.js setup.", flush=True)
        return

    print(f"[llm-wiki] Installing Node.js into venv ({node_dir})…", flush=True)
    result = subprocess.run(
        [sys.executable, "-m", "nodeenv", "--prebuilt", str(node_dir)],
        check=False,
    )
    if result.returncode == 0:
        _prepend_path(str(node_dir / "bin"))
        print("[llm-wiki] Node.js ready.", flush=True)
    else:
        print("[llm-wiki] nodeenv failed — install Node.js manually: https://nodejs.org", flush=True)


# ---------------------------------------------------------------------------
# qmd search engine  (bundled TypeScript — built with npm)
# ---------------------------------------------------------------------------

def _build_qmd(qmd_dir: Path) -> None:
    dist_bin = qmd_dir / "dist" / "cli" / "qmd.js"
    if dist_bin.exists():
        print("[llm-wiki] qmd search engine already built.", flush=True)
        return  # already built

    if not qmd_dir.exists():
        print("[llm-wiki] src/qmd not found — skipping qmd build.", flush=True)
        return

    npm = shutil.which("npm")
    if not npm:
        # Try the nodeenv-installed npm
        node_bin = Path(sys.prefix) / "node" / "bin" / "npm"
        npm = str(node_bin) if node_bin.exists() else None

    if not npm:
        print("[llm-wiki] npm not available — skipping qmd build.", flush=True)
        return

    print(f"[llm-wiki] Building qmd ({qmd_dir})…", flush=True)

    res = subprocess.run([npm, "install"], cwd=str(qmd_dir), check=False)
    if res.returncode != 0:
        print("[llm-wiki] qmd: npm install failed.", flush=True)
        return

    res = subprocess.run([npm, "run", "build"], cwd=str(qmd_dir), check=False)
    if res.returncode == 0:
        print("[llm-wiki] qmd built successfully.", flush=True)
    else:
        print("[llm-wiki] qmd: npm run build failed.", flush=True)


def _prepend_path(bin_dir: str) -> None:
    existing = os.environ.get("PATH", "")
    if bin_dir not in existing.split(os.pathsep):
        os.environ["PATH"] = bin_dir + os.pathsep + existing


if __name__ == "__main__":
    _install_ollama()
    _install_node()
    _build_qmd(Path(__file__).resolve().parent / "src" / "qmd")
