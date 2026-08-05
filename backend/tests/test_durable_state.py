from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml
from cryptography.fernet import Fernet

from curator import config as cfg
from curator import durable_io
from curator import secret_store


def _use_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_dir = tmp_path / "config"
    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: config_dir)
    return config_dir


def test_corrupt_secret_store_is_preserved_and_blocks_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = _use_config_dir(tmp_path, monkeypatch)
    store = config_dir / "secrets" / secret_store.STORE_FILE
    store.parent.mkdir(parents=True)
    corrupt = b'{"existing": '
    store.write_bytes(corrupt)

    with pytest.raises(durable_io.DurableStateError, match="secret store"):
        secret_store.set_secret("new", "value")

    assert store.read_bytes() == corrupt


def test_secret_mutations_serialize_without_losing_unrelated_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_config_dir(tmp_path, monkeypatch)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: secret_store.set_secret(f"key-{i}", f"value-{i}"), range(24)))

    assert {
        secret_store.get_secret(f"secret:key-{i}")
        for i in range(24)
    } == {f"value-{i}" for i in range(24)}


def test_interrupted_secret_replace_leaves_previous_store_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = _use_config_dir(tmp_path, monkeypatch)
    secret_store.set_secret("existing", "preserve-me")
    store = config_dir / "secrets" / secret_store.STORE_FILE
    original = store.read_bytes()

    monkeypatch.setattr(
        durable_io.os,
        "replace",
        lambda _source, _target: (_ for _ in ()).throw(OSError("interrupted replace")),
    )

    with pytest.raises(OSError, match="interrupted replace"):
        secret_store.set_secret("new", "must-not-clobber")

    assert store.read_bytes() == original
    assert not list(store.parent.glob(f".{store.name}.*.tmp"))


def test_global_config_updates_serialize_and_preserve_unrelated_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = _use_config_dir(tmp_path, monkeypatch)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(
            pool.map(
                lambda i: cfg.save_global_config({"concurrent": {f"key_{i}": i}}),
                range(32),
            )
        )

    stored = yaml.safe_load((config_dir / "config.yml").read_text(encoding="utf-8"))
    assert stored["concurrent"] == {f"key_{i}": i for i in range(32)}


def test_corrupt_global_config_is_preserved_and_blocks_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = _use_config_dir(tmp_path, monkeypatch)
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.yml"
    corrupt = b"llm: [unterminated"
    config_file.write_bytes(corrupt)

    with pytest.raises(durable_io.DurableStateError, match="config"):
        cfg.save_global_config({"llm": {"primary": "codex-cli::gpt-5.6-sol"}})

    assert config_file.read_bytes() == corrupt


def test_corrupt_project_config_is_preserved_and_blocks_mutation(
    tmp_path: Path,
) -> None:
    paths = cfg.WikiPaths(tmp_path / "vault")
    paths.internal.mkdir(parents=True)
    corrupt = b"version: [unterminated"
    paths.config_file.write_bytes(corrupt)

    with pytest.raises(durable_io.DurableStateError, match="config"):
        cfg.save_config(paths, {"version": 2})

    assert paths.config_file.read_bytes() == corrupt


