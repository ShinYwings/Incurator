from pathlib import Path

import pytest

from curator.curate_yml import load_curate_spec


def test_goal_field_primary(tmp_path: Path):
    """Canonical curate.yml uses 'goal' field."""
    curate_file = tmp_path / "curate.yml"
    curate_file.write_text("""
project: "Modern Project"
description: "A modern project"
persona:
  domain: "test"
  subdomain: "modern"
  goal: "This is the canonical goal field."
  output_intent: "engineer"
  disambiguation_keywords: ["modern"]
""")
    spec = load_curate_spec(tmp_path)
    assert spec is not None
    assert spec.project == "Modern Project"
    assert spec.persona.goal == "This is the canonical goal field."


def test_text_forward_compat(tmp_path: Path):
    """curate.yml with 'text:' (new field name) still loads into .goal for forward compat."""
    curate_file = tmp_path / "curate.yml"
    curate_file.write_text("""
project: "Compat Project"
description: "A compat project"
persona:
  domain: "test"
  subdomain: "compat"
  text: "This is a text field."
  output_intent: "researcher"
  disambiguation_keywords: ["compat"]
""")
    spec = load_curate_spec(tmp_path)
    assert spec is not None
    assert spec.persona.goal == "This is a text field."


def test_goal_takes_priority_over_text(tmp_path: Path):
    """If both 'goal' and 'text' are present, 'goal' wins."""
    curate_file = tmp_path / "curate.yml"
    curate_file.write_text("""
project: "Mixed Project"
persona:
  domain: "test"
  goal: "This is goal."
  text: "This is text."
""")
    spec = load_curate_spec(tmp_path)
    assert spec is not None
    assert spec.persona.goal == "This is goal."


def test_confidence_parsed(tmp_path: Path):
    """Explicit confidence block is parsed correctly."""
    curate_file = tmp_path / "curate.yml"
    curate_file.write_text("""
project: "Confidence Project"
persona:
  domain: "test"
  text: "Test workspace."
  confidence:
    high_threshold: 0.80
    low_threshold: 0.50
""")
    spec = load_curate_spec(tmp_path)
    assert spec is not None
    assert spec.persona.confidence == {"high_threshold": 0.80, "low_threshold": 0.50}


def test_confidence_defaults(tmp_path: Path):
    """curate.yml without confidence block gets default thresholds."""
    curate_file = tmp_path / "curate.yml"
    curate_file.write_text("""
project: "No Confidence Project"
persona:
  domain: "test"
  text: "Test workspace."
""")
    spec = load_curate_spec(tmp_path)
    assert spec is not None
    assert spec.persona.confidence == {"high_threshold": 0.85, "low_threshold": 0.55}


def test_confidence_missing_persona(tmp_path: Path):
    """curate.yml without any persona block gets default confidence."""
    curate_file = tmp_path / "curate.yml"
    curate_file.write_text("""
project: "Bare Project"
""")
    spec = load_curate_spec(tmp_path)
    assert spec is not None
    assert spec.persona.confidence == {"high_threshold": 0.85, "low_threshold": 0.55}
    assert spec.persona.goal == ""


# ── G11-4 regression tests ──────────────────────────────────────────────────

def test_bool_string_false_not_inverted(tmp_path: Path):
    """bool("false") == True in Python; curate.yml loader must treat it as False."""
    (tmp_path / "curate.yml").write_text("""
project: "Bool String Test"
persona:
  domain: "test"
  text: "Test."
verification:
  allow_general_knowledge: "false"
  require_source_spans: "true"
reasoning:
  exploration_enabled: "false"
  require_insight_candidates: "true"
""")
    spec = load_curate_spec(tmp_path)
    assert spec is not None
    assert spec.verification.allow_general_knowledge is False, "string 'false' must parse as False"
    assert spec.verification.require_source_spans is True, "string 'true' must parse as True"
    assert spec.reasoning.exploration_enabled is False, "string 'false' must parse as False"
    assert spec.reasoning.require_insight_candidates is True, "string 'true' must parse as True"


def test_bool_variants(tmp_path: Path):
    """Various YAML-style truthy/falsy strings are accepted."""
    (tmp_path / "curate.yml").write_text("""
project: "Bool Variants"
persona:
  domain: "test"
  text: "Test."
verification:
  allow_general_knowledge: "yes"
  require_source_spans: "no"
""")
    spec = load_curate_spec(tmp_path)
    assert spec is not None
    assert spec.verification.allow_general_knowledge is True
    assert spec.verification.require_source_spans is False


def test_str_list_scalar_include(tmp_path: Path):
    """A scalar string for `include` is treated as a one-item list, not dropped."""
    (tmp_path / "curate.yml").write_text("""
project: "Scalar Include"
persona:
  domain: "test"
  text: "Test."
sources:
  include: "03_Notes/**"
""")
    spec = load_curate_spec(tmp_path)
    assert spec is not None
    assert spec.sources.include == ["03_Notes/**"], (
        "scalar include must be wrapped; empty list means 'all sources' which is wrong here"
    )


@pytest.mark.parametrize(
    "sources_yaml",
    [
        "sources: []",
        "sources:\n  include: 42",
        "sources:\n  include: {path: 03_Notes/**}",
        "sources:\n  include: [03_Notes/**, 42]",
        "sources:\n  exclude: [[03_Notes/private/**]]",
    ],
)
def test_invalid_source_scope_shape_fails_closed(
    tmp_path: Path, sources_yaml: str
) -> None:
    (tmp_path / "curate.yml").write_text(
        f'project: "Scoped"\n{sources_yaml}\n', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="sources"):
        load_curate_spec(tmp_path)


def test_backprop_enabled_string(tmp_path: Path):
    """backprop.enabled accepts string 'false'."""
    (tmp_path / "curate.yml").write_text("""
project: "Backprop Str"
persona:
  domain: "test"
  text: "Test."
backprop:
  enabled: "false"
""")
    spec = load_curate_spec(tmp_path)
    assert spec is not None
    assert spec.backprop.enabled is False
