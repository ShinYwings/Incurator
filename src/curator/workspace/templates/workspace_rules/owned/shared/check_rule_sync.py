#!/usr/bin/env python3
"""Check that runtime rule files point back to shared incurator rules."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
REQUIRED = ".agents/curator/shared/rules.md"


def main() -> None:
    runtime_dir = ROOT / ".agents" / "curator" / "runtime"
    missing: list[Path] = []
    for path in sorted(runtime_dir.glob("*.md")):
        if REQUIRED not in path.read_text(encoding="utf-8", errors="replace"):
            missing.append(path)
    if missing:
        names = ", ".join(str(path.relative_to(ROOT)) for path in missing)
        raise SystemExit(f"Runtime rules missing shared-rule pointer: {names}")
    print("incurator workspace rules are synchronized")


if __name__ == "__main__":
    main()

