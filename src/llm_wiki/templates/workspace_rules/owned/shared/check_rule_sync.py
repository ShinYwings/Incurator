#!/usr/bin/env python3
"""Check llm-wiki managed rule blocks for this workspace."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SHARED = ".agents/llm_wiki/shared/rules.md"
REQUIRED = [
    SHARED,
    "Do not use cross-workspace paths",
    "Restrict knowledge extraction, graph search, and insertion commands",
]


def main() -> int:
    errors: list[str] = []
    shared_path = ROOT / SHARED
    if not shared_path.is_file():
        errors.append(f"missing {SHARED}")
    else:
        text = shared_path.read_text(encoding="utf-8")
        for marker in REQUIRED[1:]:
            if marker not in text:
                errors.append(f"{SHARED} missing marker: {marker}")

    if errors:
        print("llm-wiki rule sync check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("llm-wiki rule sync check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
