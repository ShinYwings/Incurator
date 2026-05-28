"""Source registry helpers for reference-mode MCP tools.

This module deliberately has no MCP dependency so tests can exercise source
status, external resource discovery, and human-approved rebinding directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config as cfg
from . import db, parsers


@dataclass(frozen=True)
class SourceStatus:
    state: str
    message: str
    current_path: str = ""
    current_hash: str = ""
    candidate_path: str = ""
    candidate_hash: str = ""
    requires_rebind: bool = False
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "message": self.message,
            "current_path": self.current_path,
            "current_hash": self.current_hash,
            "candidate_path": self.candidate_path,
            "candidate_hash": self.candidate_hash,
            "requires_rebind": self.requires_rebind,
            "error": self.error,
        }


def parse_source(path: Path) -> parsers.ParsedDocument:
    """Parse a supported source path and return the normalized document."""
    if not parsers.is_supported(path):
        raise parsers.ParserError(f"Unsupported file type: {path.suffix or '(no extension)'}")
    return parsers.parse(path)


def external_resources(config: dict) -> list[dict[str, Any]]:
    """Return normalized external resource roots from config.

    Accepts both the v0.2 nested shape:

        external:
          roots: [...]
          zotero:
            roots: [...]

    and a forgiving `path`/string shorthand used in older notes.
    """

    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    external = config.get("external") or {}
    if not isinstance(external, dict):
        return out

    def add_root(name: str, raw: Any, enabled: bool = True) -> None:
        if raw is None or raw == "":
            return
        values = raw if isinstance(raw, list) else [raw]
        for value in values:
            if not isinstance(value, str) or not value.strip():
                continue
            path = str(Path(value).expanduser())
            key = (name, path)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "name": name,
                    "path": path,
                    "enabled": bool(enabled),
                    "exists": Path(path).expanduser().exists(),
                }
            )

    add_root("external", external.get("roots"), True)
    for name, spec in external.items():
        if name == "roots":
            continue
        if isinstance(spec, dict):
            enabled = bool(spec.get("enabled", True))
            add_root(str(name), spec.get("roots") or spec.get("path"), enabled)
        else:
            add_root(str(name), spec, True)
    return out


def _row_path(paths: cfg.WikiPaths, row: dict[str, Any]) -> Path:
    external_path = str(row.get("external_path") or "")
    if int(row.get("is_reference") or 0) and external_path:
        return Path(external_path).expanduser()
    relpath = str(row.get("relpath") or "")
    candidate = Path(relpath).expanduser()
    if candidate.is_absolute():
        return candidate
    return paths.root / relpath


def _candidate_roots(config: dict) -> list[Path]:
    roots: list[Path] = []
    for item in external_resources(config):
        if item.get("enabled") is False:
            continue
        raw = item.get("path")
        if not isinstance(raw, str) or not raw:
            continue
        path = Path(raw).expanduser()
        if path.exists() and path.is_dir():
            roots.append(path)
    return roots


def find_moved_candidate(
    filename: str,
    expected_hash: str,
    config: dict,
    max_candidates: int = 200,
) -> tuple[Path | None, str]:
    """Search configured roots for a moved source.

    Returns the first exact-hash match when possible. If only same-name files
    with different content are found, returns the first candidate and its hash
    so the caller can surface a human rebind decision.
    """

    fallback: tuple[Path | None, str] = (None, "")
    checked = 0
    for root in _candidate_roots(config):
        try:
            iterator = root.rglob(filename)
            for candidate in iterator:
                if checked >= max_candidates:
                    return fallback
                checked += 1
                if not candidate.is_file():
                    continue
                try:
                    parsed = parse_source(candidate)
                except Exception:
                    continue
                if parsed.content_hash == expected_hash:
                    return candidate.resolve(), parsed.content_hash
                if fallback[0] is None:
                    fallback = (candidate.resolve(), parsed.content_hash)
        except OSError:
            continue
    return fallback


def source_status(
    paths: cfg.WikiPaths,
    row: dict[str, Any],
    config: dict,
) -> dict[str, Any]:
    """Return source row metadata enriched with reference/live-file state."""

    out = dict(row)
    expected_hash = str(row.get("content_hash") or "")
    path = _row_path(paths, row)
    out["current_path"] = str(path)
    out["requires_rebind"] = False

    if not path.exists():
        if int(row.get("is_reference") or 0):
            candidate, candidate_hash = find_moved_candidate(
                path.name,
                expected_hash,
                config,
            )
            if candidate and candidate_hash == expected_hash:
                out.update(
                    SourceStatus(
                        state="moved",
                        message="Reference source moved; human-approved rebind is required.",
                        current_path=str(path),
                        candidate_path=str(candidate),
                        candidate_hash=candidate_hash,
                        requires_rebind=True,
                    ).as_dict()
                )
                return out
            if candidate:
                out.update(
                    SourceStatus(
                        state="moved_and_hash_drift",
                        message=(
                            "Reference source moved and candidate content changed; "
                            "inspect before rebinding."
                        ),
                        current_path=str(path),
                        candidate_path=str(candidate),
                        candidate_hash=candidate_hash,
                        requires_rebind=True,
                    ).as_dict()
                )
                return out
            out.update(
                SourceStatus(
                    state="missing",
                    message="Reference source file is missing from its cached path.",
                    current_path=str(path),
                    requires_rebind=True,
                ).as_dict()
            )
            return out
        out.update(
            SourceStatus(
                state="missing",
                message="Vault source file is missing.",
                current_path=str(path),
                requires_rebind=False,
            ).as_dict()
        )
        return out

    try:
        parsed = parse_source(path)
    except Exception as exc:
        out.update(
            SourceStatus(
                state="error",
                message=f"Could not parse source: {exc}",
                current_path=str(path),
                error=str(exc),
            ).as_dict()
        )
        return out

    current_hash = parsed.content_hash
    out["current_hash"] = current_hash
    if current_hash != expected_hash:
        out.update(
            SourceStatus(
                state="hash_drift",
                message="Source content hash differs from the tracked registry hash.",
                current_path=str(path),
                current_hash=current_hash,
                requires_rebind=bool(int(row.get("is_reference") or 0)),
            ).as_dict()
        )
        return out

    status = str(row.get("status") or "pending")
    state = "indexed" if status in {"curated", "done"} else status
    out.update(
        SourceStatus(
            state=state,
            message="Source file matches the tracked registry hash.",
            current_path=str(path),
            current_hash=current_hash,
        ).as_dict()
    )
    return out


def rebind_source(
    paths: cfg.WikiPaths,
    row: dict[str, Any],
    new_path: Path,
    *,
    apply: bool = False,
    update_hash: bool = True,
) -> dict[str, Any]:
    """Return or apply a human-approved source rebind proposal."""

    source_id = int(row["id"])
    old_path = _row_path(paths, row)
    new_path = new_path.expanduser().resolve()
    if not new_path.exists() or not new_path.is_file():
        return {
            "ok": False,
            "state": "error",
            "error": f"File not found: {new_path}",
            "source_id": source_id,
        }
    parsed = parse_source(new_path)
    old_hash = str(row.get("content_hash") or "")
    hash_changed = parsed.content_hash != old_hash
    proposal = {
        "ok": True,
        "state": "rebind_proposal" if not apply else "rebound",
        "source_id": source_id,
        "old_path": str(old_path),
        "new_path": str(new_path),
        "old_hash": old_hash,
        "new_hash": parsed.content_hash,
        "hash_changed": hash_changed,
        "apply": apply,
        "requires_human_approval": not apply,
        "message": (
            "Dry run: would rebind source to the new path."
            if not apply
            else "Source rebound to the new path."
        ),
    }
    if not apply:
        return proposal

    relpath = str(new_path)
    content_hash = parsed.content_hash if update_hash else old_hash
    status = "pending" if update_hash and hash_changed else str(row.get("status") or "pending")
    with db.connect(paths.state_db) as conn:
        conn.execute(
            """
            UPDATE sources
            SET relpath = ?, external_path = ?, import_origin = ?,
                content_hash = ?, file_type = ?, bytes = ?,
                status = ?, last_ingested = CASE WHEN ? THEN NULL ELSE last_ingested END,
                context_id = CASE WHEN ? THEN NULL ELSE context_id END,
                l1_status = CASE WHEN ? THEN 'pending' ELSE l1_status END,
                l2_status = CASE WHEN ? THEN 'pending' ELSE l2_status END,
                l3_status = CASE WHEN ? THEN 'pending' ELSE l3_status END,
                l4_status = CASE WHEN ? THEN 'pending' ELSE l4_status END,
                layer_error = NULL, error_reason = NULL,
                is_reference = 1,
                import_policy = COALESCE(import_policy, 'reference')
            WHERE id = ?
            """,
            (
                relpath,
                str(new_path),
                str(new_path),
                content_hash,
                parsed.file_type,
                parsed.bytes,
                status,
                int(update_hash and hash_changed),
                int(update_hash and hash_changed),
                int(update_hash and hash_changed),
                int(update_hash and hash_changed),
                int(update_hash and hash_changed),
                int(update_hash and hash_changed),
                source_id,
            ),
        )
    pages = []
    if parsed.file_type == "pdf":
        pages = list(parsed.metadata.get("pages") or [])
    db.replace_source_pdf_pages(paths.state_db, source_id, relpath, pages)
    try:
        paths.ledger.parent.mkdir(parents=True, exist_ok=True)
        with paths.ledger.open("a", encoding="utf-8") as f:
            f.write(
                "\n"
                f"- rebind_source: source_id={source_id} old={old_path} new={new_path} "
                f"hash_changed={hash_changed}\n"
            )
    except OSError:
        pass
    return proposal
