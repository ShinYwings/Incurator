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


def from_source_row(
    source: dict[str, Any] | None, *, verify_exists: bool = False
) -> AssetIdentity:
    """Construct an AssetIdentity from an already-fetched ``sources`` row.

    For a Reference Mode row the external file path is exposed as ``abs_path`` and
    is authoritative for opening; the in-vault ``relpath`` is only the stub.

    By default this is cheap (no I/O) — the locator hot path uses it directly.
    Pass ``verify_exists=True`` (as ``resolve`` does) to stat the external file:
    a Reference Mode source whose external file has moved/been deleted is then
    downgraded to ``PATH_UNRESOLVED`` with ``abs_path=None`` so callers never
    trust a phantom path.
    """
    if not source:
        return AssetIdentity(resolution_status=UNTRACKED)
    is_reference = bool(source.get("is_reference"))
    external = source.get("external_path") or source.get("import_origin")
    abs_path = str(external) if (is_reference and external) else None
    if verify_exists and abs_path and not Path(abs_path).expanduser().exists():
        abs_path = None
    relpath = source.get("relpath") or None
    # A Reference Mode source's only usable open target is the external file
    # (relpath is a stub); a vault source's target is its relpath.
    if is_reference:
        status = RESOLVED if abs_path else PATH_UNRESOLVED
    else:
        status = RESOLVED if relpath else PATH_UNRESOLVED
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
        # Strict, isolated match on the logical_source_id column — never smuggle
        # the logical id through `relpath` (that risks a path/logical collision
        # via get_source_row's relpath OR clause). Kept local so the frozen
        # db.py is untouched (Plan D2 holdout pins its hash).
        with db.connect(paths.state_db) as conn:
            r = conn.execute(
                "SELECT * FROM sources WHERE logical_source_id = ?",
                (resolved_logical,),
            ).fetchone()
            row = dict(r) if r else None

    if row is not None:
        # The matched row is authoritative for the identity. verify_exists: a
        # tracked Reference Mode source whose external file is gone must not be
        # returned as RESOLVED with a phantom abs_path.
        ident = from_source_row(row, verify_exists=True)
        # content_hash is safe to backfill for any source kind.
        merged_hash = ident.content_hash or (content_hash or None)
        if not ident.is_reference:
            # State-leakage guard: a vault source must never inherit Zotero /
            # external-reference identity from the caller's arguments just because
            # its own logical fields are empty. Only the content hash is filled.
            return replace(ident, content_hash=merged_hash)
        # Reference row: caller-provided reference identity refers to the same
        # external entity, so it may fill genuinely-missing fields. A freshly
        # resolved path (e.g. Zotero) that exists on disk can recover an
        # otherwise path_unresolved reference row.
        recovered = (
            resolved_abs
            if (resolved_abs and Path(resolved_abs).expanduser().exists())
            else None
        )
        abs_final = ident.abs_path or recovered
        status = ident.resolution_status
        if status == PATH_UNRESOLVED and abs_final:
            status = RESOLVED
        return replace(
            ident,
            resolution_status=status,
            abs_path=abs_final,
            logical_source_id=ident.logical_source_id or (resolved_logical or None),
            zotero_key=ident.zotero_key or (zotero_key or None),
            content_hash=merged_hash,
        )

    abs_exists = bool(resolved_abs) and Path(resolved_abs).expanduser().exists()
    # Derive the effective Zotero key from either the explicit argument or a
    # `zotero:<key>` logical id, so an identity built from logical_source_id alone
    # is not structurally inconsistent (zotero logical id but is_reference=False).
    eff_zotero_key = zotero_key or _zotero_key_from_logical(resolved_logical)
    return AssetIdentity(
        resolution_status=UNTRACKED,
        source_id=None,
        abs_path=resolved_abs if abs_exists else None,
        relpath=relpath or None,
        logical_source_id=resolved_logical or None,
        zotero_key=eff_zotero_key,
        content_hash=content_hash or None,
        is_reference=bool(eff_zotero_key),
    )
