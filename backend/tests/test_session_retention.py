"""ROADMAP B2: chat retention, with the one fact that makes it a real choice.

The user asked for a selectable window on `sessions.json`. Building it surfaced
what that actually means: the plugin's merge re-seeds from whatever is on disk
and from peers, so a prune WITHOUT a tombstone is undone on the next save. With
one, the removal reaches every device.

That is not a hazard to be engineered away — it is what a retention window means,
and it is what ChatGPT and Google Chat do. What it does require is that the
default be **keep**, that the window be the user's explicit choice, and that the
CLI say "every device" before it deletes anything.

`writeMergedSessionStore` re-reads the canonical file and `mergeSessionData`
unions `deletedSessionIds` from both sides, so a tombstone the backend writes
survives the plugin's next save. That is why the backend may prune this file at
all.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from curator import config as cfg
from curator.gc import plan_session_prune, prune_sessions

NOW = datetime(2026, 8, 24, tzinfo=timezone.utc)


def _ms(days_ago: int) -> float:
    return (NOW - timedelta(days=days_ago)).timestamp() * 1000.0


def _vault(tmp_path: Path, sessions: list[dict], deleted: list[str] | None = None):
    paths = cfg.WikiPaths(tmp_path / "vault")
    paths.internal.mkdir(parents=True, exist_ok=True)
    (paths.internal / "sessions.json").write_text(
        json.dumps({
            "chatSessions": sessions,
            "activeChatSessionId": sessions[0]["id"] if sessions else None,
            "deletedSessionIds": deleted or [],
        }),
        encoding="utf-8",
    )
    return paths


def _read(paths) -> dict:
    return json.loads((paths.internal / "sessions.json").read_text(encoding="utf-8"))


def _session(sid: str, days_ago: int) -> dict:
    return {"id": sid, "title": sid, "createdAt": _ms(days_ago), "updatedAt": _ms(days_ago),
            "messages": [{"id": "m", "role": "user", "content": "hi"}]}


def test_keep_is_the_default_and_removes_nothing(tmp_path: Path) -> None:
    """Their own writing. A timer never touches it unless they choose one."""
    paths = _vault(tmp_path, [_session("old", 400), _session("new", 1)])

    assert prune_sessions(paths, {}, now=NOW) == 0
    assert len(_read(paths)["chatSessions"]) == 2


def test_a_chosen_window_removes_only_what_is_past_it(tmp_path: Path) -> None:
    paths = _vault(tmp_path, [_session("old", 120), _session("recent", 10)])

    removed = prune_sessions(paths, {"gc": {"sessions_retention_days": 90}}, now=NOW)

    data = _read(paths)
    assert removed == 1
    assert [s["id"] for s in data["chatSessions"]] == ["recent"]


def test_a_removed_session_is_tombstoned_or_it_comes_back(tmp_path: Path) -> None:
    """Without the tombstone the plugin's merge re-seeds it from disk or a peer
    and the prune is silently undone."""
    paths = _vault(tmp_path, [_session("old", 120)])

    prune_sessions(paths, {"gc": {"sessions_retention_days": 90}}, now=NOW)

    assert "old" in _read(paths)["deletedSessionIds"]


def test_a_session_with_no_usable_timestamp_is_kept(tmp_path: Path) -> None:
    """Deleting on a missing field would silently remove the oldest data, which
    is the opposite of what choosing a window means."""
    paths = _vault(tmp_path, [{"id": "undated", "title": "t", "messages": []}])

    assert prune_sessions(paths, {"gc": {"sessions_retention_days": 30}}, now=NOW) == 0
    assert [s["id"] for s in _read(paths)["chatSessions"]] == ["undated"]


def test_the_active_session_pointer_never_dangles(tmp_path: Path) -> None:
    paths = _vault(tmp_path, [_session("old", 200), _session("recent", 2)])
    with open(paths.internal / "sessions.json", encoding="utf-8") as fh:
        data = json.load(fh)
    data["activeChatSessionId"] = "old"
    (paths.internal / "sessions.json").write_text(json.dumps(data), encoding="utf-8")

    prune_sessions(paths, {"gc": {"sessions_retention_days": 90}}, now=NOW)

    after = _read(paths)
    assert after["activeChatSessionId"] == "recent"


def test_existing_tombstones_are_preserved(tmp_path: Path) -> None:
    """They are the peer-resurrection guard; dropping one restores a deleted chat."""
    paths = _vault(tmp_path, [_session("old", 120)], deleted=["earlier"])

    prune_sessions(paths, {"gc": {"sessions_retention_days": 90}}, now=NOW)

    assert set(_read(paths)["deletedSessionIds"]) == {"earlier", "old"}


def test_plan_is_read_only(tmp_path: Path) -> None:
    paths = _vault(tmp_path, [_session("old", 120), _session("recent", 1)])

    count, size = plan_session_prune(paths, {"gc": {"sessions_retention_days": 90}}, now=NOW)

    assert count == 1 and size > 0
    assert len(_read(paths)["chatSessions"]) == 2, "plan must not delete"


def test_a_corrupt_store_is_reported_not_crashed_or_overwritten(tmp_path: Path) -> None:
    """Found reviewing the merged v0.70.0 rather than while writing it.

    A `sessions.json` that will not parse raised `JSONDecodeError` straight out
    of `wiki gc plan` — read-only reporting that should never fail — and took the
    unrelated cache sweep down with it. Worse in principle: the backend must
    never be the component that rewrites a store it cannot read, because that
    destroys whatever the file still holds. The plugin already treats a corrupt
    store as a first-class state and fails closed.
    """
    import pytest

    from curator.gc import UnreadableSessionStore, plan_session_prune, prune_sessions

    paths = cfg.WikiPaths(tmp_path / "vault")
    paths.internal.mkdir(parents=True, exist_ok=True)
    broken = paths.internal / "sessions.json"
    broken.write_text("{ this is not json", encoding="utf-8")
    before = broken.read_bytes()
    policy = {"gc": {"sessions_retention_days": 30}}

    count, size = plan_session_prune(paths, policy)
    assert size > 0, "plan must report, not raise"
    assert count == -1, (
        "an unreadable store returned 0, which is what a healthy store past no "
        "sessions returns -- SYSTEM_BEHAVIOR §32: false success is forbidden"
    )

    with pytest.raises(UnreadableSessionStore):
        prune_sessions(paths, policy)

    assert broken.read_bytes() == before, "an unreadable store was rewritten"


def test_a_wrong_shaped_store_is_treated_the_same(tmp_path: Path) -> None:
    """Valid JSON is not the same as a session store. A list reached
    `data.get(...)` and raised AttributeError."""
    import pytest

    from curator.gc import UnreadableSessionStore, prune_sessions

    paths = cfg.WikiPaths(tmp_path / "vault")
    paths.internal.mkdir(parents=True, exist_ok=True)
    (paths.internal / "sessions.json").write_text(json.dumps(["not", "a", "store"]), encoding="utf-8")

    with pytest.raises(UnreadableSessionStore):
        prune_sessions(paths, {"gc": {"sessions_retention_days": 30}})


def test_a_malformed_session_entry_does_not_take_the_prune_down(tmp_path: Path) -> None:
    """One bad entry must not block retention on the rest, nor be deleted for
    being unparseable."""
    paths = _vault(tmp_path, [_session("old", 120)])
    data = json.loads((paths.internal / "sessions.json").read_text(encoding="utf-8"))
    data["chatSessions"].append("a string, somehow")
    (paths.internal / "sessions.json").write_text(json.dumps(data), encoding="utf-8")

    removed = prune_sessions(paths, {"gc": {"sessions_retention_days": 90}}, now=NOW)

    assert removed == 1
