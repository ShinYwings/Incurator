"""Fail-closed, serialized atomic writes for durable local state."""

from __future__ import annotations

import hashlib
import importlib
import os
import secrets
import stat
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class DurableStateError(RuntimeError):
    """Raised when existing durable state cannot be safely read or updated."""


_lock_guard = threading.Lock()
_path_locks: dict[str, threading.RLock] = {}
#: Re-entrancy depth per (thread, path). The thread RLock below already permits
#: re-entry, but `flock` is per file descriptor: a nested acquisition opens a
#: SECOND descriptor and `LOCK_EX` on it blocks against the first, from the same
#: process, forever. Only the outermost acquisition may take the file lock.
_lock_depth = threading.local()
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

    key = str(path.expanduser().resolve(strict=False))
    depths: dict[str, int] = getattr(_lock_depth, "depths", None) or {}
    _lock_depth.depths = depths

    with _thread_lock(path):
        if depths.get(key, 0):
            # Already held further up this call stack. Re-entering is safe;
            # taking `flock` again would deadlock against ourselves.
            depths[key] += 1
            try:
                yield
            finally:
                depths[key] -= 1
            return

        lock_file = _lock_file(path)
        with lock_file.open("a+b") as handle:
            if _fcntl is not None:
                _fcntl.flock(handle.fileno(), _fcntl.LOCK_EX)
            depths[key] = 1
            try:
                yield
            finally:
                depths[key] = 0
                if _fcntl is not None:
                    _fcntl.flock(handle.fileno(), _fcntl.LOCK_UN)


def atomic_write_text(path: Path, text: str, *, mode: int | None = None) -> None:
    """Replace ``path`` atomically, retaining the old bytes if replacement fails."""

    path.parent.mkdir(parents=True, exist_ok=True)
    selected_mode = mode
    if selected_mode is None:
        try:
            selected_mode = stat.S_IMODE(path.stat().st_mode)
        except FileNotFoundError:
            selected_mode = None

    create_mode = selected_mode if selected_mode is not None else 0o666
    descriptor = -1
    temp_path: Path | None = None
    for _attempt in range(128):
        candidate = path.parent / f".{path.name}.{secrets.token_hex(12)}.tmp"
        try:
            descriptor = os.open(
                candidate,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                create_mode,
            )
            temp_path = candidate
            break
        except FileExistsError:
            continue
    if temp_path is None:
        raise FileExistsError(f"could not create a unique temporary sibling for {path}")

    try:
        handle = os.fdopen(descriptor, "w", encoding="utf-8")
        descriptor = -1
        with handle:
            handle.write(text)
            handle.flush()
            if selected_mode is not None and os.name != "nt":
                os.fchmod(handle.fileno(), selected_mode)
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
