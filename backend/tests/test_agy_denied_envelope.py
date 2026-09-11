"""agy 1.2.0's exit-zero denied turn must enter graph retry, not JSON repair."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from curator import db, llm
from curator.pipeline import graph_index


DENIED = {
    "status": "SUCCESS", "num_turns": 1, "response": "",
    "denied_actions": [{"action": "command", "display_name": "RunCommand"}],
}
GRAPH = {"entities": [{
    "canonical_name": "ResNet", "entity_type": "method",
    "description": "Adds identity shortcuts to improve optimization.",
    "source_span_ids": ["SPAN-1"],
}], "relations": []}
UNITS = [{"id": "KNU-1", "source_id": 1, "unit_type": "claim",
          "statement": "ResNet uses identity shortcuts.", "source_span_ids": ["SPAN-1"]}]


@pytest.fixture()
def bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Isolate provider cache/logs and SQLite; fake only process execution, leaving
    # adapter, contract rendering/validation, trace writes and graph retry real.
    from curator import config
    monkeypatch.setattr(config, "get_global_config_dir", lambda: tmp_path / "config")
    monkeypatch.setattr(llm.AntigravityCliClient, "_sandbox_roots", lambda self: [])
    llm.clear_capacity_block(llm.AntigravityCliClient.CAPACITY_KEY)
    responses: list[dict] = []
    prompts: list[str] = []

    def run(cmd, **kwargs):
        prompts.append(cmd[cmd.index("--print") + 1])
        assert responses, "unexpected provider round trip"
        return subprocess.CompletedProcess(cmd, 0, json.dumps(responses.pop(0)), "")

    monkeypatch.setattr(llm.subprocess, "run", run)
    path = tmp_path / "state.sqlite"
    db.init_db(path)
    with db.connect(path) as conn:
        conn.execute("INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                     "VALUES ('04_Resources/probe.md', 'h', 'md', 10, datetime('now'))")
    yield llm.AntigravityCliClient(), responses, prompts, path
    llm.clear_capacity_block(llm.AntigravityCliClient.CAPACITY_KEY)


@pytest.mark.parametrize("response", ["", " \n"])
def test_denied_no_answer_is_provider_failure(bridge, response):
    client, responses, _, _ = bridge
    responses.append({**DENIED, "response": response})
    with pytest.raises(llm.AntigravityCliError, match="permission.*command"):
        client._run("extract", json_schema={"type": "object"})
    assert client.capacity_blocked_for() == 0


@pytest.mark.parametrize("payload", [GRAPH, {"entities": [], "relations": []}, {"units": []}])
def test_denied_action_does_not_erase_recovered_structure(bridge, payload):
    client, responses, _, _ = bridge
    responses.append({**DENIED, "structured_output": payload})
    assert json.loads(client._run("extract", json_schema={"type": "object"})) == payload


def test_denied_action_does_not_erase_recovered_prose(bridge):
    client, responses, _, _ = bridge
    responses.append({**DENIED, "response": json.dumps(GRAPH)})
    assert json.loads(client._run("extract", json_schema={"type": "object"})) == GRAPH


@pytest.mark.parametrize("error", ["provider rejected request", ""])
def test_explicit_error_cannot_return_a_graph_even_with_exit_zero(bridge, error):
    client, responses, _, _ = bridge
    responses.append({"status": "ERROR", "error": error, "structured_output": GRAPH})
    with pytest.raises(llm.AntigravityCliError):
        client._run("extract", json_schema={"type": "object"})


def test_exit_zero_capacity_envelope_still_blocks_provider(bridge):
    client, responses, _, _ = bridge
    responses.append({"status": "ERROR", "error": "429 RESOURCE_EXHAUSTED: capacity exhausted"})
    with pytest.raises(llm.AntigravityCliError, match="capacity"):
        client._run("extract", json_schema={"type": "object"})
    assert client.capacity_blocked_for() > 0


def test_two_denials_retry_original_graph_prompt_and_cache_only_success(bridge):
    client, responses, prompts, path = bridge
    responses.extend([DENIED, DENIED, {"status": "SUCCESS", "structured_output": GRAPH}])
    result = graph_index.extract_graph_data(path, client, units=UNITS, valid_span_ids=["SPAN-1"])
    assert result.ok, result.errors
    assert len(prompts) == 3
    assert len(set(prompts)) == 1, "provider denial must not consume JSON repair"
    assert db.count_graph_batch_results(path, 1) == 1
    with db.connect(path) as conn:
        rows = conn.execute("SELECT validator_status FROM prompt_runs").fetchall()
    assert sorted(row[0] for row in rows) == ["failed", "failed", "ok"]


def test_denial_exhaustion_keeps_earlier_batch_for_resume(bridge, monkeypatch):
    client, responses, prompts, path = bridge
    monkeypatch.setattr(llm.AntigravityCliClient, "optimal_chunk_chars", property(lambda self: 1000))
    monkeypatch.setattr(graph_index, "_MAX_BATCH_ATTEMPTS", 2)
    units = [{**UNITS[0], "id": f"KNU-{i}", "statement": str(i) * 480} for i in (1, 2)]
    responses.extend([{"status": "SUCCESS", "structured_output": GRAPH}, DENIED, DENIED])
    failed = graph_index.extract_graph_data(path, client, units=units, valid_span_ids=["SPAN-1"])
    assert not failed.ok
    assert any("permission" in error for error in failed.errors)
    assert db.count_graph_batch_results(path, 1) == 1
    before = len(prompts)
    responses.append({"status": "SUCCESS", "structured_output": GRAPH})
    resumed = graph_index.extract_graph_data(path, client, units=units, valid_span_ids=["SPAN-1"])
    assert resumed.ok and len(prompts) == before + 1
    assert db.count_graph_batch_results(path, 1) == 2
    assert len(resumed.entities) == 2



def test_live_flag_cannot_bypass_provider_spawn_guard(monkeypatch):
    """Even a stale opt-in must not launch agy under pytest's isolated HOME."""
    import runpy
    block_real_provider_cli = runpy.run_path(str(Path(__file__).with_name("conftest.py")))[
        "block_real_provider_cli"
    ]

    calls = []
    monkeypatch.setenv("INCURATOR_LIVE_AGY", "1")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: calls.append(a))
    block_real_provider_cli.__wrapped__(monkeypatch)
    with pytest.raises(AssertionError, match="real 'agy' CLI"):
        subprocess.run(["sandbox-exec", "-p", "profile", "--", "agy", "--print", "test"])
    assert calls == []
