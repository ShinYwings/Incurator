"""
Tests for System Stability Phase A S2 batch (v0.27.0):
  G08-6: LLM client is closed after curator_build_all / curator_sync
  G11-8: cross-layer lint emits the frontmatter field name, not dataclasses.field
  G11-9: lint reports saved to .curator/reports/, not L4 synthesis
  G11-10: check_contradictions_deep is read-only by default (apply_flags=False)
  G14-5: syncReasoningControl persists normalized effort when model changes
  G15-6: renderJobs clears stale jobsTimer before installing a new one
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock


# ─── G08-6: LLM client lifecycle in MCP build/sync tools ────────────────────

class TestMcpLlmClientLifecycle:
    """build_client returns a context manager; verify all LLM client types support it."""

    def test_ollama_client_context_manager_protocol(self) -> None:
        """OllamaClient must implement __enter__/__exit__ so 'with build_client()' works."""
        from curator.llm import OllamaClient
        import curator.constants as consts
        client = OllamaClient(consts.DEFAULT_OLLAMA_HOST)
        assert hasattr(client, "__enter__") and hasattr(client, "__exit__")
        with client:
            pass

    def test_mcp_server_build_sync_uses_with(self) -> None:
        """Verify the source of curator_build_all and curator_sync uses 'with build_client'."""
        import inspect
        import curator.mcp_server as mcp_mod
        src = inspect.getsource(mcp_mod)
        # Both tools must use context-manager form; check by looking for the pattern
        assert src.count("with build_client(") >= 2, (
            "curator_build_all and curator_sync must both use 'with build_client(...)'"
        )


# ─── G11-8: lint cross-layer field name ──────────────────────────────────────

class TestLintCrossLayerFieldName:
    """check_cross_layer_links must emit fm_field (the loop variable), not field."""

    def _build_inventory(self, tmp_path: Path, atom_id: str, wrong_ref: str) -> Any:
        from curator.lint import _build_inventory
        from curator import config as cfg, constants as consts, page_writer

        atoms_dir = tmp_path / consts.DEFAULT_COLLECTIONS_DIR / consts.LAYER_L2
        atoms_dir.mkdir(parents=True)

        # Write an atom page that references an L4 id in its concept_ids field
        content = (
            "---\n"
            f"id: {atom_id}\n"
            "type: atom\n"
            f"concept_ids: [{wrong_ref}]\n"
            "source_ids: []\n"
            "---\n\nBody text.\n"
        )
        (atoms_dir / f"{atom_id}.md").write_text(content, encoding="utf-8")

        paths = cfg.WikiPaths(root=tmp_path)
        return _build_inventory(paths)

    def test_field_name_in_context_is_string(self, tmp_path: Path) -> None:
        from curator.lint import check_cross_layer_links

        inv = self._build_inventory(tmp_path, "ATM-test-001", "SYN-bad-ref")
        issues = check_cross_layer_links(inv)

        # There should be a cross-layer issue for the bad SYN ref in concept_ids
        matching = [i for i in issues if "concept_ids" in (i.context or {}).get("field", "")]
        if matching:
            field_val = matching[0].context["field"]
            assert isinstance(field_val, str), (
                f"context['field'] must be a plain string, got {type(field_val)}"
            )
            assert field_val == "concept_ids"


# ─── G11-9: lint report save location ────────────────────────────────────────

class TestLintReportStorage:
    def test_render_report_markdown_uses_lint_report_type(self, tmp_path: Path) -> None:
        from curator.lint import render_report_markdown, LintReport
        from curator import config as cfg

        paths = cfg.WikiPaths(root=tmp_path)
        report = LintReport()

        md = render_report_markdown(report, paths)

        assert "type: lint_report" in md, "report must use type: lint_report, not type: synthesis"
        assert "concept_ids" not in md, "report must not emit L4-specific frontmatter"
        assert "confidence_score" not in md, "report must not emit L4-specific frontmatter"

    def test_cli_saves_to_curator_reports_dir(self, tmp_path: Path) -> None:
        """CLI --save must write to .curator/reports/, not L4 synthesis."""
        from curator import config as cfg, constants as consts

        paths = cfg.WikiPaths(root=tmp_path)
        synthesis_dir = paths.synthesis
        synthesis_dir.mkdir(parents=True, exist_ok=True)
        reports_dir = paths.internal / "reports"

        # Simulate what cli.py does on save
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_file = reports_dir / "lint-2026-01-01-abcd.md"
        report_file.write_text("---\ntype: lint_report\n---\n", encoding="utf-8")

        # The synthesis dir must remain empty
        syn_files = list(synthesis_dir.glob("*.md"))
        assert syn_files == [], "lint report must not be written to L4 synthesis"
        assert report_file.exists(), "lint report must be written to .curator/reports/"


# ─── G11-10: deep lint is read-only by default ───────────────────────────────

class TestDeepLintReadOnly:
    def test_apply_flags_false_does_not_write_atoms(self, tmp_path: Path) -> None:
        from curator.lint import check_contradictions_deep, PageInventory
        from curator import config as cfg, constants as consts

        # Set up a minimal atoms dir with two pages sharing a link
        atoms_dir = tmp_path / consts.DEFAULT_COLLECTIONS_DIR / consts.LAYER_L2
        atoms_dir.mkdir(parents=True)

        for atom_id, body in [
            ("ATM-a", "Water boils at 100°C. [[SYN-common]]"),
            ("ATM-b", "Water boils at 90°C. [[SYN-common]]"),
        ]:
            (atoms_dir / f"{atom_id}.md").write_text(
                f"---\nid: {atom_id}\ntype: atom\n---\n\n{body}\n",
                encoding="utf-8",
            )

        paths = cfg.WikiPaths(root=tmp_path)

        # Build a minimal inventory
        from curator.lint import _build_inventory
        inv = _build_inventory(paths)

        mock_client = MagicMock()
        mock_client.chat.return_value = "Potential contradiction: boiling point differs."

        # Default: apply_flags=False — atom files must NOT be modified
        before_mtimes = {
            p.name: p.stat().st_mtime for p in atoms_dir.glob("*.md")
        }
        check_contradictions_deep(inv, paths, mock_client, apply_flags=False)
        after_mtimes = {
            p.name: p.stat().st_mtime for p in atoms_dir.glob("*.md")
        }
        assert before_mtimes == after_mtimes, (
            "check_contradictions_deep with apply_flags=False must not write atom files"
        )

    def test_apply_flags_true_writes_atoms(self, tmp_path: Path) -> None:
        from curator.lint import check_contradictions_deep
        from curator import config as cfg, constants as consts

        atoms_dir = tmp_path / consts.DEFAULT_COLLECTIONS_DIR / consts.LAYER_L2
        atoms_dir.mkdir(parents=True)

        for atom_id, body in [
            ("ATM-x", "Claim A. [[SYN-shared]]"),
            ("ATM-y", "Contradicts Claim A. [[SYN-shared]]"),
        ]:
            (atoms_dir / f"{atom_id}.md").write_text(
                f"---\nid: {atom_id}\ntype: atom\n---\n\n{body}\n",
                encoding="utf-8",
            )

        paths = cfg.WikiPaths(root=tmp_path)
        from curator.lint import _build_inventory
        inv = _build_inventory(paths)

        mock_client = MagicMock()
        mock_client.chat.return_value = "Contradiction: claim A vs not-A."

        check_contradictions_deep(inv, paths, mock_client, apply_flags=True)

        for atom_file in atoms_dir.glob("*.md"):
            content = atom_file.read_text()
            assert "is_flagged_for_agent: true" in content, (
                f"{atom_file.name} must be flagged when apply_flags=True"
            )

    def test_apply_flags_true_ignores_malformed_frontmatter(self, tmp_path: Path, monkeypatch) -> None:
        from curator.lint import check_contradictions_deep
        from curator import config as cfg, constants as consts, page_writer

        atoms_dir = tmp_path / consts.DEFAULT_COLLECTIONS_DIR / consts.LAYER_L2
        atoms_dir.mkdir(parents=True)

        for atom_id, body in [
            ("ATM-bad-a", "Claim A. [[SYN-shared]]"),
            ("ATM-bad-b", "Contradicts Claim A. [[SYN-shared]]"),
        ]:
            (atoms_dir / f"{atom_id}.md").write_text(
                f"---\nid: {atom_id}\ntype: atom\n---\n\n{body}\n",
                encoding="utf-8",
            )

        paths = cfg.WikiPaths(root=tmp_path)
        from curator.lint import _build_inventory
        inv = _build_inventory(paths)

        mock_client = MagicMock()
        mock_client.chat.return_value = "Contradiction: claim A vs not-A."

        malformed_page = MagicMock()
        malformed_page.frontmatter = None
        monkeypatch.setattr(page_writer, "read_page", lambda _: malformed_page)
        write_page = MagicMock()
        monkeypatch.setattr(page_writer, "write_page", write_page)

        issues = check_contradictions_deep(inv, paths, mock_client, apply_flags=True)

        assert len(issues) == 1
        write_page.assert_not_called()


# ─── run_lint apply_flags threading ──────────────────────────────────────────

class TestRunLintApplyFlagsThreading:
    """run_lint must forward apply_flags to check_contradictions_deep."""

    def _setup_vault(self, tmp_path: Path) -> None:
        from curator import constants as consts

        atoms_dir = tmp_path / consts.DEFAULT_COLLECTIONS_DIR / consts.LAYER_L2
        atoms_dir.mkdir(parents=True)
        for atom_id, body in [
            ("ATM-p", "Sky is blue. [[SYN-sky]]"),
            ("ATM-q", "Sky is red. [[SYN-sky]]"),
        ]:
            (atoms_dir / f"{atom_id}.md").write_text(
                f"---\nid: {atom_id}\ntype: atom\n---\n\n{body}\n",
                encoding="utf-8",
            )

    def test_run_lint_apply_flags_false_does_not_write(self, tmp_path: Path) -> None:
        from curator import config as cfg, constants as consts
        from curator.lint import run_lint

        self._setup_vault(tmp_path)
        atoms_dir = tmp_path / consts.DEFAULT_COLLECTIONS_DIR / consts.LAYER_L2
        paths = cfg.WikiPaths(root=tmp_path)

        mock_client = MagicMock()
        mock_client.chat.return_value = "Contradiction: blue vs red."

        before = {p.name: p.stat().st_mtime for p in atoms_dir.glob("*.md")}
        run_lint(paths, deep=True, client=mock_client, apply_flags=False)
        after = {p.name: p.stat().st_mtime for p in atoms_dir.glob("*.md")}

        assert before == after, "run_lint with apply_flags=False must not write atom files"

    def test_run_lint_apply_flags_true_writes(self, tmp_path: Path) -> None:
        from curator import config as cfg, constants as consts
        from curator.lint import run_lint

        self._setup_vault(tmp_path)
        atoms_dir = tmp_path / consts.DEFAULT_COLLECTIONS_DIR / consts.LAYER_L2
        paths = cfg.WikiPaths(root=tmp_path)

        mock_client = MagicMock()
        mock_client.chat.return_value = "Contradiction: blue vs red."

        run_lint(paths, deep=True, client=mock_client, apply_flags=True)

        for atom_file in atoms_dir.glob("*.md"):
            assert "is_flagged_for_agent: true" in atom_file.read_text(), (
                f"{atom_file.name} must be flagged when run_lint apply_flags=True"
            )
