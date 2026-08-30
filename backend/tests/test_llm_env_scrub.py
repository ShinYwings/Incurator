"""The CLI environment must not carry the host IDE's Antigravity variables.

When Incurator runs inside the Antigravity IDE, the host exports ``ANTIGRAVITY_*``
pointing at its local daemon. A spawned ``agy`` picks them up, connects back to
that daemon, and answers from the IDE's active-tab metadata instead of the
prompt Incurator sent — the "PDF context hijack" reported against v0.53.1.

The plugin has scrubbed these since v0.53.2. The backend's own CLI clients were
left inheriting them, so this pins the backend half.
"""

import os
from unittest import mock

from curator import llm


def test_ide_injected_antigravity_vars_are_dropped() -> None:
    hostile = {
        "ANTIGRAVITY_IDE_PORT": "51234",
        "ANTIGRAVITY_SESSION_ID": "host-session",
        "ANTIGRAVITY_ACTIVE_DOCUMENT": "/some/other.pdf",
    }
    with mock.patch.dict(os.environ, hostile, clear=False):
        env = llm._repo_temp_env()

    assert not [k for k in env if k.startswith("ANTIGRAVITY_")], (
        "a host ANTIGRAVITY_* variable survived into the spawned CLI's "
        "environment; agy will reconnect to the IDE daemon"
    )


def test_unrelated_environment_survives() -> None:
    """The scrub is a prefix match, not a wipe — everything else must remain."""
    with mock.patch.dict(os.environ, {"ANTIGRAVITY_IDE_PORT": "1", "PATH": "/x"}):
        env = llm._repo_temp_env()

    assert env["PATH"] == "/x"
    # Names that merely CONTAIN the prefix are not IDE injections.
    with mock.patch.dict(os.environ, {"MY_ANTIGRAVITY_SETTING": "keep"}):
        assert llm._repo_temp_env()["MY_ANTIGRAVITY_SETTING"] == "keep"


def test_caller_supplied_trust_flag_outlives_the_scrub() -> None:
    """Order matters: ``extra`` is applied AFTER the scrub, never before.

    The original caller was ``AntigravityCliClient``, which set
    ``ANTIGRAVITY_TRUST_WORKSPACE`` on the theory that without it agy would stop
    at a workspace-trust prompt it cannot show in ``--print`` mode. That theory
    was never measured, and the plugin disproves it: it has spawned agy with
    ``-p`` and no trust flag for many releases and never stalls. The backend no
    longer sets it either — asking a CLI to skip its own guardrails on the one
    path that feeds it ingested, untrusted source material is not a tradeoff
    worth making for a prompt that does not appear.

    The ordering this pins is still load-bearing for every other caller-supplied
    variable, so the test keeps the trust flags as its example payload rather
    than pretending the scrub has no ``extra`` to protect.
    """
    with mock.patch.dict(os.environ, {"ANTIGRAVITY_IDE_PORT": "51234"}):
        env = llm._repo_temp_env({
            "ANTIGRAVITY_TRUST_WORKSPACE": "true",
            "AGY_TRUST_WORKSPACE": "true",
        })

    assert env["ANTIGRAVITY_TRUST_WORKSPACE"] == "true"
    assert env["AGY_TRUST_WORKSPACE"] == "true"
    assert "ANTIGRAVITY_IDE_PORT" not in env


def test_temp_dir_redirection_still_applies() -> None:
    """The scrub must not disturb what this helper existed to do."""
    env = llm._repo_temp_env()
    assert env["TMPDIR"] == env["TEMP"] == env["TMP"]
    assert env["TMPDIR"].endswith(os.path.join("llm", "tmp"))
