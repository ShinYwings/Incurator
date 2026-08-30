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

from pathlib import Path

import pytest


def _sandbox_actually_runs() -> bool:
    """True when a trivial command survives the real sandbox on this machine.

    Presence of the binary is not enough. A CI runner can have bubblewrap
    installed and still refuse it, because unprivileged user namespaces are
    restricted on recent Ubuntu images — so the tests that EXECUTE the sandbox
    ask it to prove itself, while the tests that only inspect the generated argv
    pass `platform=` and need nothing installed.
    """
    import subprocess
    import sys

    from curator import llm

    try:
        prefix = llm.os_sandbox_prefix(["/tmp/vault"])
    except llm.SandboxUnavailableError:
        return False
    try:
        return (
            subprocess.run(
                [*prefix, sys.executable, "-c", "pass"],
                capture_output=True,
                timeout=30,
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


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


@pytest.mark.skipif(
    not _sandbox_actually_runs(),
    reason="no working OS sandbox on this machine; the argv tests still cover the plan",
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


def test_an_uncontainable_platform_fails_over_instead_of_crashing() -> None:
    """A machine that cannot contain the CLI must fall back, not take the vault down.

    USER_GUIDE promises the configured fallback takes over when a provider
    cannot serve. `SandboxUnavailableError` began life as a bare `RuntimeError`,
    so it slipped past `FailoverClient` and every `except LLMError` site in the
    pipeline: a Linux user without `bwrap` got a traceback where the guide
    promises Ollama picks up the work.

    Refusing to run the CLI uncontained and refusing to let the fallback serve
    are two different decisions. Only the first is the security requirement.
    """
    from curator import llm

    class Uncontainable:
        def chat(self, messages, **kwargs):  # type: ignore[no-untyped-def]
            raise llm.SandboxUnavailableError("bwrap is not installed")

    class Fallback:
        def chat(self, messages, **kwargs):  # type: ignore[no-untyped-def]
            return "served by the fallback"

    client = llm.FailoverClient([Uncontainable(), Fallback()])
    answer = client.chat([llm.ChatMessage(role="user", content="hi")])

    assert answer == "served by the fallback"
    assert isinstance(llm.SandboxUnavailableError("x"), llm.LLMError), (
        "every other provider failure in llm.py subclasses LLMError; this one "
        "must too or _FAILOVER_ERRORS will not see it"
    )


def test_agy_is_not_handed_the_other_clis_credential_dirs() -> None:
    """Least privilege, the way the plugin already fixed it in v0.25.5 (PR #53).

    The first version granted all four provider state directories to whichever
    CLI was running, so a contained `agy` — running over ingested, untrusted
    source material — could overwrite the auth state of `claude` and `codex`,
    two CLIs it never touches. The plugin's review caught exactly this shape and
    the backend must not be laxer than the surface it mirrors.
    """
    from curator import llm

    profile = " ".join(
        llm.os_sandbox_prefix(["/tmp/vault"], provider="antigravity", platform="darwin")
    )

    assert ".gemini" in profile and ".antigravity" in profile, (
        "agy still needs its own state dirs"
    )
    for foreign in (".claude", ".codex"):
        assert foreign not in profile, (
            f"agy was granted write access to {foreign}, a CLI it does not run"
        )


def test_an_unnamed_provider_gets_no_credential_dir_at_all() -> None:
    """The plugin's bug was a default that fell back to *all four* dirs.

    Failing open is what made that a security finding rather than a typo, so the
    backend's default is the empty set.
    """
    from curator import llm

    profile = " ".join(llm.os_sandbox_prefix(["/tmp/vault"], platform="darwin"))

    for d in (".gemini", ".antigravity", ".claude", ".codex"):
        assert d not in profile, f"an unnamed provider was granted {d}"


def test_the_backend_keeps_the_flag_that_stops_print_mode_hanging() -> None:
    """`--sandbox` is why `-p` mode does not stop at a permission prompt.

    v0.23.0 measured that dropping it makes agy revert to a prompt it cannot show
    and hang; the plugin has passed it ever since. The backend used to rely on
    `*_TRUST_WORKSPACE` instead, so removing that without adding this flag would
    have left it in a combination neither surface has ever run — a 900 s stall on
    every ingest call.
    """
    import subprocess
    import types
    from unittest import mock

    from curator import llm

    captured: dict = {}

    def fake_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured["cmd"] = [str(c) for c in cmd]
        return types.SimpleNamespace(returncode=0, stdout="ok", stderr="")

    with mock.patch.object(subprocess, "run", fake_run):
        llm.AntigravityCliClient(model="gemini-3-pro").chat(
            [llm.ChatMessage(role="user", content="hi")]
        )

    cmd = captured["cmd"]
    assert "--sandbox" in cmd, (
        "agy would stop at a permission prompt it cannot display under --print"
    )
    assert not [k for k in cmd if "TRUST_WORKSPACE" in k]


@pytest.mark.skipif(
    not _sandbox_actually_runs(),
    reason="no working OS sandbox on this machine; the argv tests still cover the plan",
)
def test_the_real_profile_allows_the_vault_and_refuses_everything_else(
    tmp_path,  # type: ignore[no-untyped-def]
) -> None:
    """Runs the generated profile instead of asserting on its text.

    The CHANGELOG claims a write inside the vault succeeds, a write to `$HOME` or
    the system temp dir is refused, reads still work, and the refusal survives the
    nested shells `agy` spawns. Those claims were checked by hand and not shipped,
    which is how a profile that looks right and behaves wrong gets released. They
    are assertions now.
    """
    import subprocess
    import sys

    from curator import llm

    vault = tmp_path / "vault"
    vault.mkdir()
    prefix = llm.os_sandbox_prefix([str(vault)], provider="antigravity")

    def run(code: str) -> int:
        return subprocess.run(
            [*prefix, sys.executable, "-c", code], capture_output=True, timeout=60
        ).returncode

    assert run(f"open({str(vault / 'note.md')!r}, 'w').write('x')") == 0, (
        "the CLI cannot write into the vault it was granted"
    )
    assert run(f"open({str(Path.home() / '.sandbox-probe')!r}, 'w').write('x')") != 0, (
        "the CLI escaped into $HOME"
    )
    assert run("open('/tmp/.incurator-sandbox-probe', 'w').write('x')") != 0, (
        "the CLI escaped into the system temp dir"
    )
    assert run("open('/etc/hosts').read()") == 0, (
        "reads are deliberately not restricted; denying them breaks the CLI"
    )
    assert (
        run(
            "import subprocess; subprocess.run("
            "['sh','-c','sh -c \\'sh -c \"echo x > /tmp/.incurator-nested\"\\''], check=True)"
        )
        != 0
    ), "the refusal did not survive nested shells, which is how agy runs tools"
