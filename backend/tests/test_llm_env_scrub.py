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

    ``AntigravityCliClient`` deliberately sets ``ANTIGRAVITY_TRUST_WORKSPACE``.
    If the scrub ran last it would delete that too, and agy would stop at a
    workspace-trust prompt it cannot show in ``--print`` mode — turning the
    hijack fix into the "no output produced" failure it sits next to.
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