def test_stale_project_save_merges_freshly_locked_peer_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_config_dir(tmp_path, monkeypatch)
    paths = cfg.WikiPaths(tmp_path / "vault")
    paths.internal.mkdir(parents=True)
    stale = {
        "version": 2,
        "sync": {"enabled": True, "metadata": {"local": "requested"}},
        "llm": {"provider": "local-only"},
        "search": {"embedding": "local-only"},
        "external": {"zotero": {"roots": ["/local-only"]}},
    }
    peer_current = {
        "version": 1,
        "sync": {
            "enabled": False,
            "metadata": {"peer": "arrived-after-load"},
        },
        "peer_only": {"device": "macos"},
        "llm": {"peer": "must-migrate-out"},
        "search": {"peer": "must-migrate-out"},
        "external": {"peer": "must-migrate-out"},
    }
    paths.config_file.write_text(yaml.safe_dump(peer_current), encoding="utf-8")

    cfg.save_config(paths, stale)

    stored = yaml.safe_load(paths.config_file.read_text(encoding="utf-8"))
    assert stored["version"] == 2
    assert stored["sync"] == {
        "enabled": True,
        "metadata": {"local": "requested", "peer": "arrived-after-load"},
    }
    assert stored["peer_only"] == {"device": "macos"}
    assert not ({"llm", "search", "external"} & stored.keys())


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode semantics")
def test_successful_config_replace_preserves_existing_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = _use_config_dir(tmp_path, monkeypatch)
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.yml"
    config_file.write_text("existing: true\n", encoding="utf-8")
    config_file.chmod(0o664)

    cfg.save_global_config({"new": {"value": 2}})

    assert stat.S_IMODE(config_file.stat().st_mode) == 0o664


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode semantics")
def test_new_config_uses_normal_process_umask(tmp_path: Path) -> None:
    script = """
import json
import os
import stat
import sys
from pathlib import Path
from curator.durable_io import atomic_write_text

root = Path(sys.argv[1])
os.umask(0o027)
control = root / "control.yml"
control.write_text("control: true\\n", encoding="utf-8")
target = root / "config.yml"
atomic_write_text(target, "config: true\\n")
print(json.dumps({
    "control": stat.S_IMODE(control.stat().st_mode),
    "target": stat.S_IMODE(target.stat().st_mode),
}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    modes = json.loads(completed.stdout)
    assert modes == {"control": 0o640, "target": 0o640}


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode semantics")
def test_secret_key_and_store_are_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = _use_config_dir(tmp_path, monkeypatch)

    secret_store.set_secret("private", "credential")

    secret_dir = config_dir / "secrets"
    assert stat.S_IMODE((secret_dir / secret_store.KEY_FILE).stat().st_mode) == 0o600
    assert stat.S_IMODE((secret_dir / secret_store.STORE_FILE).stat().st_mode) == 0o600


def test_interrupted_config_replace_leaves_previous_file_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = _use_config_dir(tmp_path, monkeypatch)
    cfg.save_global_config({"existing": {"value": 1}})
    config_file = config_dir / "config.yml"
    original = config_file.read_bytes()
    if os.name != "nt":
        config_file.chmod(0o664)

    monkeypatch.setattr(
        durable_io.os,
        "replace",
        lambda _source, _target: (_ for _ in ()).throw(OSError("interrupted replace")),
    )

    with pytest.raises(OSError, match="interrupted replace"):
        cfg.save_global_config({"new": {"value": 2}})

    assert config_file.read_bytes() == original
    if os.name != "nt":
        assert stat.S_IMODE(config_file.stat().st_mode) == 0o664
    assert not list(config_file.parent.glob(f".{config_file.name}.*.tmp"))


def test_secret_store_json_remains_a_mapping_after_concurrent_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = _use_config_dir(tmp_path, monkeypatch)
    secret_store.set_secret("one", "first")
    payload = json.loads(
        (config_dir / "secrets" / secret_store.STORE_FILE).read_text(encoding="utf-8")
    )
    assert isinstance(payload, dict)
    assert set(payload) == {"one"}


def test_secret_stored_but_undecryptable_is_not_reported_as_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A synced config references a secret whose ciphertext this key cannot open.

    The encryption key is machine-local and never syncs, so this is the ordinary
    outcome of this project's own cross-device config sync. Returning "" made it
    indistinguishable from "no secret stored", and the provider then told the
    user their API key was not configured — sending them to re-check an env var
    that was never the problem.
    """
    config_dir = _use_config_dir(tmp_path, monkeypatch)
    secret_store.set_secret("deepseek-api-key", "sk-real-value")

    # Simulate arriving on another machine: same store file, different key.
    key_path = config_dir / "secrets" / secret_store.KEY_FILE
    key_path.write_bytes(Fernet.generate_key() + b"\n")

    with pytest.raises(secret_store.SecretDecryptionError) as excinfo:
        secret_store.get_secret("secret:deepseek-api-key")

    message = str(excinfo.value)
    assert "deepseek-api-key" in message
    assert "cannot be decrypted on this machine" in message
    assert "wiki config provider --api-key" in message

    # A name that was never stored still reads as absent, not as a failure.
    assert secret_store.get_secret("secret:never-stored") == ""


def test_listing_secrets_survives_one_undecryptable_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = _use_config_dir(tmp_path, monkeypatch)
    secret_store.set_secret("stale", "sk-from-another-machine")
    key_path = config_dir / "secrets" / secret_store.KEY_FILE
    key_path.write_bytes(Fernet.generate_key() + b"\n")
    secret_store.set_secret("fresh", "sk-local-value")

    listed = secret_store.list_secrets()

    assert listed["secret:stale"] == "<undecryptable>"
    assert listed["secret:fresh"] == "sk-l...alue"
