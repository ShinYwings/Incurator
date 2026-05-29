import sqlite3
import json
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional

def _hex_to_color_category(hex_color: str) -> str:
    """Map Zotero hex color to a human-readable color category name."""
    color_map = {
        "#ffd400": "yellow",
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
    Reads the locked Zotero SQLite database by copying it to /tmp,
    and returns all annotations for a given PDF attachment key.

    Returns fields matching the Nunjucks template contract:
      id, key, type, annotatedText, comment, color, colorCategory,
      pageLabel, pageIndex, dateModified, date, sortIndex,
      imageRelativePath, tags, desktopURI, position
    """
    db_path = Path(zotero_db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Zotero database not found at {zotero_db_path}")

    # Copy to bypass lock
    temp_db_path = Path("/tmp/zotero_temp.sqlite")
    shutil.copy2(db_path, temp_db_path)

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
                "colorCategory": _hex_to_color_category(raw.get('color')),
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

def get_zotero_attachment_path_from_db(zotero_db_path: str, attachment_key: str) -> Optional[str]:
    """
    Looks up the attachment path in the Zotero SQLite database.
    Returns the raw path string (e.g., 'attachments:file.pdf', 'storage:file.pdf', or an absolute path).
    """
    db_path = Path(zotero_db_path)
    if not db_path.exists():
        return None

    temp_db_path = Path("/tmp/zotero_temp.sqlite")
    shutil.copy2(db_path, temp_db_path)

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
