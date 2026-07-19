from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from curator import db
from curator.mcp_server import build_server


def _tools(tmp_path: Path, monkeypatch):
    curator_dir = tmp_path / ".curator"
    curator_dir.mkdir()
    (curator_dir / "settings.yml").write_text(
        "llm:\n  primary: ollama::test\n",
        encoding="utf-8",
    )
    db.init_db(db_path := tmp_path / ".curator" / "state.sqlite")
    assert db_path.exists()
    monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
    monkeypatch.setenv("CURATOR_DISABLE_INGEST_WORKER", "1")
    server = build_server()
    return getattr(server._tool_manager, "_tools", {})


def test_add_knowledge_reports_search_refresh_degradation(
    tmp_path: Path, monkeypatch
) -> None:
    tools = _tools(tmp_path, monkeypatch)
    client = MagicMock()
    monkeypatch.setattr("curator.llm.build_client", lambda _config: client)
    monkeypatch.setattr(
        "curator.query.classify_wiki_topic",
        lambda _client, _insight, _context: ("General", "captured-insight"),
    )
    monkeypatch.setattr(
        "curator.query.save_wiki_page",
        lambda *_args, **_kwargs: "02_Wiki/captured-insight.md",
    )

    def fail_index(*_args, **_kwargs):
        raise RuntimeError("index unavailable")

    monkeypatch.setattr("curator.search.update_index", fail_index)

    result = tools["curator_add_knowledge"].fn(
        insight="insight",
        context="context",
        workspace_path=str(tmp_path),
    )

    assert result["ok"] is True
    assert "index unavailable" in "\n".join(result["warnings"])
    client.close.assert_called_once_with()
