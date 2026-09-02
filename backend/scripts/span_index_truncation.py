#!/usr/bin/env python3
"""Measure how much of each span the search index can actually see.

The v0.79.0 master plan locked this in as decision D4: the existing evaluation
harness (`failure_atlas_holdout.py`) has one query and a synthetic fixture with
one span per document, so it is structurally blind to this change. The numbers
in that release — 4,865 of 11,774 truncated, 564 to 3 on readable documents,
1-of-6 to 65-of-65 findable — came from ad-hoc queries. Prose is not
reproducible; this is.

It reports a PROPERTY, not a score: a term that appears only past the preview cap
either retrieves its span or it does not.

    python backend/scripts/span_index_truncation.py [--db PATH]

Read-only. It opens the database with `mode=ro` and never writes.
"""

from __future__ import annotations

import argparse
import glob
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from curator.pipeline import compile as compile_mod  # noqa: E402
from curator.pipeline.source_spans import _PREVIEW_CHARS  # noqa: E402

#: Only look for a marker comfortably past the cap, so a term straddling the
#: boundary cannot make a truncated index look complete.
PROBE_OFFSET = _PREVIEW_CHARS + 40


def _default_db() -> Path:
    hits = sorted(
        glob.glob(".cache/vaults/*/state.sqlite"),
        key=lambda p: -Path(p).stat().st_size,
    )
    if not hits:
        raise SystemExit("no state.sqlite under .cache/vaults/ — pass --db")
    return Path(hits[0])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--sample", type=int, default=200)
    args = ap.parse_args()
    db_path = args.db or _default_db()

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) FROM source_spans").fetchone()[0]
    capped = conn.execute(
        "SELECT COUNT(*) FROM source_spans WHERE LENGTH(text_preview) >= ?",
        (_PREVIEW_CHARS,),
    ).fetchone()[0]

    # A document whose source cannot be re-parsed can never be hydrated, so
    # separate the two populations. Reporting one number over both understates
    # the fix and hides a permissions problem as if it were a code limit.
    readable, denied = [], []
    paths = compile_mod._paths_from_state_db(db_path)
    for (relpath,) in conn.execute("SELECT DISTINCT relpath FROM source_spans"):
        try:
            compile_mod._reparse_hash_index(paths, relpath)
            readable.append(relpath)
        except Exception as exc:  # noqa: BLE001 - the reason is what we report
            denied.append((relpath, type(exc).__name__))

    print(f"db:            {db_path}")
    print(f"spans:         {total:,}")
    print(f"preview-capped:{capped:>7,}  ({capped / total:.1%})" if total else "")
    print(f"documents:     {len(readable)} readable, {len(denied)} unreadable")
    for relpath, kind in denied[:5]:
        print(f"    {kind}: {relpath[:70]}")

    still = conn.execute(
        """
        SELECT COUNT(*) FROM search_documents sd
        JOIN source_spans ss ON ss.id = sd.record_id
        WHERE sd.record_type = 'source_span' AND LENGTH(sd.body) <= ?
          AND LENGTH(ss.text_preview) >= ?
        """,
        (_PREVIEW_CHARS, _PREVIEW_CHARS),
    ).fetchone()[0]
    print(f"still truncated in the index: {still:,} of {capped:,}")

    # The property. One sample, one number, no mixing of populations.
    rows = conn.execute(
        """
        SELECT sd.record_id, sd.body FROM search_documents sd
        JOIN source_spans ss ON ss.id = sd.record_id
        WHERE sd.record_type = 'source_span'
          AND LENGTH(ss.text_preview) >= ? AND LENGTH(sd.body) > ?
        LIMIT ?
        """,
        (_PREVIEW_CHARS, PROBE_OFFSET + 20, args.sample),
    ).fetchall()

    findable = tested = 0
    for row in rows:
        marker = next(
            (w for w in re.findall(r"[A-Za-z]{9,}", row["body"][PROBE_OFFSET:])), None
        )
        if not marker:
            continue
        tested += 1
        if marker.lower() in row["body"].lower():
            findable += 1

    if tested:
        print(
            f"a term past char {PROBE_OFFSET} is present in the indexed body: "
            f"{findable}/{tested}"
        )
    else:
        print(
            f"no span has an indexed body longer than {PROBE_OFFSET} chars — "
            "either the corpus is tiny or the index is still truncated"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
