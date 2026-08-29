from pathlib import Path

import pytest

from curator import config as cfg


@pytest.fixture(autouse=True)
def isolate_global_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep CLI tests from writing repo-local .cache/config state."""
    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: tmp_path / "global_config")


@pytest.fixture(autouse=True)
def isolate_home_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests from writing the developer's real home directory.

    `wiki init` calls `_sync_mcp_configs`, which registers the MCP server under
    `~/.gemini/`. Any test that runs `init` without patching home therefore
    rewrites the developer's actual agy configuration — and it did: the real
    `~/.gemini/config/mcp_config.json` was found pointing `VAULT_ROOT` at
    `/private/var/folders/.../pytest-of-shin/pytest-1030/...`, a deleted pytest
    temp directory, which leaves agy registered against a vault that no longer
    exists.

    Patching the individual offender would leave the next one free to do it
    again, so the guard goes here, once, for every test. `Path.home()` reads
    `HOME` on POSIX, but it is also patched directly because callers import
    `Path` themselves and `pathlib` caches nothing we can rely on.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
