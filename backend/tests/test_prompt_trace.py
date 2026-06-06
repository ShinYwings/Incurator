"""Phase 1 (v0.3.1): run_prompt end-to-end tracing and repair."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from curator import db, prompting
from curator.llm import ChatMessage


class FakeClient:
    """Minimal LLM client double. Returns queued responses in order."""

    def __init__(self, responses: list[str], model: str = "fake-model") -> None:
        self._responses = list(responses)
        self.model = model
        self.calls: list[list[ChatMessage]] = []

    def chat(self, messages, *, json_mode=False, temperature=0.3) -> str:
        self.calls.append(list(messages))
        return self._responses.pop(0)


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
    assert run["prompt_version"] == "v1"
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
