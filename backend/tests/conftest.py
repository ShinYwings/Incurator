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


@pytest.fixture(autouse=True)
def block_real_provider_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if a test spawns a real provider CLI.

    `cfg.DEFAULT_CONFIG` sets `llm.primary = "antigravity-cli::..."`, so any test
    that saves the default config and then builds a client runs the **user's own
    `agy`**, against their account and their quota. It was happening: `ps` during
    a full-suite run showed real `agy` processes whose parent was pytest and
    whose `--log-file` pointed into `pytest-of-shin/pytest-1047/...`. The user
    noticed before the test suite did, because nothing in the suite was watching.

    Same shape as `isolate_home_dir` above, one level worse: that one wrote the
    developer's files, this one spends their money and touches an external
    account. A test that wants to exercise a CLI client must patch
    `subprocess.run` itself — which is what the ones that already do this
    correctly do — and this guard is what makes forgetting it loud instead of
    silent.
    """
    import subprocess

    real_run = subprocess.run
    blocked = {"agy", "claude", "codex", "gemini", "ollama"}

    def guarded_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        name = ""
        if isinstance(cmd, (list, tuple)) and cmd:
            name = Path(str(cmd[0])).name
        elif isinstance(cmd, str):
            name = Path(cmd.split()[0]).name if cmd.split() else ""
        if name in blocked:
            raise AssertionError(
                f"A test tried to run the real {name!r} CLI. That spends the "
                f"user's own provider account. Patch `subprocess.run` (or the "
                f"client) in this test instead. Command: {cmd!r}"
            )
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", guarded_run)
