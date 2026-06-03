"""Phase 1 (v0.3.1): prompt rendering and family contract behavior."""

from __future__ import annotations

import pytest

from curator import prompting
from curator.prompting.render import render_prompt, render_template


def test_render_template_substitutes_placeholders() -> None:
    out = render_template("Hello {{ name }}, see {{ n }}", {"name": "A", "n": 3})
    assert out == "Hello A, see 3"


def test_render_template_unknown_field_raises() -> None:
    with pytest.raises(KeyError):
        render_template("Hi {{ missing }}", {"name": "A"})


def test_render_template_preserves_literal_json_braces() -> None:
    # JSON braces in templates must not be treated as placeholders.
    tmpl = 'Return {"key": "value"} for {{ topic }}'
    out = render_template(tmpl, {"topic": "x"})
    assert '{"key": "value"}' in out
    assert out.endswith("for x")


def test_render_prompt_produces_system_and_user_messages() -> None:
    contract = prompting.REGISTRY.get("curator.source_map")
    input_obj = contract.input_model(source_title="T", source_text="body")
    rendered = render_prompt(contract, input_obj)
    assert [m.role for m in rendered.messages] == ["system", "user"]
    assert "T" in rendered.messages[1].content
    assert "body" in rendered.messages[1].content
    assert rendered.input_hash


def test_input_hash_is_deterministic_and_input_sensitive() -> None:
    contract = prompting.REGISTRY.get("curator.source_map")
    a = render_prompt(contract, contract.input_model(source_title="T", source_text="x"))
    b = render_prompt(contract, contract.input_model(source_title="T", source_text="x"))
    c = render_prompt(contract, contract.input_model(source_title="T", source_text="y"))
    assert a.input_hash == b.input_hash
    assert a.input_hash != c.input_hash


def test_extraction_contracts_require_source_spans_flag() -> None:
    for pid in (
        "curator.knowledge_unit_extract",
        "curator.entity_relation_extract",
    ):
        assert prompting.REGISTRY.get(pid).requires_source_spans


def test_backprop_classify_contract_has_classification_model() -> None:
    contract = prompting.REGISTRY.get("curator.backprop_classify")
    fields = contract.output_model.model_fields
    assert "classification" in fields
    assert "source_truth_impact" in fields
