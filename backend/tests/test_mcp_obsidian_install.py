"""v0.53.0: `wiki mcp install obsidian` registers the server the sidechat needs.

Measured on the reporting vault: `mcpServers` was `[]`, which disables the whole
knowledge-base channel in the plugin's chat — tool injection and the
system-prompt section that describes `curator_query` / `search_curator` /
`curator_fetch_context` are both gated on a configured server whose name
contains "incurator". No amount of backend retrieval work is reachable without
this entry, which is why repeated retrieval fixes changed nothing for the user.

Writing is justified here (the other targets only print): a plugin `data.json`
is owned by Obsidian, not hand-edited. That makes preserving unrelated keys and
refusing to clobber unparseable files load-bearing, not defensive padding.
"""

import json
import tempfile
import unittest
from pathlib import Path

from curator import config as cfg
from curator.mcp import server as mcp_server

PLUGIN_REL = Path(".obsidian") / "plugins" / "incurator-obsidian-agent"


def _vault_with_plugin(root: Path, data: dict | str | None = None) -> Path:
    plugin_dir = root / PLUGIN_REL
    plugin_dir.mkdir(parents=True, exist_ok=True)
    if data is not None:
        payload = data if isinstance(data, str) else json.dumps(data, indent=2)
        (plugin_dir / "data.json").write_text(payload, encoding="utf-8")
    return plugin_dir / "data.json"


