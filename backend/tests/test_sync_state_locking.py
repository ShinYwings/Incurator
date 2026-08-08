"""Device sync state is a serialized read-modify-write (B2 / sync_db-4).

`read_sync_state` → mutate → `write_sync_state` ran unlocked at four sites, so
two concurrent passes could interleave. Two measured consequences:

- **Split device identity.** `get_device_id` mints an id when none exists. Two
  callers racing both mint, one wins, and the loser writes
  `dev-<its-id>.jsonl` into the synced directory. Every other device then sees a
  peer that exists only in that filename and never exports again — a permanently
  stale phantom.
- **Lost update.** Two sections read the same base and the last writer wins,
  silently dropping the other's key. Losing `peers` forgets a checkpoint and
  re-imports that peer's whole snapshot; losing `last_export_ts` re-fires the
  export gate.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from curator import db_sync


@pytest.fixture()
def internal(tmp_path: Path) -> Path:
    d = tmp_path / ".curator"
    d.mkdir(parents=True)
    return d


def test_concurrent_get_device_id_yields_one_identity(internal: Path) -> None:
    """Every caller must receive the id that is actually persisted."""
    handed_out: list[str] = []
    barrier = threading.Barrier(4)

    def mint() -> None:
        barrier.wait()
        handed_out.append(db_sync.get_device_id(internal))

    threads = [threading.Thread(target=mint) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    persisted = db_sync.read_sync_state(internal)["device_id"]
    assert set(handed_out) == {persisted}, (
        f"callers received {sorted(set(handed_out))} but the device persisted "
        f"{persisted!r}; the losing id becomes a phantom peer file that every "
        f"other device imports forever"
    )


def test_concurrent_state_updates_do_not_drop_each_other(internal: Path) -> None:
    """Two independent keys written concurrently must both survive."""
    db_sync.write_sync_state(internal, {"device_id": "dev1"})
    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def update(key: str, value: object) -> None:
        try:
            barrier.wait()
            with db_sync.sync_state_transaction(internal) as state:
                state[key] = value
        except Exception as exc:  # pragma: no cover - surfaced by the assert
            errors.append(exc)

    a = threading.Thread(
        target=update, args=("last_export_ts", "2099-01-01T00:00:00Z")
    )
    b = threading.Thread(
        target=update, args=("peers", {"dev-x.jsonl": {"last_export_id": "e1"}})
    )
    a.start(); b.start(); a.join(); b.join()

    assert not errors, errors
    state = db_sync.read_sync_state(internal)
    assert "last_export_ts" in state and "peers" in state, (
        f"a concurrent update was silently dropped: {sorted(state)}"
    )


def test_transaction_rereads_inside_the_lock(internal: Path) -> None:
    """A transaction must not act on state captured before it acquired the lock."""
    db_sync.write_sync_state(internal, {"device_id": "dev1"})

    with db_sync.sync_state_transaction(internal) as state:
        state["last_export_ts"] = "2099-01-01T00:00:00Z"

    # An outer transaction opened afterwards must observe the committed value.
    with db_sync.sync_state_transaction(internal) as state:
        assert state.get("last_export_ts") == "2099-01-01T00:00:00Z"


def test_a_failed_transaction_leaves_state_untouched(internal: Path) -> None:
    db_sync.write_sync_state(internal, {"device_id": "dev1"})
    with pytest.raises(RuntimeError):
        with db_sync.sync_state_transaction(internal) as state:
            state["last_export_ts"] = "2099-01-01T00:00:00Z"
            raise RuntimeError("boom")
    assert "last_export_ts" not in db_sync.read_sync_state(internal)


def test_device_id_is_stable_across_calls(internal: Path) -> None:
    first = db_sync.get_device_id(internal)
    assert db_sync.get_device_id(internal) == first
