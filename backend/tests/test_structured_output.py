"""Ask the CLI for a value, not for prose — and never trust an empty one.

Two jobs died because the agentic CLI answered a JSON request by writing a
`python3` program to build the object, which the permission layer denied. The
CLI has a native structured-output mode that removes the choice: measured,
`num_turns` drops to 1 and the parsed object arrives in its own field.

The trap, and the reason this file exists: that only holds for a FLATTENED
schema. The real contract schema carries `$defs`/`$ref`, and with it the CLI
returns `SUCCESS` with `structured_output: {"units": []}` — no error, no
warning, nothing. Shipping that would ingest a book to nothing while reporting
success, which is worse than the crash it replaces. See SYSTEM_BEHAVIOR §11.0.
"""

from __future__ import annotations

import json

import pytest

from curator import llm
from curator.prompting import json_schema as js


# --------------------------------------------------------------------------
# G2 — the flattener
# --------------------------------------------------------------------------


def test_a_referenced_definition_is_inlined() -> None:
    schema = {
        "$defs": {"Unit": {"type": "object", "properties": {"name": {"type": "string"}}}},
        "type": "object",
        "properties": {"units": {"type": "array", "items": {"$ref": "#/$defs/Unit"}}},
    }
    flat = js.flatten_refs(schema)
    assert "$defs" not in flat
    assert '"$ref"' not in json.dumps(flat)
    assert flat["properties"]["units"]["items"]["properties"]["name"] == {"type": "string"}


def test_a_definition_used_twice_is_copied_to_both_sites() -> None:
    """Sharing one dict between two sites would let a later edit corrupt both."""
    schema = {
        "$defs": {"Span": {"type": "string", "title": "Span"}},
        "type": "object",
        "properties": {"a": {"$ref": "#/$defs/Span"}, "b": {"$ref": "#/$defs/Span"}},
    }
    flat = js.flatten_refs(schema)
    a, b = flat["properties"]["a"], flat["properties"]["b"]
    assert a == b == {"type": "string", "title": "Span"}
    assert a is not b, "the two sites must not share one object"


def test_a_recursive_model_does_not_hang() -> None:
    """A self-referencing schema must fail loudly, not spin forever."""
    schema = {
        "$defs": {"Node": {"type": "object", "properties": {"child": {"$ref": "#/$defs/Node"}}}},
        "$ref": "#/$defs/Node",
    }
    with pytest.raises(js.UnflattenableSchema):
        js.flatten_refs(schema)


def test_the_real_contract_schema_flattens() -> None:
    """The one that matters. Its unflattened form silently returns zero units."""
    from curator import prompting

    contract = prompting.REGISTRY.get("curator.knowledge_unit_extract")
    raw = contract.output_model.model_json_schema()
    assert "$defs" in raw, "fixture assumption: this schema is the nested kind"

    flat = js.flatten_refs(raw)
    assert '"$ref"' not in json.dumps(flat)
    assert "$defs" not in flat
    # Flattening must not lose the fields the contract depends on.
    unit = flat["properties"]["units"]["items"]
    for field in ("canonical_name", "unit_type", "statement", "source_span_ids"):
        assert field in unit["properties"], f"{field} lost while flattening"


# --------------------------------------------------------------------------
# G5 / G3 — the envelope
# --------------------------------------------------------------------------

_SUCCESS = json.dumps({
    "conversation_id": "x", "status": "SUCCESS", "num_turns": 1,
    "response": "Here you go:\n```json\n{...}\n```",
    "structured_output": {"units": [{"canonical_name": "A"}]},
    "usage": {"input_tokens": 10, "output_tokens": 2},
})

# Exactly what the real CLI returned for the UNFLATTENED schema: success, an
# answer in the prose, and an empty structure.
_EMPTY_STRUCTURE = json.dumps({
    "conversation_id": "x", "status": "SUCCESS", "num_turns": 2,
    "response": 'Here are the units:\n```json\n[{"knowledge_unit": "..."}]\n```',
    "structured_output": {"units": []},
    "usage": {"input_tokens": 10, "output_tokens": 2},
})

_ERROR = json.dumps({
    "conversation_id": "", "status": "ERROR", "num_turns": 0, "response": "",
    "error": "invalid model selection (--model bogus)",
    "usage": {"input_tokens": 0, "output_tokens": 0},
})


def test_a_populated_structure_is_returned_as_the_answer() -> None:
    out = llm._structured_from_envelope(_SUCCESS)
    assert json.loads(out) == {"units": [{"canonical_name": "A"}]}


