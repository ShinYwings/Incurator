from pathlib import Path
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
