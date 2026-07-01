"""Portable external-file references.

Persistent state stores ``@<root_key>/<relative-posix-path>``. Absolute root
values are supplied by the machine-local repository cache configuration and are
expanded only at an I/O boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping

_ROOT_KEY = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


class RootUnregisteredError(ValueError):
    """Raised when an absolute path is outside every configured named root."""


@dataclass(frozen=True)
class PortablePathRef:
    root_key: str
    relpath: str

    def __post_init__(self) -> None:
        if not _ROOT_KEY.fullmatch(self.root_key):
            raise ValueError(f"invalid root key: {self.root_key!r}")
        _validate_relative(self.relpath)

    def __str__(self) -> str:
        return f"@{self.root_key}/{self.relpath}"

    @classmethod
    def parse(cls, raw: str) -> "PortablePathRef":
        if not isinstance(raw, str) or not raw.startswith("@"):
            raise ValueError("portable path ref must start with '@'")
        root_key, separator, relpath = raw[1:].partition("/")
        if not separator:
            raise ValueError("portable path ref must include a relative path")
        return cls(root_key=root_key, relpath=relpath)


def _validate_relative(raw: str) -> None:
    if (
        not raw
        or raw.startswith(("/", "\\"))
        or raw.startswith("file://")
        or _WINDOWS_DRIVE.match(raw)
        or "\\" in raw
    ):
        raise ValueError(f"invalid portable relative path: {raw!r}")
    path = PurePosixPath(raw)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"portable relative path may not traverse: {raw!r}")
    if path.as_posix() != raw:
        raise ValueError(f"portable relative path is not canonical: {raw!r}")


def configured_roots(config: Mapping[str, object]) -> dict[str, Path]:
    external = config.get("external")
    if not isinstance(external, Mapping):
        return {}
    raw_roots = external.get("path_roots")
    if not isinstance(raw_roots, Mapping):
        return {}
    roots: dict[str, Path] = {}
    for key, value in raw_roots.items():
        if not isinstance(key, str) or not _ROOT_KEY.fullmatch(key):
            continue
        if isinstance(value, str) and value.strip():
            roots[key] = Path(value).expanduser()
    return roots


def encode_path(path: Path, roots: Mapping[str, Path | str]) -> str:
    target = path.expanduser().resolve(strict=False)
    matches: list[tuple[str, Path, Path]] = []
    for key, raw_root in roots.items():
        if not _ROOT_KEY.fullmatch(key):
            continue
        root = Path(raw_root).expanduser().resolve(strict=False)
        try:
            relative = target.relative_to(root)
        except ValueError:
            continue
        if not relative.parts:
            continue
        matches.append((key, root, relative))
    if not matches:
        raise RootUnregisteredError(
            f"path is outside configured external.path_roots: {target}"
        )
    key, _, relative = max(matches, key=lambda item: len(item[1].parts))
    return str(PortablePathRef(key, relative.as_posix()))


def resolve_ref(ref: str, roots: Mapping[str, Path | str]) -> Path:
    parsed = PortablePathRef.parse(ref)
    if parsed.root_key not in roots:
        raise RootUnregisteredError(
            f"external root key is not configured: {parsed.root_key}"
        )
    root = Path(roots[parsed.root_key]).expanduser().resolve(strict=False)
    target = (root / PurePosixPath(parsed.relpath)).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("portable path escapes configured root") from exc
    return target


def resolve_source_path(paths: object, source: Mapping[str, object]) -> Path | None:
    """Resolve a persisted source row at the runtime I/O boundary."""
    logical = str(source.get("logical_source_id") or "")
    if logical.startswith("zotero:"):
        from . import zotero_tools

        key = logical.split(":", 1)[1]
        result = zotero_tools.resolve_pdf(key, paths)  # type: ignore[arg-type]
        if result.get("ok") and result.get("path"):
            return Path(str(result["path"]))
        return None
    external_ref = str(source.get("external_ref") or "")
    if external_ref:
        from . import config as cfg

        config = cfg.load_config(paths)  # type: ignore[arg-type]
        try:
            return resolve_ref(external_ref, configured_roots(config))
        except (ValueError, OSError):
            return None
    return None