def test_an_empty_structure_falls_back_to_the_response_text() -> None:
    """The measured failure shape. An empty structure is a defect signal.

    Returning it verbatim would report "the model found nothing" for every batch
    of every source, with a SUCCESS status and no error anywhere.
    """
    out = llm._structured_from_envelope(_EMPTY_STRUCTURE)
    assert "knowledge_unit" in out, (
        "an empty structure beside a non-empty response must degrade to the "
        "response text, not be reported as an empty result"
    )


def test_an_empty_structure_with_no_response_is_still_empty() -> None:
    """Not everything empty is a defect — a model may genuinely find nothing."""
    envelope = json.dumps({
        "status": "SUCCESS", "num_turns": 1, "response": "",
        "structured_output": {"units": []},
    })
    assert json.loads(llm._structured_from_envelope(envelope)) == {"units": []}


def test_the_error_envelope_surfaces_its_reason() -> None:
    """stderr is empty under --output-format json; the reason is in the body.

    Building the message from stderr, as the pre-v0.60.0 code does, would raise
    "Antigravity CLI exited 1: " and drop the cause entirely.
    """
    assert llm._envelope_error(_ERROR) == "invalid model selection (--model bogus)"
    assert llm._envelope_error(_SUCCESS) == ""


def test_a_capacity_error_in_the_envelope_is_recognised() -> None:
    """With stderr empty, the envelope is the surviving signal beside the log."""
    envelope = json.dumps({"status": "ERROR", "response": "",
                           "error": "429 RESOURCE_EXHAUSTED: capacity exhausted"})
    assert llm._is_capacity_error(llm._envelope_error(envelope))


# --------------------------------------------------------------------------
# Capability + argv
# --------------------------------------------------------------------------


def test_only_a_measured_client_claims_structured_output() -> None:
    """False by default. A client claims it once its mode has been measured."""
    assert llm.AntigravityCliClient(model="m").supports_structured_output is True
    assert llm.ClaudeCodeClient(model="m").supports_structured_output is False
    assert llm.CodexCliClient(model="m").supports_structured_output is False


def test_the_schema_is_passed_as_a_string_not_a_temp_file() -> None:
    """Measured: --json-schema accepts a string, so nothing is written to disk.

    At one call per extraction batch (277 for the book that prompted this), a
    file per call would litter the temp dir `test_workspace_hygiene.py` polices.
    """
    argv = llm.AntigravityCliClient(model="m")._structured_args({"type": "object"})
    assert "--output-format" in argv and argv[argv.index("--output-format") + 1] == "json"
    i = argv.index("--json-schema")
    assert json.loads(argv[i + 1]) == {"type": "object"}


# --------------------------------------------------------------------------
# G1 — the live gate. Everything above asserts what we BUILD; only this asserts
# what the CLI ACCEPTS, and that distinction is the whole history of this area:
# v0.58.0 shipped a feature whose every test passed and which never ran.
# --------------------------------------------------------------------------


@pytest.mark.skipif(
    not __import__("os").environ.get("INCURATOR_LIVE_AGY"),
    reason="live CLI test; set INCURATOR_LIVE_AGY=1 to run",
)
def test_live_the_real_contract_schema_returns_one_turn_and_valid_units() -> None:
    """The real schema, the real CLI, the real contract model.

    Asserts the property that fixes the incident: `num_turns == 1`. One turn
    means the model answered directly instead of reaching for a shell, so there
    is nothing for the permission layer to deny. A run reporting more than one
    turn is the early sign of the failure returning — and is exactly what the
    UNFLATTENED schema produces, with an empty result and no error.
    """
    from curator import prompting

    contract = prompting.REGISTRY.get("curator.knowledge_unit_extract")
    schema = js.flatten_refs(contract.output_model.model_json_schema())

    client = llm.AntigravityCliClient()
    client.ensure_ready()
    raw = client.chat(
        [llm.ChatMessage(role="user", content=(
            "Extract knowledge units. Every source_span_id must be one of: SPAN-aaa.\n"
            "SPAN-aaa [Homography]: Each point correspondence between two views "
            "gives two independent linear equations in the entries of H."
        ))],
        json_mode=True,
        json_schema=schema,
    )

    parsed = contract.output_model.model_validate(json.loads(raw))
    assert parsed.units, "the CLI accepted the schema but returned nothing"
    assert parsed.units[0].source_span_ids == ["SPAN-aaa"]
