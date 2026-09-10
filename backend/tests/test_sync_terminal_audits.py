"""Terminal source audit rows remain portable after their source is removed."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from curator import db
from curator.db_sync import export_knowledge, import_knowledge

STAMP = "2026-08-01T00:00:00Z"


def _source() -> dict:
    return {
        "id": 32, "relpath": "unrelated.md", "sync_key": "vault:unrelated.md",
        "content_hash": "hash", "file_type": "md", "bytes": 1,
        "added_at": STAMP, "updated_at": STAMP,
    }


def _audit(table: str, *, terminal: bool = True) -> dict:
    if table == "knowledge_units":
        return {
            "id": "KNU-audit", "unit_type": "claim", "canonical_name": "claim",
            "statement": "Retained historical evidence", "source_span_ids": '["SPAN-gone"]',
            "source_id": 32, "retired_at": STAMP if terminal else None,
            "created_at": STAMP, "updated_at": STAMP,
        }
    return {
        "id": "GEN-audit", "source_id": 32,
        "status": "discarded" if terminal else "authoritative",
        "discarded_at": STAMP if terminal else None,
        "prompt_contract_version": "compile.v2", "audit_json": '{"unit_ids":["KNU-audit"]}',
        "created_at": STAMP, "updated_at": STAMP,
    }


def _write(path: Path, rows: list[tuple[str, dict]]) -> None:
    records = [{"type": "header", "schema_version": db.SCHEMA_VERSION, "export_id": "audit-export"}]
    records.extend({"type": "row", "table": table, "row": row} for table, row in rows)
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n")


@pytest.mark.parametrize("table", ["knowledge_units", "compiler_generations"])
def test_historical_terminal_orphan_preserves_audit_without_local_id_alias(
    tmp_path: Path, table: str,
) -> None:
    target = tmp_path / "target.sqlite"
    db.init_db(target)
    local_source = _source()
    with db.connect(target) as conn:
        conn.execute(
            f"INSERT INTO sources ({','.join(local_source)}) "
            f"VALUES ({','.join('?' for _ in local_source)})",
            tuple(local_source.values()),
        )
        assert conn.execute("SELECT id FROM sources").fetchone()[0] == 32
    row = _audit(table)
    peer = tmp_path / "peer.jsonl"
    _write(peer, [(table, row)])
    original = peer.read_bytes()
    stats = import_knowledge(target, peer)
    assert stats.inserted == 1 and stats.rejected == 0
    assert peer.read_bytes() == original
    with db.connect(target) as conn:
        stored = dict(conn.execute(f"SELECT * FROM {table}").fetchone())
        for name, value in row.items():
            assert stored[name] == (None if name == "source_id" else value)
        assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 1
    repeated = import_knowledge(target, peer)
    assert repeated.inserted == repeated.updated == 0


@pytest.mark.parametrize("table", ["knowledge_units", "compiler_generations"])
@pytest.mark.parametrize("invalid_kind", ["active", "invalid_stamp", "parent_later"])
def test_unresolved_nonterminal_or_misordered_parent_fails_atomically(
    tmp_path: Path, table: str, invalid_kind: str,
) -> None:
    target = tmp_path / "target.sqlite"
    db.init_db(target)
    row = _audit(table, terminal=invalid_kind != "active")
    if invalid_kind == "invalid_stamp":
        row["retired_at" if table == "knowledge_units" else "discarded_at"] = "broken"
    first = _source()
    first["id"] = 1
    first["relpath"] = "first.md"
    first["sync_key"] = "vault:first.md"
    rows = [("sources", first), (table, row)]
    if invalid_kind == "parent_later":
        rows.append(("sources", _source()))
    peer = tmp_path / "peer.jsonl"
    _write(peer, rows)
    with pytest.raises(ValueError, match="unmapped source_id"):
        import_knowledge(target, peer)
    with db.connect(target) as conn:
        assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


@pytest.mark.parametrize("table", ["knowledge_units", "compiler_generations"])
def test_export_terminal_detachment_is_read_only_and_uses_full_source_table(
    tmp_path: Path, table: str,
) -> None:
    source = tmp_path / "source.sqlite"
    db.init_db(source)
    row = _audit(table)
    with db.connect(source) as conn:
        conn.execute(
            f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
            tuple(row.values()),
        )
    exported = tmp_path / "out.jsonl"
    export_knowledge(source, exported)
    records = [json.loads(line) for line in exported.read_text().splitlines()]
    transported = next(record["row"] for record in records if record.get("table") == table)
    assert transported["source_id"] is None
    with db.connect(source) as conn:
        assert conn.execute(f"SELECT source_id FROM {table}").fetchone()[0] == 32
        parent = _source()
        conn.execute(
            f"INSERT INTO sources ({','.join(parent)}) VALUES ({','.join('?' for _ in parent)})",
            tuple(parent.values()),
        )
        conn.execute(f"UPDATE {table} SET updated_at = '2026-09-01T00:00:00Z'")
    export_knowledge(source, exported, since="2026-08-15T00:00:00Z")
    records = [json.loads(line) for line in exported.read_text().splitlines()]
    assert not any(record.get("table") == "sources" for record in records)
    transported = next(record["row"] for record in records if record.get("table") == table)
    assert transported["source_id"] == 32
