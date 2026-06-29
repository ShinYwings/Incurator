import sqlite3
import json
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional


def _copy_db_to_repo_temp(db_path: Path) -> Path:
    from . import config as cfg

    temp_dir = cfg.get_global_config_dir().parent / "zotero_sqlite"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile(
        prefix="zotero-",
        suffix=".sqlite",
        delete=False,
        dir=temp_dir,
    )
    temp_db_path = Path(temp_file.name)
    temp_file.close()
    shutil.copy2(db_path, temp_db_path)
    return temp_db_path

def _hex_to_color_category(hex_color: str) -> str:
    """Map Zotero hex color to a human-readable color category name."""
    color_map = {
        "#ffd400": "yellow",
        "#fee832": "yellow",  # Alternate/iOS yellow
        "#ff6666": "red",
        "#5fb236": "green",
        "#2ea8e5": "blue",
        "#a28ae5": "purple",
        "#e56eee": "magenta",
        "#f19837": "orange",
        "#aaaaaa": "gray",
    }
    return color_map.get((hex_color or "").lower(), "gray")


def _annotation_type_to_str(type_int: int) -> str:
    """Map Zotero annotation type integer to string."""
    # Zotero 7: 1=highlight, 2=note (sticky), 3=image/area, 4=underline
    type_map = {1: "highlight", 2: "note", 3: "image", 4: "underline"}
    return type_map.get(type_int, "highlight")


