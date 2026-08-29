"""v0.62.3: the plugin must be able to persist and recover its provider key.

The reported bug is that the DeepSeek key has to be re-entered after every
update, and it reproduced deterministically: deploying the plugin and reloading
Obsidian was enough to lose it, and it blocked the P6 acceptance test twice in
one day.

Three facts combine into it, and only the third is fixable here:

1. The plugin strips `deepseekApiKey` from `data.json` on purpose, so it cannot
   leak into Obsidian Sync or a git-tracked vault (PLUGIN_SCHEMA §2.4). That is
   correct and stays.
2. Its only restore path is `process.env.DEEPSEEK_API_KEY`, which a
   GUI-launched Obsidian does not have.
3. A durable encrypted store already exists — `secret_store`, Fernet, under the
   machine-local `.cache/config/secrets/` — and the plugin has **no way to reach
   it**. `set_secret`/`get_secret` had no plugin-facing command at all.

These tests pin the bridge that closes (3).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from curator.cli import app

runner = CliRunner()


@pytest.fixture()
def isolated_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the secret store at a temp dir so tests never touch the real one."""
    from curator import config as cfg

    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: tmp_path / "config")
    return tmp_path


def _run(*args: str) -> dict:
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.output
    start = result.output.index("{")
    return json.loads(result.output[start:])


def test_a_stored_key_survives_and_comes_back(isolated_secrets: Path) -> None:
    """Set, then get. This is the whole point: a value that outlives the plugin
    process, so an update cannot take it."""
    stored = _run("plugin", "secret", "set", "--name", "deepseek-api-key",
                  "--value", "sk-test-abc123")
    assert stored["ok"] is True
    assert stored["name"] == "deepseek-api-key"
    assert "sk-test-abc123" not in json.dumps(stored), (
        "the set response must not echo the secret back"
    )

    got = _run("plugin", "secret", "get", "--name", "deepseek-api-key")
    assert got["ok"] is True
    assert got["value"] == "sk-test-abc123"


def test_missing_key_reports_absence_rather_than_failing(isolated_secrets: Path) -> None:
    """A first run has no key. That is a normal state, not an error — the plugin
    needs to tell them to enter one, not surface a crash."""
    got = _run("plugin", "secret", "get", "--name", "deepseek-api-key")
    assert got["ok"] is True
    assert got["value"] == ""
    assert got["present"] is False


def test_the_value_is_encrypted_on_disk(isolated_secrets: Path) -> None:
    """Not plaintext in a file. The reason the plugin refuses `data.json` in the
    first place is that a plaintext key travels; this store must not just move
    the same problem somewhere else."""
    _run("plugin", "secret", "set", "--name", "deepseek-api-key",
         "--value", "sk-plaintext-canary")

    files = list((isolated_secrets / "config" / "secrets").rglob("*"))
    assert files, "nothing was written"
    for f in (f for f in files if f.is_file()):
        assert "sk-plaintext-canary" not in f.read_bytes().decode("utf-8", "replace"), (
            f"the secret is readable in {f.name}"
        )


def test_an_empty_value_is_rejected_not_stored(isolated_secrets: Path) -> None:
    """Clearing the field must not silently store an empty secret that then
    reads back as 'configured'."""
    result = runner.invoke(app, ["plugin", "secret", "set",
                                 "--name", "deepseek-api-key", "--value", ""])
    payload = json.loads(result.output[result.output.index("{"):])
    assert payload["ok"] is False
    got = _run("plugin", "secret", "get", "--name", "deepseek-api-key")
    assert got["present"] is False


def test_plugin_and_backend_keys_are_stored_separately(isolated_secrets: Path) -> None:
    """They are configured separately ON PURPOSE — possibly different accounts or
    tiers — so the store must keep them apart rather than let one overwrite the
    other. What is shared is the encryption, not the value."""
    _run("plugin", "secret", "set", "--name", "obsidian-deepseek-api-key",
         "--value", "sk-obsidian-side")
    _run("plugin", "secret", "set", "--name", "deepseek-api-key",
         "--value", "sk-backend-side")

    assert _run("plugin", "secret", "get",
                "--name", "obsidian-deepseek-api-key")["value"] == "sk-obsidian-side"
    assert _run("plugin", "secret", "get",
                "--name", "deepseek-api-key")["value"] == "sk-backend-side"


def test_sign_out_can_actually_forget_the_key(isolated_secrets: Path) -> None:
    """v0.71.0: the bridge was write-only, so "Sign out" could not finish.

    The plugin's sign-out cleared `settings.deepseekApiKey` and stopped there.
    But the key lives in TWO places, and this store is the durable one — the
    plugin reads it back at launch via `restoreDeepseekKeyFromStore()`. With no
    delete command, sign-out was undone by the next restart, silently, with the
    UI still reporting the key as cleared. That is the failure this pins.
    """
    _run("plugin", "secret", "set", "--name", "deepseek-api-key", "--value", "sk-test-abc123")

    removed = _run("plugin", "secret", "rm", "--name", "deepseek-api-key")
    assert removed["ok"] is True
    assert removed["deleted"] is True

    got = _run("plugin", "secret", "get", "--name", "deepseek-api-key")
    assert got["present"] is False, "the key came back after sign-out"
    assert got["value"] == ""


def test_signing_out_twice_is_not_an_error(isolated_secrets: Path) -> None:
    """Sign-out must succeed whether or not a key was ever stored — the user can
    click it with nothing saved, and a second click must not surface a crash."""
    first = _run("plugin", "secret", "rm", "--name", "deepseek-api-key")
    assert first["ok"] is True
    assert first["deleted"] is False


def test_removing_the_plugin_key_leaves_the_backend_key_alone(isolated_secrets: Path) -> None:
    """The two keys are separate by design (the user configures them
    independently). Signing out of the plugin must not sign the backend out."""
    _run("plugin", "secret", "set", "--name", "deepseek-api-key", "--value", "sk-plugin")
    _run("plugin", "secret", "set", "--name", "backend-deepseek", "--value", "sk-backend")

    _run("plugin", "secret", "rm", "--name", "deepseek-api-key")

    survivor = _run("plugin", "secret", "get", "--name", "backend-deepseek")
    assert survivor["value"] == "sk-backend", "sign-out took the backend's key with it"
