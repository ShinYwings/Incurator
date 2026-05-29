from __future__ import annotations

import sqlite3
from pathlib import Path

from curator.zotero_integration import search_zotero_items


def _make_zotero_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE itemTypes (itemTypeID INTEGER PRIMARY KEY, typeName TEXT);
        CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT, itemTypeID INTEGER, dateModified TEXT);
        CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT);
        CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT);
        CREATE TABLE itemData (itemID INTEGER, fieldID INTEGER, valueID INTEGER);
        CREATE TABLE creators (creatorID INTEGER PRIMARY KEY, firstName TEXT, lastName TEXT);
        CREATE TABLE itemCreators (itemID INTEGER, creatorID INTEGER, orderIndex INTEGER);
        INSERT INTO itemTypes VALUES (2, 'journalArticle');
        INSERT INTO fields VALUES (1, 'title'), (2, 'date');
        """
    )
    rows = [
        (1, "OLDKEY", "Old Paper", "2024-01-01 00:00:00", "2020"),
        (2, "NEWKEY", "Recently Modified Paper", "2026-05-01 00:00:00", "2026"),
    ]
    for item_id, key, title, modified, date in rows:
        cur.execute("INSERT INTO items VALUES (?, ?, 2, ?)", (item_id, key, modified))
        cur.execute("INSERT INTO itemDataValues VALUES (?, ?)", (item_id * 10, title))
        cur.execute("INSERT INTO itemData VALUES (?, 1, ?)", (item_id, item_id * 10))
        cur.execute("INSERT INTO itemDataValues VALUES (?, ?)", (item_id * 10 + 1, date))
        cur.execute("INSERT INTO itemData VALUES (?, 2, ?)", (item_id, item_id * 10 + 1))
    conn.commit()
    conn.close()


def test_blank_zotero_search_returns_recent_modified_items(tmp_path: Path) -> None:
    db_path = tmp_path / "zotero.sqlite"
    _make_zotero_db(db_path)

    items = search_zotero_items(str(db_path), "")

    assert [item["key"] for item in items] == ["NEWKEY", "OLDKEY"]


def test_zotero_search_still_filters_by_query(tmp_path: Path) -> None:
    db_path = tmp_path / "zotero.sqlite"
    _make_zotero_db(db_path)

    items = search_zotero_items(str(db_path), "old")

    assert [item["key"] for item in items] == ["OLDKEY"]
