"""Backend Zotero helpers for CLI, plugin, and MCP wrappers."""

from __future__ import annotations

import copy
import os
import platform
import re
import sqlite3
from pathlib import Path
from typing import Any

from . import config as cfg
from . import constants as consts
from . import zotero


def zotero_db_candidates(custom_paths: str) -> list[str]:
    """Expand configured Zotero directories/sqlite paths into DB candidates."""
    out: list[str] = []
    for raw in str(custom_paths or "").split(","):
        p = raw.strip()
        if not p:
            continue
        base = os.path.expanduser(p)
        out.append(base if base.endswith(".sqlite") else os.path.join(base, consts.FILE_ZOTERO_SQLITE))
    return out


def _db_candidates(custom_paths: str, config: dict[str, Any] | None = None) -> list[str]:
    candidates = zotero_db_candidates(custom_paths)
    for root in zotero_root_candidates(custom_paths, config):
        db_path = root if root.endswith(".sqlite") else os.path.join(root, consts.FILE_ZOTERO_SQLITE)
        candidates.append(db_path)

    out: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        norm = os.path.normpath(os.path.expanduser(candidate))
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def _sqlite_readable(db_path: str) -> tuple[bool, str]:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        finally:
            conn.close()
    except Exception as exc:
        return False, str(exc)
    return True, ""


def zotero_status(paths: cfg.WikiPaths, custom_paths: str = "") -> dict[str, Any]:
    """Return backend-owned Zotero setup diagnostics for this machine."""
    config = cfg.load_config(paths)
    checked = _db_candidates(custom_paths, config)
    existing_dirs: list[str] = []
    issues: list[dict[str, str]] = []

    for db_path in checked:
        parent = str(Path(db_path).expanduser().parent)
        if os.path.isdir(parent) and parent not in existing_dirs:
            existing_dirs.append(parent)
        if not os.path.exists(db_path):
            continue
        readable, error = _sqlite_readable(db_path)
        if readable:
            return {
                "ok": True,
                "state": "ready",
                "data_dir": parent,
                "db_path": db_path,
                "roots_checked": checked,
                "issues": issues,
            }
        issues.append({"path": db_path, "error": error})

    state = "db_missing" if existing_dirs else "not_configured"
    return {
        "ok": False,
        "state": "db_unreadable" if issues else state,
        "data_dir": existing_dirs[0] if existing_dirs else "",
        "db_path": "",
        "roots_checked": checked,
        "issues": issues,
    }


def zotero_init(
    paths: cfg.WikiPaths,
    *,
    data_dir: str = "",
    linked_base_dir: str = "",
    custom_paths: str = "",
) -> dict[str, Any]:
    """Persist local Zotero roots into Curator config after validation."""
    config = cfg.load_config(paths)
    updated = copy.deepcopy(config)
    external = updated.setdefault("external", {})
    zotero_cfg = external.setdefault("zotero", {})
    zotero_cfg["enabled"] = True

    roots = list(zotero_cfg.get("roots") or [])
    chosen = data_dir.strip()
    if not chosen:
        current = zotero_status(paths, custom_paths)
        chosen = str(current.get("data_dir") or "")
    if chosen.endswith(".sqlite"):
        chosen = str(Path(chosen).expanduser().parent)

    for raw in (chosen, linked_base_dir.strip()):
        if not raw:
            continue
        expanded = os.path.expanduser(raw)
        if expanded not in roots:
            roots.append(expanded)
    zotero_cfg["roots"] = roots

    cfg.save_global_config({"external": external})
    status = zotero_status(paths, custom_paths)
    status["saved_roots"] = roots
    return status


def _decode_prefs_path(value: str) -> str:
    if "\\" not in value:
        return value
    try:
        return bytes(value, "utf-8").decode("unicode_escape")
    except Exception:
        return value


def _zotero_profile_roots() -> list[str]:
    if platform.system() == "Darwin":
        return [os.path.expanduser("~/Library/Application Support/Zotero/Profiles")]
    if platform.system() == "Linux":
        return [os.path.expanduser("~/.zotero/zotero")]
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return [os.path.join(appdata, "Zotero", "Profiles")]
    return []


def discover_zotero_base_attachment_path(candidates: list[str]) -> None:
    """Append baseAttachmentPath/ZotMoov paths from Zotero prefs.js if present."""
    profile_roots = _zotero_profile_roots()

    for root in profile_roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for prefs in root_path.glob("*/prefs.js"):
            try:
                text = prefs.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for key in ("extensions.zotero.baseAttachmentPath", "extensions.zotmoov.dst_dir"):
                match = re.search(rf'user_pref\("{re.escape(key)}",\s*"([^"]+)"\);', text)
                if match:
                    candidates.append(os.path.expanduser(_decode_prefs_path(match.group(1))))


def zotero_root_candidates(custom_paths: str, config: dict[str, Any] | None = None) -> list[str]:
    """Return Zotero data/attachment roots from settings, config, and prefs."""
    candidates = [os.path.expanduser("~/Zotero")]
    for raw in str(custom_paths or "").split(","):
        p = raw.strip()
        if not p:
            continue
        expanded = os.path.expanduser(p)
        candidates.append(os.path.dirname(expanded) if expanded.endswith(".sqlite") else expanded)
    if config and "external" in config and "zotero" in config["external"]:
        for root in config["external"]["zotero"].get("roots", []):
            candidates.append(os.path.expanduser(root))

    discover_zotero_base_attachment_path(candidates)

    out: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        norm = os.path.normpath(candidate)
        if norm in seen:
            continue
        seen.add(norm)
        out.append(candidate)
    return out


