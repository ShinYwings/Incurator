"""Single PDF/source identity resolution authority (SYSTEM_BEHAVIOR §29.6).

A PDF/source is referred to by up to five identifiers (vault relpath, absolute
path, Zotero attachment key, content hash, logical source id). This module is the
ONE place that converts between them, so Reference Mode ingest, add-source, and
locator building all consume the same result instead of re-deriving identity ad
hoc.

This is a facade over existing helpers. It performs NO DB mutation and does NOT
change dedup semantics — it only reads.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from . import config as cfg
from . import db

# resolution_status values
RESOLVED = "resolved"
PATH_UNRESOLVED = "path_unresolved"
UNTRACKED = "untracked"


@dataclass(frozen=True)
class AssetIdentity:
    resolution_status: str
    source_id: int | None = None
    abs_path: str | None = None
    relpath: str | None = None
    logical_source_id: str | None = None
    zotero_key: str | None = None
    content_hash: str | None = None
    is_reference: bool = False


def default_logical_source_id(abs_path: str) -> str:
    """Deterministic logical id from an absolute path (v1 fallback).

    Mirrors ``ingest_raw._default_logical_source_id`` so the two cannot drift.
    """
    digest = hashlib.sha256(
        str(Path(abs_path).expanduser().resolve()).encode("utf-8")
    ).hexdigest()
    return f"ref-{digest[:16]}"


def _zotero_key_from_logical(logical: Any) -> str | None:
    if isinstance(logical, str) and logical.startswith("zotero:"):
        return logical.split(":", 1)[1] or None
    return None


def from_source_row(source: dict[str, Any] | None) -> AssetIdentity:
    """Construct a AssetIdentity from an already-fetched ``sources`` row.

    Cheap (no I/O). Used by locator building, which already holds the row. For a
    Reference Mode row the external file path is exposed as ``abs_path`` and is
    authoritative for opening; the in-vault ``relpath`` is only the stub.
    """
    if not source:
        return AssetIdentity(resolution_status=UNTRACKED)
    is_reference = bool(source.get("is_reference"))
    external = source.get("external_path") or source.get("import_origin")
    abs_path = str(external) if (is_reference and external) else None
    relpath = source.get("relpath") or None
    status = RESOLVED if (relpath or abs_path) else PATH_UNRESOLVED
    logical = source.get("logical_source_id") or None
    return AssetIdentity(
        resolution_status=status,
        source_id=int(source["id"]) if source.get("id") is not None else None,
        abs_path=abs_path,
        relpath=relpath,
        logical_source_id=logical,
        zotero_key=_zotero_key_from_logical(logical),
        content_hash=source.get("content_hash") or None,
        is_reference=is_reference,
    )


def resolve(
    paths: cfg.WikiPaths,
    *,
    relpath: str = "",
    abs_path: str = "",
    zotero_key: str = "",
    content_hash: str = "",
    logical_source_id: str = "",
    zotero_custom_paths: str = "",
) -> AssetIdentity:
    """Resolve whatever identifiers are provided into a canonical AssetIdentity.

    1. A Zotero key derives ``zotero:<key>`` and (via the single backend Zotero
       resolver) its local file path.
    2. An existing ``sources`` row is matched by relpath / external_path /
       import_origin / logical_source_id.

    Returns ``UNTRACKED`` when no row matches (still echoing any resolved path /
    logical id so an ingest caller can create the row).
    """
    resolved_logical = logical_source_id or ""
    resolved_abs = abs_path or ""

    if zotero_key:
        if not resolved_logical:
            resolved_logical = f"zotero:{zotero_key}"
        if not resolved_abs:
            from . import zotero_tools

            res = zotero_tools.resolve_pdf(zotero_key, paths, zotero_custom_paths)
            if res.get("ok") and res.get("path"):
                resolved_abs = str(res["path"])

    row: dict[str, Any] | None = None
    if relpath:
        row = db.get_source_row(paths.state_db, paths.root, relpath=relpath)
    if row is None and resolved_abs:
        row = db.get_source_row(paths.state_db, paths.root, source_path=resolved_abs)
    if row is None and resolved_logical:
        # get_source_row's lookup also matches logical_source_id via its OR clause.
        row = db.get_source_row(paths.state_db, paths.root, relpath=resolved_logical)

    if row is not None:
        ident = from_source_row(row)
        return replace(
            ident,
            abs_path=ident.abs_path or (resolved_abs or None),
            logical_source_id=ident.logical_source_id or (resolved_logical or None),
            zotero_key=ident.zotero_key or (zotero_key or None),
            content_hash=ident.content_hash or (content_hash or None),
        )

    abs_exists = bool(resolved_abs) and Path(resolved_abs).expanduser().exists()
    return AssetIdentity(
        resolution_status=UNTRACKED,
        source_id=None,
        abs_path=resolved_abs if abs_exists else None,
        relpath=relpath or None,
        logical_source_id=resolved_logical or None,
        zotero_key=zotero_key or None,
        content_hash=content_hash or None,
        is_reference=bool(zotero_key),
    )
