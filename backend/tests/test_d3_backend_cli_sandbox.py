"""D3: the backend spawned `agy` with no OS containment at all.

`AntigravityCliClient._run` used a plain `subprocess.run`, unlike
`CodexCliClient`, which passes `--sandbox read-only`. It also set
`ANTIGRAVITY_TRUST_WORKSPACE` / `AGY_TRUST_WORKSPACE`.

That was latent while the read permission was broken. v0.56.1 fixed the
permission — it had to, the vision path was dead without it — so the backend now
spawns an uncontained CLI on the code path that processes **ingested, untrusted
source material**.

**Be exact about what this buys.** The plugin's sandbox is a WRITE sandbox:
Seatbelt is `(allow default)` + `(deny file-write*)`, and bwrap read-only-binds
the filesystem. Applying the same containment to the backend aligns the two spawn
paths and adds write and process containment. It does **not** close the read
exposure, because reads were never restricted on either path — denying them
breaks the CLI's ability to read its own binaries. Anything claiming this closes
the v0.56.1 read grant would be false.
"""

from __future__ import annotations

import pytest


def test_the_backend_wraps_the_agy_spawn_in_an_os_sandbox() -> None:
    """The plugin refuses to spawn an agentic CLI uncontained. The backend runs
    the same binary over the same untrusted material and must not be laxer."""
    from curator import llm

    plan = llm.os_sandbox_prefix(["/tmp/vault"], platform="darwin")
    assert plan, "no sandbox prefix produced on macOS"
    assert plan[0] == "sandbox-exec", f"expected Seatbelt, got {plan[0]!r}"
    profile = " ".join(plan)
    assert "(deny file-write*)" in profile, "the profile does not deny writes"
    assert "/tmp/vault" in profile, "the vault was not re-granted write access"


def test_reads_stay_allowed_because_denying_them_breaks_the_cli() -> None:
    """Stated so a future reader does not 'tighten' this into a broken CLI, and
    so nobody mistakes this for a fix to the read grant."""
    from curator import llm

    profile = " ".join(llm.os_sandbox_prefix(["/tmp/vault"], platform="darwin"))
    assert "(allow default)" in profile
    assert "deny file-read" not in profile


def test_linux_uses_bwrap_and_refuses_when_it_is_absent(monkeypatch) -> None:
    """On Linux the plugin refuses the CLI outright when `bwrap` is missing
    rather than running it uncontained. The backend must make the same call."""
    from curator import llm

    monkeypatch.setattr(llm.shutil, "which", lambda name: None)
    with pytest.raises(llm.SandboxUnavailableError):
        llm.os_sandbox_prefix(["/tmp/vault"], platform="linux")

    monkeypatch.setattr(llm.shutil, "which", lambda name: "/usr/bin/bwrap")
    plan = llm.os_sandbox_prefix(["/tmp/vault"], platform="linux")
    assert plan[0].endswith("bwrap")
    assert "--ro-bind" in plan


def test_an_unknown_platform_refuses_rather_than_running_uncontained() -> None:
    """Silently dropping containment on an unrecognised platform is the failure
    this repo keeps naming — the guarantee that quietly is not there."""
    from curator import llm

    with pytest.raises(llm.SandboxUnavailableError):
        llm.os_sandbox_prefix(["/tmp/vault"], platform="sunos")


def test_the_trust_workspace_env_vars_are_not_set() -> None:
    """`ANTIGRAVITY_TRUST_WORKSPACE` tells the CLI to skip its own guardrails on
    the very path that handles untrusted material."""
    import inspect

    from curator import llm

    src = inspect.getsource(llm.AntigravityCliClient)
    # Strip comments: the code must not SET it, and a comment explaining why it
    # no longer does is exactly what should be there. An earlier version of this
    # test matched the raw source and so would have failed on its own
    # explanation, which is a test that punishes the fix.
    code = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    assert "TRUST_WORKSPACE" not in code, (
        "the backend still asks the CLI to trust the workspace"
    )


def test_the_cli_can_write_the_log_file_the_backend_asks_it_for() -> None:
    """`_run` passes `--log-file` into `llm/agy_logs` and then reads it back to
    classify capacity errors.

    The first version of the allowlist granted only the temp dir, so the sandbox
    denied that write — breaking the CLI's own logging and blinding the capacity
    check that depends on it. A containment that stops the program doing its job
    is not containment, it is a bug wearing its clothes.
    """
    import subprocess
    import sys

    from curator import llm

    for name in ("agy_logs", "codex_outputs"):
        target = llm._repo_cache_dir("llm", name) / "sandbox-probe.log"
        result = subprocess.run(
            llm.os_sandbox_prefix(["/tmp/somevault"])
            + [sys.executable, "-c", f"open({str(target)!r}, 'w').write('x')"],
            capture_output=True,
            text=True,
        )
        target.unlink(missing_ok=True)
        assert result.returncode == 0, (
            f"the sandbox denied the CLI its own {name} directory: "
            f"{result.stderr.strip()[:120]}"
        )
