"""InCurator: An AI-maintained personal knowledge base."""

__version__ = "0.1.0"

import os
import sys
from pathlib import Path

# Prioritize Node installed via NVM
_nvm_dir = Path.home() / ".nvm" / "versions" / "node"
if _nvm_dir.exists():
    for _d in sorted(_nvm_dir.iterdir(), reverse=True):
        if _d.is_dir() and (_d / "bin").exists():
            _bin_dir = str(_d / "bin")
            if _bin_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = _bin_dir + os.pathsep + os.environ.get("PATH", "")
            break