class TestObsidianMcpInstall(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _read(self) -> dict:
        return json.loads((self.root / PLUGIN_REL / "data.json").read_text(encoding="utf-8"))

    def test_registers_the_server_when_none_exists(self) -> None:
        _vault_with_plugin(self.root, {"mcpServers": []})
        report = mcp_server.install_obsidian_mcp_server(self.paths)

        self.assertEqual(report["action"], "added")
        servers = self._read()["mcpServers"]
        self.assertEqual(len(servers), 1)
        self.assertEqual(servers[0]["name"], "incurator")
        self.assertEqual(servers[0]["args"], ["mcp"])
        self.assertTrue(servers[0]["enabled"])
        self.assertEqual(servers[0]["env"]["VAULT_ROOT"], str(self.root.resolve()))

    def test_name_satisfies_the_plugin_gate(self) -> None:
        """ChatSidebarView matches `s.enabled && s.name.toLowerCase().includes("incurator")`."""
        _vault_with_plugin(self.root, {})
        mcp_server.install_obsidian_mcp_server(self.paths)
        server = self._read()["mcpServers"][0]
        self.assertIn("incurator", server["name"].lower())
        self.assertIs(server["enabled"], True)

    def test_preserves_every_unrelated_setting(self) -> None:
        _vault_with_plugin(
            self.root,
            {
                "provider": "antigravity",
                "zoteroProfiles": [{"name": "main"}],
                "pdfRagTopK": 5,
                "mcpServers": [],
            },
        )
        mcp_server.install_obsidian_mcp_server(self.paths)
        data = self._read()
        self.assertEqual(data["provider"], "antigravity")
        self.assertEqual(data["zoteroProfiles"], [{"name": "main"}])
        self.assertEqual(data["pdfRagTopK"], 5)

    def test_is_idempotent(self) -> None:
        _vault_with_plugin(self.root, {"mcpServers": []})
        mcp_server.install_obsidian_mcp_server(self.paths)
        first = self._read()
        report = mcp_server.install_obsidian_mcp_server(self.paths)
        self.assertEqual(report["action"], "unchanged")
        self.assertEqual(self._read(), first)
        self.assertEqual(len(self._read()["mcpServers"]), 1)

    def test_repairs_a_stale_entry_instead_of_duplicating(self) -> None:
        _vault_with_plugin(
            self.root,
            {"mcpServers": [{
                "name": "Incurator",           # different case
                "command": "/old/path/wiki",   # stale
                "args": ["mcp"],
                "enabled": False,              # and disabled
            }]},
        )
        report = mcp_server.install_obsidian_mcp_server(self.paths)
        self.assertEqual(report["action"], "updated")
        servers = self._read()["mcpServers"]
        self.assertEqual(len(servers), 1, "a stale entry must be repaired, not duplicated")
        self.assertTrue(servers[0]["enabled"])
        self.assertNotEqual(servers[0]["command"], "/old/path/wiki")

    def test_leaves_other_servers_alone(self) -> None:
        other = {"name": "some-other", "command": "x", "args": [], "enabled": True}
        _vault_with_plugin(self.root, {"mcpServers": [other]})
        mcp_server.install_obsidian_mcp_server(self.paths)
        servers = self._read()["mcpServers"]
        self.assertIn(other, servers)
        self.assertEqual(len(servers), 2)

    def test_creates_the_list_when_the_key_is_missing_or_wrong_type(self) -> None:
        for payload in ({}, {"mcpServers": None}, {"mcpServers": "nope"}):
            with self.subTest(payload=payload):
                _vault_with_plugin(self.root, payload)
                mcp_server.install_obsidian_mcp_server(self.paths)
                self.assertEqual(len(self._read()["mcpServers"]), 1)

    def test_handles_a_missing_data_file(self) -> None:
        _vault_with_plugin(self.root)  # plugin dir, no data.json yet
        mcp_server.install_obsidian_mcp_server(self.paths)
        self.assertEqual(len(self._read()["mcpServers"]), 1)

    def test_refuses_to_overwrite_unparseable_settings(self) -> None:
        """That file holds API keys and Zotero profiles — never clobber it blind."""
        _vault_with_plugin(self.root, "{not json")
        with self.assertRaises(ValueError):
            mcp_server.install_obsidian_mcp_server(self.paths)
        self.assertEqual(
            (self.root / PLUGIN_REL / "data.json").read_text(encoding="utf-8"), "{not json"
        )

    def test_refuses_a_non_object_settings_file(self) -> None:
        _vault_with_plugin(self.root, "[1, 2, 3]")
        with self.assertRaises(ValueError):
            mcp_server.install_obsidian_mcp_server(self.paths)

    def test_fails_clearly_when_the_plugin_is_not_installed(self) -> None:
        with self.assertRaises(FileNotFoundError):
            mcp_server.install_obsidian_mcp_server(self.paths)


class TestWikiCommandResolution(unittest.TestCase):
    def test_prefers_the_repo_root_venv_over_a_bare_name(self) -> None:
        """A GUI app does not reliably inherit the shell PATH that finds `wiki`."""
        command = mcp_server.resolve_wiki_command()
        if command != "wiki":
            self.assertTrue(command.endswith("/.venv/bin/wiki"), command)
            self.assertNotIn("/backend/", command, "venvs live at the repo root")



class TestBareWikiMcpStartsTheServer(unittest.TestCase):
    """`wiki mcp` with no subcommand MUST reach the callback.

    Every documented client config launches the server as
    `{"command": "wiki", "args": ["mcp"]}`. Two Typer settings each broke that
    independently, and together they made the server unstartable by any client
    from v0.34.0 until v0.53.0:

    * `no_args_is_help=True` on the app short-circuits to a usage screen (exit 2)
      before the callback runs.
    * a callback without `invoke_without_command=True` is rejected earlier still
      with "Missing command".

    Asserted on the Typer object rather than by spawning a server, so the test
    stays fast and cannot hang waiting on stdio.
    """

    def test_app_does_not_short_circuit_to_help(self) -> None:
        from curator.commands.mcp import mcp_app

        self.assertFalse(
            mcp_app.info.no_args_is_help,
            "no_args_is_help exits 2 before the callback, so `wiki mcp` never serves",
        )

    def test_callback_runs_without_a_subcommand(self) -> None:
        from curator.commands.mcp import mcp_app

        self.assertTrue(
            mcp_app.registered_callback.invoke_without_command,
            "without this Typer rejects a bare `wiki mcp` with 'Missing command'",
        )

    def test_subcommands_are_still_reachable(self) -> None:
        from curator.commands.mcp import mcp_app

        names = {c.name for c in mcp_app.registered_commands}
        self.assertIn("install", names)
        self.assertIn("connect", names)

if __name__ == "__main__":
    unittest.main()
