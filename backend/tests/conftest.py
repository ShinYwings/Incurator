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
    import os
    import subprocess

    # One test is BUILT to hit the real CLI, behind its own explicit opt-in:
    # `test_structured_output.py::test_live_...` is skipped unless
    # `INCURATOR_LIVE_AGY=1`, and it deliberately does not patch `subprocess.run`
    # because asserting what the CLI actually accepts is its whole purpose.
    # `skipif` does not stop fixtures from running when the flag IS set, so
    # without this carve-out the guard would silently break the one test the flag
    # exists to enable.
    if os.environ.get("INCURATOR_LIVE_AGY"):
        return

    real_run = subprocess.run
    real_popen = subprocess.Popen
    blocked = {"agy", "claude", "codex", "gemini", "ollama"}

    def _blocked_name(cmd) -> str:  # type: ignore[no-untyped-def]
        name = ""
        if isinstance(cmd, (list, tuple)) and cmd:
            name = Path(str(cmd[0])).name
        elif isinstance(cmd, str):
            name = Path(cmd.split()[0]).name if cmd.split() else ""
        return name if name in blocked else ""

    def guarded_popen(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        # `Popen`, not just `run`: `ensure_ollama_serving` and
        # `_ensure_ollama_running` start a real detached `ollama serve` this way.
        # Guarding only `run` would leave the background-daemon path open, which
        # is the harder one to notice — it survives the test that started it.
        name = _blocked_name(cmd)
        if name:
            raise AssertionError(
                f"A test tried to start the real {name!r} CLI in the background. "
                f"That spends the user's own provider account and leaves a "
                f"process running. Patch `subprocess.Popen` in this test. "
                f"Command: {cmd!r}"
            )
        return real_popen(cmd, *args, **kwargs)

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
    monkeypatch.setattr(subprocess, "Popen", guarded_popen)
