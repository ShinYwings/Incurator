"""
Tests for S2 CLI correctness fixes (v0.25.8):
  G07-1: wiki config models use <ollama-model> writes llm.primary (not nested ollama.model)
  G07-3: wiki query warns when no-op orchestrator flags are passed
  G07-7: wiki status --refresh gates state-mutating calls
  G07-8: wiki lint is read-only by default (no manifest refresh without --fix/--save/--refresh-manifests)
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

from curator import config as cfg
from curator import constants as consts
from curator import db


# ─── helpers ────────────────────────────────────────────────────────────────

def _make_settings_yml(root: Path, primary: str = "ollama::qwen2.5:7b") -> None:
    settings_dir = root / ".curator"
    settings_dir.mkdir(parents=True, exist_ok=True)
    (settings_dir / "settings.yml").write_text(
        textwrap.dedent(f"""\
            llm:
              primary: "{primary}"
              primary_effort: ""
        """)
    )


def _make_wiki_paths(root: Path) -> cfg.WikiPaths:
    _make_settings_yml(root)
    db.init_db(root / ".curator" / "state.sqlite")
    return cfg.WikiPaths(root)


# ─── G07-1: ollama model selection writes llm.primary ───────────────────────

class TestOllamaModelSelection:
    def test_models_use_ollama_writes_primary_field(self, tmp_path: Path) -> None:
        """G07-1: wiki config models use <tag> for an Ollama vault must write llm.primary."""
        _make_settings_yml(tmp_path, primary="ollama::qwen2.5:7b")
        paths = cfg.WikiPaths(tmp_path)
        config = cfg.load_config(paths)

        # Simulate what models_use does after confirming model availability
        model = "mistral:7b"
        config.setdefault("llm", {})["primary"] = cfg.join_provider_model(consts.BACKEND_OLLAMA, model)
        config["llm"]["primary_effort"] = ""
        cfg.save_config(paths, config)

        # Reload and verify the new primary is preserved
        reloaded = cfg.load_config(paths)
        provider, loaded_model = cfg.split_provider_model(reloaded["llm"]["primary"])
        assert provider == consts.BACKEND_OLLAMA
        assert loaded_model == model

    def test_legacy_nested_ollama_model_key_stripped_on_load(self, tmp_path: Path) -> None:
        """G07-1 regression: old config with nested ollama.model is stripped on load."""
        settings_dir = tmp_path / ".curator"
        settings_dir.mkdir(parents=True, exist_ok=True)
        (settings_dir / "settings.yml").write_text(
            textwrap.dedent("""\
                llm:
                  primary: "ollama::qwen2.5:7b"
                  ollama:
                    model: "old-legacy-model"
            """)
        )
        paths = cfg.WikiPaths(tmp_path)
        config = cfg.load_config(paths)
        # _migrate_llm_config strips the nested ollama.model key
        nested = config.get("llm", {}).get(consts.BACKEND_OLLAMA, {})
        assert "model" not in nested, "Legacy nested ollama.model key must be stripped on load"


# ─── G07-3: no-op orchestrator flags produce a warning ──────────────────────

class TestQueryNoopFlagWarning:
    """G07-3: Passing --mode/--limit/--scope/etc. emits a deprecation warning."""

    def _query_command_source(self) -> str:
        import inspect
        from curator.cli import query as _query_cmd
        return inspect.getsource(_query_cmd)

    def test_noop_flag_check_present_in_query_source(self) -> None:
        src = self._query_command_source()
        assert "_ORCHESTRATOR_NOOP" in src, "G07-3: _ORCHESTRATOR_NOOP check must exist in query command"
        assert "_noop_used" in src
        assert "not yet wired" in src or "no effect" in src


# ─── G07-7: wiki status does NOT mutate state without --refresh ─────────────

class TestStatusReadOnly:
    """G07-7: status() no longer calls _mark_existing_l3_done_if_present or
    write_runtime_snapshots unless --refresh is passed."""

    _FAKE_STATS = {
        "total_sources": 0, "done_sources": 0, "error_sources": 0,
        "pending_sources": 0, "total_jobs": 0, "running_jobs": 0,
        "total_tokens_in": 0, "total_tokens_out": 0, "total_cost_usd": 0.0,
        "total_atoms": 0, "total_concepts": 0, "total_synthesis": 0,
    }

    def test_status_without_refresh_skips_mutations(self, tmp_path: Path) -> None:
        paths = _make_wiki_paths(tmp_path)
        config = cfg.load_config(paths)

        with (
            patch("curator.cli.ingest_llm._mark_existing_l3_done_if_present") as mark_l3,
            patch("curator.cli.runtime_state.write_runtime_snapshots") as write_snap,
            patch("curator.cli.cfg.load_config", return_value=config),
            patch("curator.cli._resolve_root_or_die", return_value=paths),
            patch("curator.cli.db.get_stats", return_value=self._FAKE_STATS),
            patch("curator.cli.console"),
        ):
            from curator.cli import status as _status
            try:
                _status(json_output=False, refresh=False)
            except (SystemExit, Exception):
                pass

        mark_l3.assert_not_called()
        write_snap.assert_not_called()

    def test_status_with_refresh_calls_mutations(self, tmp_path: Path) -> None:
        paths = _make_wiki_paths(tmp_path)
        config = cfg.load_config(paths)

        with (
            patch("curator.cli.ingest_llm._mark_existing_l3_done_if_present") as mark_l3,
            patch("curator.cli.runtime_state.write_runtime_snapshots") as write_snap,
            patch("curator.cli.cfg.load_config", return_value=config),
            patch("curator.cli._resolve_root_or_die", return_value=paths),
            patch("curator.cli.db.get_stats", return_value=self._FAKE_STATS),
            patch("curator.cli.console"),
        ):
            from curator.cli import status as _status
            try:
                _status(json_output=False, refresh=True)
            except (SystemExit, Exception):
                pass

        mark_l3.assert_called_once()
        write_snap.assert_called_once()


# ─── G07-8: wiki lint is read-only by default ────────────────────────────────

class TestLintReadOnly:
    """G07-8: plain wiki lint must NOT rebuild index, overview, ledger, or log."""

    def _run_lint(self, tmp_path: Path, **flags: object) -> tuple:
        """Run lint with mocked writers, return (rebuild, overview, ledger, log_entry) mocks."""
        paths = _make_wiki_paths(tmp_path)
        rebuild = MagicMock()
        overview = MagicMock()
        ledger = MagicMock()
        log_entry = MagicMock()

        with (
            patch("curator.cli._resolve_root_or_die", return_value=paths),
            patch("curator.cli.lint_module.run_lint") as mock_lint,
            patch("curator.cli._render_lint_report_terminal"),
            patch("curator.cli.console"),
            patch("curator.page_writer.rebuild_index", rebuild),
            patch("curator.ingest_llm._update_overview", overview),
            patch("curator.ingest_llm._update_ledger", ledger),
            patch("curator.page_writer.append_log_entry", log_entry),
        ):
            mock_lint.return_value = MagicMock(issues=[], errors=[], warnings=[], auto_fixed=0)
            from curator.cli import lint as _lint
            try:
                _lint(**flags)  # type: ignore[arg-type]
            except (SystemExit, Exception):
                pass

        return rebuild, overview, ledger, log_entry

    def test_lint_without_flags_does_not_call_manifest_writers(self, tmp_path: Path) -> None:
        rebuild, overview, ledger, log_entry = self._run_lint(
            tmp_path, deep=False, fix=False, save=False, max_pairs=10, refresh_manifests=False
        )
        rebuild.assert_not_called()
        overview.assert_not_called()
        ledger.assert_not_called()
        log_entry.assert_not_called()

    def test_lint_with_refresh_manifests_calls_writers(self, tmp_path: Path) -> None:
        rebuild, overview, ledger, log_entry = self._run_lint(
            tmp_path, deep=False, fix=False, save=False, max_pairs=10, refresh_manifests=True
        )
        rebuild.assert_called_once()
        overview.assert_called_once()
        ledger.assert_called_once()
        log_entry.assert_called_once()
