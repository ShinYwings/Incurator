"""Fail-closed, serialized atomic writes for durable local state."""

from __future__ import annotations

import hashlib
import importlib
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class DurableStateError(RuntimeError):
    """Raised when existing durable state cannot be safely read or updated."""


_lock_guard = threading.Lock()
_path_locks: dict[str, threading.RLock] = {}
_fcntl = importlib.import_module("fcntl") if os.name != "nt" else None


def _thread_lock(path: Path) -> threading.RLock:
    key = str(path.expanduser().resolve(strict=False))
    with _lock_guard:
        return _path_locks.setdefault(key, threading.RLock())


def _lock_file(path: Path) -> Path:
    key = str(path.expanduser().resolve(strict=False)).encode("utf-8")
    digest = hashlib.sha256(key).hexdigest()
    directory = Path(tempfile.gettempdir()) / "incurator-state-locks"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{digest}.lock"


@contextmanager
def locked_path(path: Path) -> Iterator[None]:
    """Serialize read-modify-write operations for one resolved target path."""

    with _thread_lock(path):
        lock_file = _lock_file(path)
        with lock_file.open("a+b") as handle:
            if _fcntl is not None:
                _fcntl.flock(handle.fileno(), _fcntl.LOCK_EX)
            try:
                yield
            finally:
                if _fcntl is not None:
                    _fcntl.flock(handle.fileno(), _fcntl.LOCK_UN)


def atomic_write_text(path: Path, text: str, *, mode: int | None = None) -> None:
    """Replace ``path`` atomically, retaining the old bytes if replacement fails."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
