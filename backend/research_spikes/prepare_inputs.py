"""Create mutation-guarded local SQLite copies for Plan E scale research."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from contracts import sha256_file, sqlite_readonly_summary, write_json


def copy_sqlite_snapshot(source: Path, destination: Path) -> dict:
    source = source.resolve()
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    before = sha256_file(source)
    source_uri = f"{source.as_uri()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    after = sha256_file(source)
    if before != after:
        destination.unlink(missing_ok=True)
        raise RuntimeError("source database changed while snapshot was being copied")
    summary = sqlite_readonly_summary(destination)
    summary.update(
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_path": str(source),
            "source_sha256_before": before,
            "source_sha256_after": after,
        }
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()

    local = Path(__file__).resolve().parent / "local"
    destination = local / "snapshots" / f"{args.label}.sqlite"
    summary = copy_sqlite_snapshot(args.source, destination)
    write_json(local / "manifests" / f"{args.label}.json", summary)
    print(destination)


if __name__ == "__main__":
    main()