def search_items(
    query: str,
    custom_paths: str,
    limit: int = 20,
    paths: cfg.WikiPaths | None = None,
) -> dict[str, Any]:
    from .zotero_integration import search_zotero_items

    config = cfg.load_config(paths) if paths else None
    checked: list[str] = []
    for zotero_db in _db_candidates(custom_paths, config):
        checked.append(zotero_db)
        if not os.path.exists(zotero_db):
            continue
        items = search_zotero_items(zotero_db, query, limit=limit)
        if items:
            return {"ok": True, "items": items, "db_path": zotero_db}
    if not any(os.path.exists(item) for item in checked):
        return {"ok": False, "state": "db_missing", "items": [], "checked": checked}
    return {"ok": True, "items": [], "checked": checked}


def item_metadata(
    item_key: str,
    custom_paths: str,
    citation_style: str = "",
    paths: cfg.WikiPaths | None = None,
) -> dict[str, Any]:
    from .zotero_integration import get_zotero_item_metadata

    config = cfg.load_config(paths) if paths else None
    candidates = [item for item in _db_candidates(custom_paths, config) if os.path.exists(item)]
    if not candidates:
        return {"ok": False, "state": "db_missing", "error": "Zotero database not found"}
    metadata = get_zotero_item_metadata(candidates[0], item_key, citation_style=citation_style)
    return {"ok": True, "metadata": metadata}


def annotations(attachment_key: str, paths: cfg.WikiPaths, custom_paths: str = "") -> dict[str, Any]:
    config = cfg.load_config(paths)
    zotero_db = config.get("zotero", {}).get("db_path", os.path.expanduser("~/Zotero/zotero.sqlite"))
    for db_cand in _db_candidates(custom_paths, config):
        if os.path.exists(db_cand):
            zotero_db = db_cand
            break
    data_dir = str(Path(zotero_db).parent) if zotero_db else ""
    return {"ok": True, "annotations": zotero.get_zotero_annotations(zotero_db, attachment_key, data_dir)}


def _first_existing_zotero_db(custom_paths: str, config: dict[str, Any]) -> str:
    for db_cand in _db_candidates(custom_paths, config):
        if os.path.exists(db_cand):
            return db_cand
    return ""


def _pdf_candidates_for_db_path(db_path: str, attachment_key: str, roots: list[str]) -> list[str]:
    if not db_path:
        return []
    if db_path.startswith("attachments:"):
        rel_path = db_path[len("attachments:"):]
        return [os.path.join(root, rel_path) for root in roots]
    if db_path.startswith("storage:"):
        rel_path = db_path[len("storage:"):]
        return [os.path.join(root, "storage", attachment_key, rel_path) for root in roots]
    if os.path.isabs(db_path):
        return [db_path]
    return [os.path.join(root, db_path) for root in roots]


def _storage_pdf_candidates(attachment_key: str, roots: list[str]) -> list[str]:
    out: list[str] = []
    for root in roots:
        item_dir = os.path.join(root, "storage", attachment_key)
        if not os.path.isdir(item_dir):
            continue
        try:
            filenames = sorted(os.listdir(item_dir))
        except OSError:
            continue
        for filename in filenames:
            if filename.lower().endswith(".pdf"):
                out.append(os.path.join(item_dir, filename))
    return out


def _first_existing_pdf(candidates: list[str]) -> str:
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return ""


def resolve_pdf(attachment_key: str, paths: cfg.WikiPaths, custom_paths: str = "") -> dict[str, Any]:
    config = cfg.load_config(paths)
    candidates = zotero_root_candidates(custom_paths, config)

    zotero_db = _first_existing_zotero_db(custom_paths, config)
    if not zotero_db:
        checked = _db_candidates(custom_paths, config)
        return {
            "ok": False,
            "state": "db_missing",
            "error": "Zotero database not found",
            "roots_checked": checked,
        }

    # Accept either an attachment key OR a parent item key (zotero_app_url carries
    # the parent item key; the PDF lives on a child attachment). The effective
    # attachment key drives the storage subdirectory lookup.
    resolved = zotero.resolve_pdf_attachment_for_key(zotero_db, attachment_key)
    effective_key = resolved[0] if resolved else attachment_key
    db_path = resolved[1] if resolved else None
    checked_paths: list[str] = []
    if db_path:
        checked_paths = _pdf_candidates_for_db_path(db_path, effective_key, candidates)
        found = _first_existing_pdf(checked_paths)
        if found:
            return {
                "ok": True, "path": found, "db_path": db_path,
                "zotero_db": zotero_db, "attachment_key": effective_key,
            }

    fallback_candidates = _storage_pdf_candidates(effective_key, candidates)
    found = _first_existing_pdf(fallback_candidates)
    if found:
        return {
            "ok": True, "path": found, "zotero_db": zotero_db,
            "attachment_key": effective_key,
        }

    checked_paths.extend(fallback_candidates)
    state = "attachment_file_missing" if db_path else "attachment_key_missing"
    error = "Zotero attachment file not found" if db_path else "Zotero attachment key not found"

    return {
        "ok": False,
        "state": state,
        "error": error,
        "db_path": db_path or "",
        "zotero_db": zotero_db,
        "roots_checked": candidates,
        "paths_checked": checked_paths,
    }
