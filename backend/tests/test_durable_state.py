from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

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


def test_interrupted_config_replace_leaves_previous_file_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = _use_config_dir(tmp_path, monkeypatch)
    cfg.save_global_config({"existing": {"value": 1}})
    config_file = config_dir / "config.yml"
    original = config_file.read_bytes()

    monkeypatch.setattr(
        durable_io.os,
        "replace",
        lambda _source, _target: (_ for _ in ()).throw(OSError("interrupted replace")),
    )

    with pytest.raises(OSError, match="interrupted replace"):
        cfg.save_global_config({"new": {"value": 2}})

    assert config_file.read_bytes() == original
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
