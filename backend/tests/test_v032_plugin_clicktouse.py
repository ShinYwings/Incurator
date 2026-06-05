"""v0.3.2 Phase 10: plugin click-to-use JSON commands (trace/insight).

DB-backed commands only — no LLM. The correction-propose command is LLM-gated and
verified separately (degrades to {"ok": false} without a backend).
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from curator import config as cfg
from curator import db
from curator.cli import app


def _json_output(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    assert start >= 0 and end > start, text
    return json.loads(text[start : end + 1])


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    paths = cfg.WikiPaths(vault)
    paths.internal.mkdir(parents=True, exist_ok=True)
    cfg.save_config(paths, {})
    db.init_db(paths.state_db)
    return vault


def test_plugin_trace_list_and_show(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = _vault(tmp_path)
    db_path = cfg.WikiPaths(vault).state_db
    tid = db.insert_query_trace(
        db_path, route="local", question_hash="qh", workspace_id="vault",
        retrieval_trace={"fallback_mode": "no_rerank", "intent": "definition"},
        warnings=["no reranker configured: returned RRF order"], latency_ms=12,
        evidence=[{"doc_id": "DOC-1", "record_id": "ATM-1", "score": 0.5}],
    )

    listed = runner.invoke(app, ["plugin", "trace", "list", "--workspace-path", str(vault)])
    assert listed.exit_code == 0, listed.output
    data = _json_output(listed.output)
    assert data["ok"] is True
    assert data["traces"][0]["traceId"] == tid
    assert data["traces"][0]["fallbackMode"] == "no_rerank"

    shown = runner.invoke(app, ["plugin", "trace", "show", "--trace-id", tid, "--workspace-path", str(vault)])
    assert shown.exit_code == 0, shown.output
    trace = _json_output(shown.output)["trace"]
    assert trace["route"] == "local"
    assert trace["retrievalTrace"]["intent"] == "definition"
    assert trace["evidence"][0]["record_id"] == "ATM-1"


def test_plugin_trace_show_unknown(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = _vault(tmp_path)
    result = runner.invoke(app, ["plugin", "trace", "show", "--trace-id", "QTR-nope", "--workspace-path", str(vault)])
    assert result.exit_code == 1
    assert _json_output(result.output)["ok"] is False


def test_plugin_insight_show_and_reject(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = _vault(tmp_path)
    db_path = cfg.WikiPaths(vault).state_db
    ins_id = db.create_insight_candidate(
        db_path, classification="derived_insight", statement="X implies Y",
        workspace_id="vault", affected_node_ids=["SYN-1"], confidence=0.7,
    )

    shown = runner.invoke(app, ["plugin", "insight", "show", "--insight-id", ins_id, "--workspace-path", str(vault)])
    assert shown.exit_code == 0, shown.output
    cand = _json_output(shown.output)["candidate"]
    assert cand["id"] == ins_id and cand["status"] == "pending"

    rejected = runner.invoke(
        app, ["plugin", "insight", "reject", "--insight-id", ins_id, "--reason", "off-topic", "--workspace-path", str(vault)]
    )
    assert rejected.exit_code == 0, rejected.output
    assert _json_output(rejected.output)["status"] == "rejected"
    # persisted
    assert db.get_insight_candidate(db_path, ins_id)["status"] == "rejected"


def test_plugin_insight_reject_unknown(tmp_path: Path) -> None:
    runner = CliRunner()
    vault = _vault(tmp_path)
    result = runner.invoke(app, ["plugin", "insight", "reject", "--insight-id", "INS-nope", "--workspace-path", str(vault)])
    assert result.exit_code == 1
    assert _json_output(result.output)["ok"] is False


def test_plugin_models_status(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    vault = _vault(tmp_path)
    # Isolate the model cache so presence is deterministic (no host GGUFs).
    monkeypatch.setenv("INCURATOR_MODELS_DIR", str(tmp_path / "models"))
    result = runner.invoke(app, ["plugin", "models", "status", "--workspace-path", str(vault)])
    assert result.exit_code == 0, result.output
    data = _json_output(result.output)
    assert data["ok"] is True
    assert "embed" in data and "reranker" in data
    assert data["embed"]["model"]  # identity exposed to the plugin
    assert data["embed"]["present"] is False  # empty isolated cache
    assert "ollamaReachable" in data and "llama_cpp_installed" in data


def test_plugin_models_refresh(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    vault = _vault(tmp_path)
    from curator import model_setup

    def _fake_ensure(paths, **kw):
        rep = model_setup.ModelReport()
        rep.add("ollama-serving", True, "already running")
        rep.add("reranker-gguf", True, "downloaded")
        return rep

    monkeypatch.setattr(model_setup, "ensure_search_models", _fake_ensure)
    result = runner.invoke(app, ["plugin", "models", "refresh", "--workspace-path", str(vault)])
    assert result.exit_code == 0, result.output
    data = _json_output(result.output)
    assert data["ok"] is True
    assert [s["name"] for s in data["steps"]] == ["ollama-serving", "reranker-gguf"]
