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

    # Wrappers that PRECEDE the real command. v0.76.0 began wrapping the agy
    # spawn in `sandbox-exec`/`bwrap`, which moved the CLI's name off argv[0] —
    # and this guard, which only looked at argv[0], stopped seeing it. Tests
    # started spending the user's provider account again, and they noticed before
    # the suite did, for the second time. Scanning every argument is the fix: a
    # guard that only inspects one position is defeated by anything that shifts
    # it.
    wrappers = {"sandbox-exec", "bwrap", "env", "nice", "timeout", "stdbuf"}

    def _blocked_name(cmd) -> str:  # type: ignore[no-untyped-def]
        if isinstance(cmd, str):
            parts = cmd.split()
        elif isinstance(cmd, (list, tuple)):
            parts = [str(c) for c in cmd]
        else:
            return ""
        for part in parts:
            name = Path(part).name
            if name in blocked:
                return name
            if name in wrappers or part.startswith("-"):
                continue
        return ""

    class guarded_popen(real_popen):  # type: ignore[misc,valid-type]
        """Guard `Popen`, not just `run`.

        `ensure_ollama_serving` and `_ensure_ollama_running` start a real
        detached `ollama serve` this way, and guarding only `run` would leave the
        background-daemon path open — the harder one to notice, because it
        survives the test that started it.

        A SUBCLASS, not a function. Replacing `subprocess.Popen` with a plain
        function breaks every library that writes `subprocess.Popen[bytes]` as a
        type annotation evaluated at runtime — the installed `mcp` package does
        exactly that, and the substitution turned an unrelated test into
        `TypeError: 'function' object is not subscriptable`. A guard that breaks
        the code it is watching over is worse than no guard.
        """

        def __init__(self, cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
            name = _blocked_name(cmd)
            if name:
                raise AssertionError(
                    f"A test tried to start the real {name!r} CLI in the "
                    f"background. That spends the user's own provider account "
                    f"and leaves a process running. Patch `subprocess.Popen` in "
                    f"this test. Command: {cmd!r}"
                )
            super().__init__(cmd, *args, **kwargs)

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
