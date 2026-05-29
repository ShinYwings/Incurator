import sqlite3
import shutil
import json
import tempfile
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from .zotero import get_zotero_annotations

def search_zotero_items(zotero_db_path: str, query: str, limit: int = 20) -> List[Dict[str, Any]]:
    db_path = Path(zotero_db_path).expanduser()
    if not db_path.exists():
        return []

    temp_db_path = Path(tempfile.gettempdir()) / f"zotero_search_{os.getpid()}_{abs(hash(str(db_path)))}.sqlite"
    try:
        shutil.copy2(db_path, temp_db_path)
    except Exception:
        temp_db_path = db_path

    try:
        conn = sqlite3.connect(temp_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        term = (query or "").strip()
        if term:
            item_filter = """
              AND i.itemID IN (
                  SELECT iD2.itemID
                  FROM itemData iD2
                  JOIN itemDataValues idV2 ON iD2.valueID = idV2.valueID
                  WHERE idV2.value LIKE ?

                  UNION

                  SELECT ic.itemID
                  FROM itemCreators ic
                  JOIN creators c ON ic.creatorID = c.creatorID
                  WHERE c.firstName LIKE ? OR c.lastName LIKE ?
              )
            """
            params = (f"%{term}%", f"%{term}%", f"%{term}%", max(1, min(int(limit), 100)))
        else:
            item_filter = ""
            params = (max(1, min(int(limit), 100)),)

        cur.execute(f"""
            SELECT i.key, i.itemID, idV.value as title, it.typeName as itemType
            FROM items i
            JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
            JOIN itemData iD ON i.itemID = iD.itemID
            JOIN itemDataValues idV ON iD.valueID = idV.valueID
            JOIN fields f ON iD.fieldID = f.fieldID
            WHERE f.fieldName = 'title'
              AND i.itemTypeID NOT IN (1, 14) -- Exclude note and attachment
              {item_filter}
            ORDER BY i.dateModified DESC
            LIMIT ?
        """, params)

        results = []
        for row in cur.fetchall():
            r = dict(row)

            # Get creators
            cur.execute("""
                SELECT c.firstName, c.lastName
                FROM itemCreators ic
                JOIN creators c ON ic.creatorID = c.creatorID
                WHERE ic.itemID = ?
                ORDER BY ic.orderIndex
            """, (r['itemID'],))
            creators = [dict(c) for c in cur.fetchall()]

            # Get date
            cur.execute("""
                SELECT idV.value
                FROM itemData iD
                JOIN itemDataValues idV ON iD.valueID = idV.valueID
                JOIN fields f ON iD.fieldID = f.fieldID
                WHERE iD.itemID = ? AND f.fieldName = 'date'
            """, (r['itemID'],))
            date_row = cur.fetchone()

            results.append({
                "key": r['key'],
                "title": r['title'],
                "itemType": r['itemType'],
                "creators": creators,
                "date": date_row['value'] if date_row else ""
            })

    finally:
        if 'conn' in locals() and conn:
            conn.close()
        if temp_db_path != db_path and temp_db_path.exists():
            temp_db_path.unlink(missing_ok=True)

    return results

_BIBTEX_TYPE_MAP = {
    "journalArticle": "article",
    "conferencePaper": "inproceedings",
    "book": "book",
    "bookSection": "incollection",
    "thesis": "phdthesis",
    "report": "techreport",
    "preprint": "misc",
    "webpage": "misc",
}

def _generate_bibtex(metadata: Dict[str, Any]) -> str:
    bib_type = _BIBTEX_TYPE_MAP.get(metadata.get("itemType", ""), "misc")
    citekey = metadata.get("citekey", "unknown")

    authors = metadata.get("creators", [])
    author_str = " and ".join(
        f"{c['lastName']}, {c['firstName']}" for c in authors if c.get("creatorType") == "author"
    ) or " and ".join(
        f"{c['lastName']}, {c['firstName']}" for c in authors
    )

    year = (metadata.get("date", "") or "")[:4]

    fields: list[tuple[str, str]] = []
    def add(key: str, val: Optional[str]) -> None:
        if val:
            fields.append((key, val.replace("{", "\\{").replace("}", "\\}")))

    add("author", author_str)
    add("title", metadata.get("title"))
    add("year", year)
    add("journal", metadata.get("publicationTitle"))
    add("booktitle", metadata.get("proceedingsTitle") or metadata.get("bookTitle"))
    add("volume", metadata.get("volume"))
    add("number", metadata.get("issue"))
    add("pages", metadata.get("pages"))
    add("publisher", metadata.get("publisher"))
    add("address", metadata.get("place"))
    add("doi", metadata.get("DOI"))
    add("url", metadata.get("url"))
    add("issn", metadata.get("ISSN"))
    add("isbn", metadata.get("ISBN"))
    add("abstract", metadata.get("abstractNote"))

    body = "\n".join(f"  {k} = {{{v}}}," for k, v in fields)
    return f"@{bib_type}{{{citekey},\n{body}\n}}"


def get_zotero_item_metadata(zotero_db_path: str, item_key: str, citation_style: str = "") -> Dict[str, Any]:
    db_path = Path(zotero_db_path).expanduser()
    if not db_path.exists():
        return {}

    temp_db_path = Path(tempfile.gettempdir()) / f"zotero_meta_{os.getpid()}.sqlite"
    try:
        shutil.copy2(db_path, temp_db_path)
    except Exception:
        pass

    try:
        conn = sqlite3.connect(temp_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("""
            SELECT i.itemID, it.typeName as itemType
            FROM items i
            JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
            WHERE i.key = ?
        """, (item_key,))
        row = cur.fetchone()
        if not row:
            return {}

        item_id = row['itemID']
        item_type = row['itemType']

        # Get all fields
        cur.execute("""
            SELECT f.fieldName, idV.value
            FROM itemData iD
            JOIN itemDataValues idV ON iD.valueID = idV.valueID
            JOIN fields f ON iD.fieldID = f.fieldID
            WHERE iD.itemID = ?
        """, (item_id,))

        metadata = {
            "itemType": item_type,
            "key": item_key,
            "desktopURI": f"zotero://select/library/items/{item_key}",
        }
        for f in cur.fetchall():
            metadata[f['fieldName']] = f['value']

        # Generate a fallback citekey if not present
        title = metadata.get('title', 'Unknown')
        date = metadata.get('date', '0000')[:4]

        # Get creators
        cur.execute("""
            SELECT c.firstName, c.lastName, ct.creatorType
            FROM itemCreators ic
            JOIN creators c ON ic.creatorID = c.creatorID
            JOIN creatorTypes ct ON ic.creatorTypeID = ct.creatorTypeID
            WHERE ic.itemID = ?
            ORDER BY ic.orderIndex
        """, (item_id,))
        creators = [dict(c) for c in cur.fetchall()]
        metadata['creators'] = creators

        first_author = creators[0]['lastName'].lower() if creators else 'unknown'
        first_word = ''.join(e for e in title.split(' ')[0] if e.isalnum()).lower()

        metadata['citekey'] = f"{first_author}{date}{first_word}"

        # Get attachments
        cur.execute("""
            SELECT i.key as attachmentKey, ia.path, ia.contentType
            FROM items i
            JOIN itemAttachments ia ON i.itemID = ia.itemID
            WHERE ia.parentItemID = ?
        """, (item_id,))

        attachments = []
        annotations = []

        for att in cur.fetchall():
            att_dict = dict(att)
            att_dict['desktopURI'] = f"zotero://select/library/items/{att_dict['attachmentKey']}"
            attachments.append(att_dict)

            # If PDF, get annotations
            if att_dict.get('path', '').endswith('.pdf') or att_dict.get('contentType') == 'application/pdf':
                zotero_data_dir = str(db_path.parent)
                anns = get_zotero_annotations(str(temp_db_path), att_dict['attachmentKey'], zotero_data_dir)
                for a in anns:
                    a['desktopURI'] = f"zotero://open-pdf/library/items/{att_dict['attachmentKey']}?page={a.get('pageLabel', 1)}&annotation={a.get('key', '')}"
                annotations.extend(anns)

        metadata['attachments'] = attachments
        metadata['annotations'] = annotations
        metadata['bibtex'] = _generate_bibtex(metadata)
        metadata['bibliographyStyle'] = citation_style

    finally:
        if 'conn' in locals() and conn:
            conn.close()
        if temp_db_path != db_path and temp_db_path.exists():
            temp_db_path.unlink(missing_ok=True)

    return metadata
