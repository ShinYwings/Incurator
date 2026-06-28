"""XC-1 slice 1: error-handling narrowing for config.py.

Verifies that the previously-broad ``except Exception`` handlers around config
reads now (a) still degrade gracefully on the *expected* failure types and
(b) let *unexpected* errors propagate instead of being silently swallowed.
"""

import logging
from pathlib import Path

import pytest

from curator import config as cfg
from curator import constants as consts


def _make_vault(tmp_path: Path, settings_body: str) -> Path:
    vault = tmp_path / "vault"
    (vault / consts.INTERNAL_DIR).mkdir(parents=True)
    (vault / consts.INTERNAL_DIR / consts.SETTINGS_FILE).write_text(
        settings_body, encoding="utf-8"
    )
    return vault


def test_find_wiki_root_tolerates_malformed_settings(tmp_path, caplog):
    # Malformed settings YAML must not crash the upward scan; the candidate is
    # still returned (treated as non-testbed) and the failure is logged.
    vault = _make_vault(tmp_path, "testbed: [unclosed")  # invalid YAML

    with caplog.at_level(logging.DEBUG, logger="curator.config"):
        found = cfg.find_wiki_root(start=vault)

    assert found == vault
    assert any("scanning for project root" in r.message for r in caplog.records)


def test_find_wiki_root_tolerates_non_dict_settings(tmp_path, caplog):
    # Valid YAML that is a list (not a dict) → .get() would AttributeError; the
    # scan must still return the candidate, treating it as non-testbed.
    vault = _make_vault(tmp_path, "- a\n- b\n")

    with caplog.at_level(logging.DEBUG, logger="curator.config"):
        assert cfg.find_wiki_root(start=vault) == vault


def test_find_wiki_root_propagates_unexpected_errors(tmp_path, monkeypatch):
    # A non-(OSError/YAMLError) failure while reading settings must propagate now
    # rather than being swallowed by the old broad ``except Exception: pass``.
    vault = _make_vault(tmp_path, "testbed: true")
    orig_read_text = Path.read_text

    def boom(self, *args, **kwargs):
        if self.name == consts.SETTINGS_FILE:
            raise RecursionError("unexpected")
        return orig_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", boom)

    with pytest.raises(RecursionError):
        cfg.find_wiki_root(start=vault)


def test_load_config_tolerates_non_dict_global_config(tmp_path, monkeypatch, caplog):
    # A global config.yml that is valid YAML but a list (not a dict) → .items()
    # would AttributeError on startup; load_config must degrade to defaults.
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    (global_dir / consts.FILE_GLOBAL_CONFIG_YML).write_text("- one\n- two\n", encoding="utf-8")
    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: global_dir)

    vault = tmp_path / "vault"
    (vault / consts.INTERNAL_DIR).mkdir(parents=True)
    paths = cfg.WikiPaths(vault)

    with caplog.at_level(logging.WARNING, logger="curator.config"):
        merged = cfg.load_config(paths)  # must not raise
    assert isinstance(merged, dict)
    assert any("using defaults" in r.message for r in caplog.records)


def test_get_last_root_logs_and_returns_none_on_bad_read(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: tmp_path)
    marker = tmp_path / consts.FILE_LAST_ROOT
    marker.write_text("/some/path", encoding="utf-8")

    orig_read_text = Path.read_text

    def boom(self, *args, **kwargs):
        if self.name == consts.FILE_LAST_ROOT:
            raise OSError("disk gone")
        return orig_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", boom)

    with caplog.at_level(logging.DEBUG, logger="curator.config"):
        assert cfg.get_last_root() is None
    assert any("last-root file" in r.message for r in caplog.records)