def get_zotero_annotations(
    zotero_db_path: str,
    attachment_key: str,
    zotero_data_dir: str = "",
) -> List[Dict[str, Any]]:
    """
    Reads the locked Zotero SQLite database by copying it to the repo-local
    `.cache/zotero_sqlite/` directory,
    and returns all annotations for a given PDF attachment key.

    Returns fields matching the Nunjucks template contract:
      id, key, type, annotatedText, comment, color, colorCategory,
      pageLabel, pageIndex, dateModified, date, sortIndex,
      imageRelativePath, tags, desktopURI, position
    """
    db_path = Path(zotero_db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Zotero database not found at {zotero_db_path}")

    # Copy to bypass lock.
    temp_db_path = _copy_db_to_repo_temp(db_path)

    conn = None
    try:
        conn = sqlite3.connect(temp_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Find itemID for the attachment key
        cur.execute("SELECT itemID FROM items WHERE key = ?", (attachment_key,))
        row = cur.fetchone()
        if not row:
            return []

        parent_id = row['itemID']

        # Fetch annotations with dateModified from items table
        cur.execute("""
            SELECT
                a.type, a.authorName, a.text, a.comment, a.color,
                a.pageLabel, a.sortIndex, a.position, a.isExternal,
                i.key, i.dateModified, i.dateAdded
            FROM itemAnnotations a
            JOIN items i ON a.itemID = i.itemID
            WHERE a.parentItemID = ?
            ORDER BY a.sortIndex
        """, (parent_id,))

        annotations = []
        for ann in cur.fetchall():
            raw = dict(ann)
            ann_key = raw['key']

            # Parse position JSON
            position = {}
            if raw.get('position'):
                try:
                    position = json.loads(raw['position'])
                except json.JSONDecodeError:
                    pass

            page_index = position.get('pageIndex', 0)

            # Check for annotation image in Zotero cache
            image_path = ""
            if zotero_data_dir and raw['type'] == 3:  # image/area annotation
                cache_path = Path(zotero_data_dir) / "cache" / "library" / f"{ann_key}.png"
                if cache_path.exists():
                    image_path = str(cache_path)

            # Fetch tags for this annotation
            ann_item_id_row = cur.execute(
                "SELECT itemID FROM items WHERE key = ?", (ann_key,)
            ).fetchone()
            tags = []
            if ann_item_id_row:
                tag_rows = cur.execute("""
                    SELECT t.name as tag
                    FROM itemTags it
                    JOIN tags t ON it.tagID = t.tagID
                    WHERE it.itemID = ?
                """, (ann_item_id_row['itemID'],)).fetchall()
                tags = [{"tag": r['tag']} for r in tag_rows]

            result = {
                "id": ann_key,
                "key": ann_key,
                "type": _annotation_type_to_str(raw['type']),
                "annotatedText": raw.get('text') or "",
                "comment": raw.get('comment') or "",
                "color": raw.get('color') or "",
                "colorCategory": _hex_to_color_category(str(raw.get('color') or "")),
                "pageLabel": raw.get('pageLabel') or str(page_index + 1),
                "pageIndex": page_index,
                "sortIndex": raw.get('sortIndex') or "",
                "dateModified": raw.get('dateModified') or "",
                "date": raw.get('dateAdded') or "",
                "position": position,
                "imageRelativePath": image_path,
                "tags": tags,
            }
            annotations.append(result)

        return annotations
    finally:
        if conn:
            conn.close()
        if temp_db_path.exists():
            temp_db_path.unlink(missing_ok=True)

def get_zotero_attachment_path_from_db(zotero_db_path: str, attachment_key: str) -> Optional[str]:
    """
    Looks up the attachment path in the Zotero SQLite database.
    Returns the raw path string (e.g., 'attachments:file.pdf', 'storage:file.pdf', or an absolute path).
    """
    db_path = Path(zotero_db_path)
    if not db_path.exists():
        return None

    temp_db_path = _copy_db_to_repo_temp(db_path)

    conn = None
    try:
        conn = sqlite3.connect(temp_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Find itemID
        cur.execute("SELECT itemID FROM items WHERE key = ?", (attachment_key,))
        row = cur.fetchone()
        if not row:
            return None
        
        item_id = row['itemID']

        # Get path (if it's an attachment directly)
        cur.execute("SELECT path FROM itemAttachments WHERE itemID = ?", (item_id,))
        att_row = cur.fetchone()
        if att_row and att_row['path']:
            return att_row['path']
            
        return None
    finally:
        if conn:
            conn.close()
        if temp_db_path.exists():
            temp_db_path.unlink(missing_ok=True)

def resolve_pdf_attachment_for_key(
    zotero_db_path: str, key: str
) -> Optional[tuple[str, str]]:
    """Resolve a Zotero ``key`` (an attachment key OR a parent item key) to the
    PDF attachment's ``(attachment_key, db_path)``.

    A ``zotero_app_url`` (``zotero://select/library/items/<KEY>``) carries the
    PARENT item key, but the PDF lives on a CHILD attachment. The previous
    resolution only looked up ``itemAttachments`` by the key's own ``itemID``, so
    a parent key found no path and reported "attachment key not found" (while
    page-based navigation, which already had the attachment key, worked). This
    returns the key as-is when it is itself an attachment, otherwise finds the
    item's first PDF child attachment and returns that child's key + path.
    """
    db_path = Path(zotero_db_path)
    if not db_path.exists():
        return None

    temp_db_path = _copy_db_to_repo_temp(db_path)

    conn = None
    try:
        conn = sqlite3.connect(temp_db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("SELECT itemID FROM items WHERE key = ?", (key,))
        row = cur.fetchone()
        if not row:
            return None
        item_id = row["itemID"]

        # 1. The key is itself an attachment with a path.
        cur.execute("SELECT path FROM itemAttachments WHERE itemID = ?", (item_id,))
        att = cur.fetchone()
        if att and att["path"]:
            return (key, att["path"])

        # 2. The key is a parent item → find its PDF child attachment. Defensive
        #    against a simplified/old schema lacking parentItemID/contentType.
        try:
            cur.execute(
                """
                SELECT i.key AS att_key, ia.path AS path, ia.contentType AS ctype
                FROM itemAttachments ia
                JOIN items i ON i.itemID = ia.itemID
                WHERE ia.parentItemID = ?
                """,
                (item_id,),
            )
            children = cur.fetchall()
        except sqlite3.OperationalError:
            return None

        first_with_path: Optional[tuple[str, str]] = None
        for child in children:
            path = child["path"] or ""
            if not path:
                continue
            if first_with_path is None:
                first_with_path = (child["att_key"], path)
            ctype = (child["ctype"] or "") if "ctype" in child.keys() else ""
            if path.lower().endswith(".pdf") or ctype == "application/pdf":
                return (child["att_key"], path)
        return first_with_path
    finally:
        if conn:
            conn.close()
        if temp_db_path.exists():
            temp_db_path.unlink(missing_ok=True)


def resolve_zotero_attachment_path(zotero_data_dir: str, attachment_key: str) -> Optional[str]:
    """
    Finds the absolute path to a PDF attachment given its key.
    """
    storage_dir = Path(zotero_data_dir) / "storage" / attachment_key
    if not storage_dir.exists():
        return None
    
    for file in storage_dir.iterdir():
        if file.suffix.lower() == '.pdf':
            return str(file.resolve())
            
    return None
