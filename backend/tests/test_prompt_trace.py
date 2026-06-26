"""Phase 1 (v0.3.1): run_prompt end-to-end tracing and repair."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from curator import db, prompting
from curator.llm import ChatMessage
from curator.prompting.trace import hash_prompt_output


class FakeClient:
    """Minimal LLM client double. Returns queued responses in order."""

    def __init__(self, responses: list[str | Exception], model: str = "fake-model") -> None:
        self._responses = list(responses)
        self.model = model
        self.calls: list[list[ChatMessage]] = []

    def chat(self, messages, *, json_mode=False, temperature=0.3) -> str:
        self.calls.append(list(messages))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture()
def db_path() -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.sqlite"
        db.init_db(path)
        yield path


def _valid_ku_output() -> str:
    return json.dumps(
        {
            "units": [
                {
                    "canonical_name": "Residual learning",
                    "unit_type": "claim",
                    "statement": "Residual connections ease optimization.",
                    "source_span_ids": ["SPAN-aaaa1111"],
                    "confidence": 0.9,
                    "truth_status": "source_supported",
                }
            ]
        }
    )


def test_run_prompt_persists_trace(db_path: Path) -> None:
    contract = prompting.REGISTRY.get("curator.knowledge_unit_extract")
    client = FakeClient([_valid_ku_output()])
    input_obj = contract.input_model(
        source_title="ResNet",
        spans_block="SPAN-aaaa1111: Residual connections ...",
        valid_span_ids_block="SPAN-aaaa1111",
    )
    result = prompting.run_prompt(
        db_path,
        client,
        contract,
        input_obj,
        validation_context={"valid_span_ids": ["SPAN-aaaa1111"]},
        source_ids=[1],
    )
    assert result.ok
    assert result.parsed is not None
    assert result.parsed.units[0].canonical_name == "Residual learning"

    run = db.get_prompt_run(db_path, result.trace_id)
    assert run is not None
    assert run["prompt_id"] == "curator.knowledge_unit_extract"
    assert run["prompt_version"] == "v3"
    assert run["validator_status"] == "ok"
    assert run["model_name"] == "fake-model"
    assert run["input_hash"]
    assert run["output_hash"]
    assert run["finished_at"]
    assert run["source_ids"] == [1]


def test_run_prompt_repairs_invalid_json_once(db_path: Path) -> None:
    contract = prompting.REGISTRY.get("curator.knowledge_unit_extract")
    # First response is broken JSON; repair returns valid output.
    client = FakeClient(["not json at all", _valid_ku_output()])
    input_obj = contract.input_model(
        source_title="ResNet",
        spans_block="...",
        valid_span_ids_block="SPAN-aaaa1111",
    )
    result = prompting.run_prompt(
        db_path,
        client,
        contract,
        input_obj,
        validation_context={"valid_span_ids": ["SPAN-aaaa1111"]},
    )
    assert result.retry_count == 1
    assert result.ok
    assert len(client.calls) == 2  # original + one repair

    run = db.get_prompt_run(db_path, result.trace_id)
    assert run["validator_status"] == "repaired"
    assert run["retry_count"] == 1


def test_run_prompt_marks_failed_when_invented_span(db_path: Path) -> None:
    contract = prompting.REGISTRY.get("curator.knowledge_unit_extract")
    bad = json.dumps(
        {
            "units": [
                {
                    "canonical_name": "x",
                    "unit_type": "claim",
                    "statement": "y",
                    "source_span_ids": ["SPAN-invented"],
                    "confidence": 0.5,
                    "truth_status": "source_supported",
                }
            ]
        }
    )
    client = FakeClient([bad, bad])  # repair also bad
    input_obj = contract.input_model(
        source_title="t", spans_block="s", valid_span_ids_block="SPAN-aaaa1111"
    )
    result = prompting.run_prompt(
        db_path,
        client,
        contract,
        input_obj,
        validation_context={"valid_span_ids": ["SPAN-aaaa1111"]},
    )
    assert not result.ok
    run = db.get_prompt_run(db_path, result.trace_id)
    assert run["validator_status"] == "failed"
    assert run["validator_errors"]


def test_run_prompt_marks_trace_failed_when_client_raises(db_path: Path) -> None:
    contract = prompting.REGISTRY.get("curator.knowledge_unit_extract")
    client = FakeClient([RuntimeError("provider unavailable")])
    input_obj = contract.input_model(
        source_title="t", spans_block="s", valid_span_ids_block="SPAN-aaaa1111"
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        prompting.run_prompt(
            db_path,
            client,
            contract,
            input_obj,
            validation_context={"valid_span_ids": ["SPAN-aaaa1111"]},
        )

    with db.connect(db_path) as conn:
        rows = [dict(row) for row in conn.execute("SELECT * FROM prompt_runs")]
    assert len(rows) == 1
    assert rows[0]["validator_status"] == "failed"
    assert "RuntimeError: provider unavailable" in rows[0]["validator_errors"]
    assert rows[0]["finished_at"]


def test_run_prompt_original_exception_survives_trace_write_failure(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """finish_prompt_run failure must never mask the original provider error."""
    contract = prompting.REGISTRY.get("curator.knowledge_unit_extract")
    client = FakeClient([RuntimeError("capacity exhausted")])
    input_obj = contract.input_model(
        source_title="t", spans_block="s", valid_span_ids_block="SPAN-aaaa1111"
    )

    import curator.prompting.runner as runner_mod

    def _bad_finish(*args, **kwargs) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(runner_mod, "finish_prompt_run", _bad_finish)

    with pytest.raises(RuntimeError, match="capacity exhausted"):
        prompting.run_prompt(
            db_path,
            client,
            contract,
            input_obj,
            validation_context={"valid_span_ids": ["SPAN-aaaa1111"]},
        )


def test_run_prompt_trace_records_first_response_when_repair_call_raises(
    db_path: Path,
) -> None:
    """When the repair call raises, the trace must record the first response, not empty."""
    contract = prompting.REGISTRY.get("curator.knowledge_unit_extract")
    first_raw = "NOT_JSON_BUT_REAL_RESPONSE"
    # First call returns invalid JSON → triggers repair; second call raises.
    client = FakeClient([first_raw, RuntimeError("repair call failed")])
    input_obj = contract.input_model(
        source_title="t", spans_block="s", valid_span_ids_block="SPAN-aaaa1111"
    )

    with pytest.raises(RuntimeError, match="repair call failed"):
        prompting.run_prompt(
            db_path,
            client,
            contract,
            input_obj,
            validation_context={"valid_span_ids": ["SPAN-aaaa1111"]},
        )

    with db.connect(db_path) as conn:
        rows = [dict(row) for row in conn.execute("SELECT * FROM prompt_runs")]
    assert len(rows) == 1
    assert rows[0]["validator_status"] == "failed"
    assert rows[0]["output_hash"] == hash_prompt_output(first_raw)
