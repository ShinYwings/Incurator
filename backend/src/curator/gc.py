"""Retention: what may be reclaimed, and — just as important — what may not.

ROADMAP B2. The vault accumulates byproducts with no rule for removing them, and
the honest finding while scoping this was that **most of the growth cannot be
safely deleted at all**:

`prompt_runs`, `query_traces`, `compiler_generations` and `deleted_records` are
all in `db_sync.SYNC_TABLES`, and exports are full snapshots. So deleting a row
from any of them has exactly two outcomes: with a tombstone it propagates to
every device the user owns, and without one the next import re-inserts it. There
is no quietly-local delete.

`deleted_records` is worse than merely synced. It IS the tombstone table — the
only thing stopping a peer's snapshot from resurrecting a deleted row — and
nothing in this codebase tracks whether every peer has seen a given tombstone
(`sync_state.json` records an mtime per journal file, never an acknowledgement).
Expiring one early silently resurrects deleted data on the next import from a
device that was offline.

So this module reclaims ONLY what carries no cross-device meaning, and reports
the rest with the reason it is being left alone. A GC that quietly turns local
tidying into fleet-wide deletion would be a far worse bug than the disk it saves.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db, durable_io

#: A cache directory is only swept when its vault root is under one of these.
#:
#: The obvious rule — "the `vault_root` path no longer exists, so the cache is
#: dead" — is a MOUNT test, not a liveness test. `get_vault_cache_dir` resolves
#: with `strict=False`, so an unmounted external drive or a disconnected network
#: share hashes to exactly the same directory name and reads as missing. That
#: directory holds `state.sqlite`, the single source of truth — 287 MB on the
#: reference vault. Deleting it because a drive was unplugged would destroy the
#: user's knowledge base.
#:
#: Every one of the 25 dead directories measured on the reference machine was
#: test debris under a temp root, so restricting the sweep to temp prefixes costs
#: nothing real and removes the entire class of catastrophic misfire.
_TEMP_ROOT_PREFIXES = ("/tmp/", "/private/tmp/", "/var/folders/", "/private/var/folders/")


@dataclass
class Reclaimable:
    """One thing the GC would remove."""

    path: Path
    bytes: int
    reason: str


@dataclass
class Retained:
    """One thing that grows and is deliberately NOT removed."""

    label: str
    amount: str
    reason: str


@dataclass
class GcPlan:
    reclaimable: list[Reclaimable] = field(default_factory=list)
    retained: list[Retained] = field(default_factory=list)

    @property
    def bytes_reclaimable(self) -> int:
        return sum(item.bytes for item in self.reclaimable)


def _dir_bytes(path: Path) -> int:
    total = 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


def _is_temp_root(root: str) -> bool:
    return any(root.startswith(prefix) for prefix in _TEMP_ROOT_PREFIXES)


def dead_vault_caches(cache_root: Path) -> list[Reclaimable]:
    """Per-vault cache directories that are provably debris.

    THREE conditions, all required. Any one alone is unsafe:

    1. the recorded `vault_root` path is absent — necessary, but only a mount test;
    2. that root is under a temp prefix — this is what makes (1) trustworthy,
       because a temp directory does not come back when a drive is remounted;
    3. the cached database holds zero sources — a directory with real ingested
       work is never debris, whatever its path says.
    """
    found: list[Reclaimable] = []
    vaults = cache_root / "vaults"
    if not vaults.is_dir():
        return found

    for entry in sorted(vaults.iterdir()):
        if not entry.is_dir():
            continue
        marker = entry / "vault_root"
        try:
            root = marker.read_text(encoding="utf-8").strip()
        except OSError:
            # No marker at all: cannot prove it is debris, so leave it.
            continue
        if not root or Path(root).exists():
            continue
        if not _is_temp_root(root):
            continue
        state_db = entry / "state.sqlite"
        if state_db.exists():
            try:
                if int(db.get_stats(state_db).get("sources_total") or 0) > 0:
                    continue
            except Exception:
                # A database we cannot read is not provably empty.
                continue
        found.append(
            Reclaimable(
                path=entry,
                bytes=_dir_bytes(entry),
                reason=f"temp vault no longer on disk: {root}",
            )
        )
    return found


def sweep(items: list[Reclaimable]) -> tuple[int, int]:
    """Delete the planned items. Returns (removed, bytes_freed)."""
    removed = 0
    freed = 0
    for item in items:
        try:
            shutil.rmtree(item.path)
        except OSError:
            continue
        removed += 1
        freed += item.bytes
    return removed, freed


def _row_count(state_db: Path, table: str) -> int:
    try:
        with db.connect(state_db) as conn:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except Exception:
        return 0


def _human(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} GB"


def build_plan(paths, cache_root: Path) -> GcPlan:
    """What can be reclaimed, and what grows but is deliberately kept.

    The second list is the point. Every item on it is something a naive
    retention policy would delete, with the reason it must not — so the user can
    see the growth AND why the tool is refusing, rather than concluding nothing
    is wrong.
    """
    plan = GcPlan(reclaimable=dead_vault_caches(cache_root))

    state_db = paths.state_db
    tombstones = _row_count(state_db, "deleted_records")
    if tombstones:
        plan.retained.append(
            Retained(
                "deleted_records",
                f"{tombstones:,} rows",
                "tombstones — the only thing stopping a peer's snapshot from "
                "resurrecting a deleted row. Nothing here records whether every "
                "device has synced (sync_state.json holds an mtime per file, not "
                "an acknowledgement), so expiring one silently restores deleted "
                "data on the next import from a device that was offline.",
            )
        )
    for table, note in (
        ("prompt_runs", "also how a finished L3 report proves it need not be regenerated"),
        ("query_traces", "also resolves live context packs"),
        ("compiler_generations", "the publish log; the ledger's dates come from it"),
    ):
        rows = _row_count(state_db, table)
        if rows:
            plan.retained.append(
                Retained(
                    table,
                    f"{rows:,} rows",
                    f"synced across devices — deleting propagates everywhere, and "
                    f"deleting without a tombstone is undone by the next import. "
                    f"({note}.)",
                )
            )

    sync_dir = paths.internal / "sync"
    if sync_dir.is_dir():
        size = _dir_bytes(sync_dir)
        if size:
            plan.retained.append(
                Retained(
                    ".curator/sync",
                    _human(size),
                    "the documented recovery path when the local database is "
                    "lost or the vault is renamed. A peer's journal is the only "
                    "copy of that peer's view.",
                )
            )

    sessions = paths.internal / "sessions.json"
    if sessions.exists():
        try:
            size = sessions.stat().st_size
        except OSError:
            size = 0
        if size:
            plan.retained.append(
                Retained(
                    ".curator/sessions.json",
                    _human(size),
                    "your own writing, and synced — its deleted-session list has "
                    "the same resurrection hazard as the tombstone table.",
                )
            )
    return plan


#: Chat-retention choices offered to the user. `0` means keep forever, and is the
#: default: this is the user's own writing, so a timer never removes it unless
#: they choose one.
SESSION_RETENTION_CHOICES = (0, 30, 90, 180, 365)


def _session_retention_days(config: dict) -> int:
    raw = ((config or {}).get("gc") or {}).get("sessions_retention_days", 0)
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return 0
    return days if days > 0 else 0


def plan_session_prune(paths, config: dict, *, now: datetime | None = None) -> tuple[int, int]:
    """(sessions that would be removed, bytes the file currently occupies).

    Read-only. Returns (0, size) when retention is off, which is the default.
    """
    days = _session_retention_days(config)
    path = paths.internal / "sessions.json"
    if not path.exists():
        return 0, 0
    try:
        size = path.stat().st_size
    except OSError:
        return 0, 0
    if days <= 0:
        return 0, size
    doomed, _kept, _tombstones = _split_sessions(path, days, now)
    return len(doomed), size


def _split_sessions(
    path: Path, days: int, now: datetime | None
) -> tuple[list[dict], list[dict], dict]:
    """Sessions older than the window, those kept, and the tombstone id list."""
    import json

    reference = now or datetime.now(timezone.utc)
    cutoff_ms = (reference - timedelta(days=days)).timestamp() * 1000.0
    data = json.loads(path.read_text(encoding="utf-8"))
    sessions = data.get("chatSessions") or []
    doomed: list[dict] = []
    kept: list[dict] = []
    for session in sessions:
        stamp = session.get("updatedAt") or session.get("createdAt") or 0
        try:
            stamp = float(stamp)
        except (TypeError, ValueError):
            stamp = 0.0
        # A session with no usable timestamp is KEPT. Deleting on a missing
        # field would silently remove the oldest data, which is exactly what a
        # user choosing a window does not expect.
        (doomed if stamp and stamp < cutoff_ms else kept).append(session)
    return doomed, kept, data


def prune_sessions(paths, config: dict, *, now: datetime | None = None) -> int:
    """Remove chat sessions past the retention window. Returns sessions removed.

    Writes a tombstone for every removed session. That is not optional: the
    plugin's merge re-seeds from whatever is on disk and from peers, so a prune
    without tombstones is undone on the next save. It also means the removal
    reaches every device -- which is what a retention window means, and why the
    default is to keep and the CLI states it before deleting.
    """
    import json

    days = _session_retention_days(config)
    path = paths.internal / "sessions.json"
    if days <= 0 or not path.exists():
        return 0

    doomed, kept, data = _split_sessions(path, days, now)
    if not doomed:
        return 0

    tombstones = list(data.get("deletedSessionIds") or [])
    seen = set(tombstones)
    for session in doomed:
        sid = session.get("id")
        if sid and sid not in seen:
            tombstones.append(sid)
            seen.add(sid)

    data["chatSessions"] = kept
    data["deletedSessionIds"] = tombstones
    active = data.get("activeChatSessionId")
    if active and any(s.get("id") == active for s in doomed):
        data["activeChatSessionId"] = kept[0]["id"] if kept else None

    durable_io.atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))
    return len(doomed)
