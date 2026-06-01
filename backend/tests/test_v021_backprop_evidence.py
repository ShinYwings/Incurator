import tempfile
from pathlib import Path
import json

from curator import config as cfg
from curator import sync
from curator import mcp_server


class FakeBackpropClient:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, *_args, **_kwargs) -> str:
        self.calls += 1
        if self.calls == 1:
            return """---
id: CON-test0001
type: concept
name: Updated Concept
domain: Test
confidence_score: 0.9
---

# Updated Concept

Concept body updated from exhibition.

## Relations

- Supports: [[02_Atoms/ATM-test0001]]
"""
        if self.calls == 2:
            return """---
id: ATM-test0001
type: atom
parent_source: "[[01_Contexts/CTX-test0001]]"
source_path: source.md
claim_type: fact
confidence_score: 0.9
is_verified_by_human: true
is_flagged_for_agent: false
---

# Updated Atom

Atom body updated from concept.
"""
        return """---
id: CTX-test0001
type: context
source_path: source.md
---

# Updated Context

Context body updated from atom.
"""


def test_exhibition_backprop_updates_referenced_dag_pages() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = cfg.WikiPaths(Path(tmp))
        for folder in (paths.contexts, paths.atoms, paths.concepts, paths.exhibitions):
            folder.mkdir(parents=True, exist_ok=True)

        (paths.contexts / "CTX-test0001.md").write_text(
            """---
id: CTX-test0001
type: context
source_path: source.md
---

# Original Context
""",
            encoding="utf-8",
        )
        (paths.atoms / "ATM-test0001.md").write_text(
            """---
id: ATM-test0001
type: atom
parent_source: "[[01_Contexts/CTX-test0001]]"
source_path: source.md
claim_type: fact
confidence_score: 0.8
is_verified_by_human: false
is_flagged_for_agent: false
---

# Original Atom
""",
            encoding="utf-8",
        )
        (paths.concepts / "CON-test0001.md").write_text(
            """---
id: CON-test0001
type: concept
name: Original Concept
domain: Test
confidence_score: 0.8
---

# Original Concept

## Relations

- Supports: [[02_Atoms/ATM-test0001]]
""",
            encoding="utf-8",
        )
        (paths.exhibitions / "EXH-test0001.md").write_text(
            """---
id: EXH-test0001
type: exhibition
core_concepts:
  - "[[03_Concepts/CON-test0001]]"
---

# Corrected Exhibition

The concept should be updated.
""",
            encoding="utf-8",
        )

        result = sync.propagate_upstream_from_exhibition(
            paths, FakeBackpropClient(), exh_id="EXH-test0001", propagate_sources=True
        )

        assert result.errors == []
        assert result.concepts_updated == ["CON-test0001"]
        assert result.atoms_updated == ["ATM-test0001"]
        assert result.contexts_updated == ["CTX-test0001"]
        assert "Updated Concept" in (paths.concepts / "CON-test0001.md").read_text(encoding="utf-8")
        assert "Updated Atom" in (paths.atoms / "ATM-test0001.md").read_text(encoding="utf-8")
        assert "Updated Context" in (paths.contexts / "CTX-test0001.md").read_text(encoding="utf-8")


class FakeBackpropClientNoSource:
    """Returns atom update without parent_source, triggering feedback_required."""

    def chat(self, *_args, **_kwargs) -> str:
        return """---
id: CON-test0002
type: concept
name: Orphan Concept
domain: Test
confidence_score: 0.9
---

# Orphan Concept

## Relations

- Supports: [[02_Atoms/ATM-test0002]]
"""


def test_backprop_feedback_required_when_atom_has_no_source() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = cfg.WikiPaths(Path(tmp))
        for folder in (paths.contexts, paths.atoms, paths.concepts, paths.exhibitions):
            folder.mkdir(parents=True, exist_ok=True)

        (paths.atoms / "ATM-test0002.md").write_text(
            """---
id: ATM-test0002
type: atom
claim_type: fact
confidence_score: 0.8
is_verified_by_human: false
is_flagged_for_agent: false
---

# Orphan Atom — no parent_source
""",
            encoding="utf-8",
        )
        (paths.concepts / "CON-test0002.md").write_text(
            """---
id: CON-test0002
type: concept
name: Orphan Concept
domain: Test
confidence_score: 0.8
---

# Orphan Concept

## Relations

- Supports: [[02_Atoms/ATM-test0002]]
""",
            encoding="utf-8",
        )
        (paths.exhibitions / "EXH-test0002.md").write_text(
            """---
id: EXH-test0002
type: exhibition
core_concepts:
  - "[[03_Concepts/CON-test0002]]"
---

# Exhibition referencing orphan atom
""",
            encoding="utf-8",
        )

        result = sync.propagate_upstream_from_exhibition(
            paths, FakeBackpropClientNoSource(), exh_id="EXH-test0002", propagate_sources=True
        )

        assert result.errors == []
        assert result.concepts_updated == ["CON-test0002"]
        assert result.atoms_updated == ["ATM-test0002"]
        # No CTX updated — atom had no parent_source
        assert result.contexts_updated == []
        # feedback_required must contain at least one entry for the orphan atom
        assert len(result.feedback_required) >= 1
        fb = result.feedback_required[0]
        assert fb.get("atom_id") == "ATM-test0002"


class FakeConceptOnlyClient:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, *_args, **_kwargs) -> str:
        self.calls += 1
        return """---
id: CON-test0003
type: concept
name: Interpretive Concept
domain: Test
confidence_score: 0.9
---

# Interpretive Concept

Concept body updated from an Exhibition-level insight.

## Relations

- Supports: [[02_Atoms/ATM-test0003]]
"""


def test_backprop_can_skip_source_propagation_when_explicitly_requested() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = cfg.WikiPaths(Path(tmp))
        for folder in (paths.contexts, paths.atoms, paths.concepts, paths.exhibitions):
            folder.mkdir(parents=True, exist_ok=True)

        (paths.contexts / "CTX-test0003.md").write_text(
            """---
id: CTX-test0003
type: context
source_path: source.md
---

# Original Context
""",
            encoding="utf-8",
        )
        (paths.atoms / "ATM-test0003.md").write_text(
            """---
id: ATM-test0003
type: atom
parent_source: "[[01_Contexts/CTX-test0003]]"
source_path: source.md
claim_type: fact
confidence_score: 0.8
is_verified_by_human: false
is_flagged_for_agent: false
---

# Original Atom
""",
            encoding="utf-8",
        )
        (paths.concepts / "CON-test0003.md").write_text(
            """---
id: CON-test0003
type: concept
name: Original Concept
domain: Test
confidence_score: 0.8
---

# Original Concept

## Relations

- Supports: [[02_Atoms/ATM-test0003]]
""",
            encoding="utf-8",
        )
        (paths.exhibitions / "EXH-test0003.md").write_text(
            """---
id: EXH-test0003
type: exhibition
core_concepts:
  - "[[03_Concepts/CON-test0003]]"
---

# Interpretive Exhibition Update
""",
            encoding="utf-8",
        )

        client = FakeConceptOnlyClient()
        result = sync.propagate_upstream_from_exhibition(
            paths, client, exh_id="EXH-test0003", propagate_sources=False
        )

        assert result.errors == []
        assert result.concepts_updated == ["CON-test0003"]
        assert result.atoms_updated == []
        assert result.contexts_updated == []
        assert result.source_propagation_skipped is True
        assert result.llm_calls == 1
        assert client.calls == 1
        assert "Original Atom" in (paths.atoms / "ATM-test0003.md").read_text(encoding="utf-8")
        assert "Original Context" in (paths.contexts / "CTX-test0003.md").read_text(encoding="utf-8")


class FakeTargetedConceptClient:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, *_args, **_kwargs) -> str:
        self.calls += 1
        return """---
id: CON-dyn0001
type: concept
name: Dynamics Concept
domain: Test
confidence_score: 0.9
---

# Dynamics Concept

Neural ODE and forward Euler interpretation added from the Exhibition insight.
"""


def test_backprop_targets_concepts_from_added_exhibition_text() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = cfg.WikiPaths(Path(tmp))
        for folder in (paths.contexts, paths.atoms, paths.concepts, paths.exhibitions):
            folder.mkdir(parents=True, exist_ok=True)

        (paths.concepts / "CON-dyn0001.md").write_text(
            """---
id: CON-dyn0001
type: concept
name: Dynamics Concept
domain: Test
confidence_score: 0.8
---

# Dynamics Concept

Residual blocks can be interpreted through dynamical systems.
""",
            encoding="utf-8",
        )
        (paths.concepts / "CON-cifar001.md").write_text(
            """---
id: CON-cifar001
type: concept
name: CIFAR Concept
domain: Test
confidence_score: 0.8
---

# CIFAR Concept

CIFAR stacking rules and classification tables.
""",
            encoding="utf-8",
        )
        previous = """---
id: EXH-target01
type: exhibition
core_concepts:
  - "[[03_Concepts/CON-dyn0001]]"
  - "[[03_Concepts/CON-cifar001]]"
---

# Exhibition

Baseline residual network summary.
"""
        updated = previous + """
## Dynamics Insight

The residual block can be read as a forward Euler step in a Neural ODE lens.
"""
        (paths.exhibitions / "EXH-target01.md").write_text(updated, encoding="utf-8")

        client = FakeTargetedConceptClient()
        result = sync.propagate_upstream_from_exhibition(
            paths,
            client,
            exh_id="EXH-target01",
            previous_exh_content=previous,
            propagate_sources=False,
        )

        assert result.errors == []
        assert result.target_concepts == ["CON-dyn0001"]
        assert result.concepts_updated == ["CON-dyn0001"]
        assert result.llm_calls == 1
        assert client.calls == 1
        assert "CIFAR Concept" in (paths.concepts / "CON-cifar001.md").read_text(encoding="utf-8")


class FakeBatchConceptClient:
    def __init__(self) -> None:
        self.calls = 0
        self.json_modes: list[bool] = []

    def chat(self, *_args, **kwargs) -> str:
        self.calls += 1
        self.json_modes.append(bool(kwargs.get("json_mode")))
        return json.dumps({
            "concepts": [
                {
                    "id": "CON-dyn0004",
                    "changed": True,
                    "markdown": """---
id: CON-dyn0004
type: concept
name: Dynamics Concept
domain: Test
confidence_score: 0.9
---

# Dynamics Concept

Forward Euler and Neural ODE lens added.
""",
                },
                {
                    "id": "CON-euler04",
                    "changed": True,
                    "markdown": """---
id: CON-euler04
type: concept
name: Euler Concept
domain: Test
confidence_score: 0.9
---

# Euler Concept

Residual updates are interpreted as explicit Euler steps.
""",
                },
            ]
        })


def test_backprop_batches_multiple_target_concept_updates() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = cfg.WikiPaths(Path(tmp))
        for folder in (paths.contexts, paths.atoms, paths.concepts, paths.exhibitions):
            folder.mkdir(parents=True, exist_ok=True)

        concepts = {
            "CON-dyn0004": "Residual dynamical systems interpretation.",
            "CON-euler04": "Explicit Euler step interpretation.",
            "CON-res0004": "Residual updates bookkeeping without a Neural ODE claim.",
            "CON-cifar004": "CIFAR classification tables.",
        }
        for con_id, body in concepts.items():
            (paths.concepts / f"{con_id}.md").write_text(
                f"""---
id: {con_id}
type: concept
name: Test Concept
domain: Test
confidence_score: 0.8
---

# Test Concept

{body}
""",
                encoding="utf-8",
            )

        previous = """---
id: EXH-batch001
type: exhibition
core_concepts:
  - "[[03_Concepts/CON-dyn0004]]"
  - "[[03_Concepts/CON-euler04]]"
  - "[[03_Concepts/CON-res0004]]"
  - "[[03_Concepts/CON-cifar004]]"
---

# Exhibition

Baseline residual network summary.
"""
        updated = previous + """
## Dynamics Insight

Neural ODE dynamics read residual updates as explicit forward Euler steps.
"""
        (paths.exhibitions / "EXH-batch001.md").write_text(updated, encoding="utf-8")

        client = FakeBatchConceptClient()
        result = sync.propagate_upstream_from_exhibition(
            paths,
            client,
            exh_id="EXH-batch001",
            previous_exh_content=previous,
            propagate_sources=False,
        )

        assert result.errors == []
        assert set(result.target_concepts) == {"CON-dyn0004", "CON-euler04", "CON-res0004"}
        assert set(result.concepts_updated) == {"CON-dyn0004", "CON-euler04"}
        assert result.llm_calls == 1
        assert client.calls == 1
        assert client.json_modes == [True]
        assert "Forward Euler" in (paths.concepts / "CON-dyn0004.md").read_text(encoding="utf-8")
        assert "explicit Euler" in (paths.concepts / "CON-euler04.md").read_text(encoding="utf-8")
        assert "without a Neural ODE claim" in (paths.concepts / "CON-res0004.md").read_text(encoding="utf-8")
        assert "CIFAR classification" in (paths.concepts / "CON-cifar004.md").read_text(encoding="utf-8")


def test_mcp_update_node_identical_exhibition_is_noop(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        paths = cfg.WikiPaths(Path(tmp))
        paths.exhibitions.mkdir(parents=True, exist_ok=True)
        config_dir = paths.root / ".curator"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yml").write_text("llm:\n  provider: ollama\n", encoding="utf-8")
        content = """---
id: EXH-noop001
type: exhibition
core_concepts: []
---

# No-op Exhibition
"""
        (paths.exhibitions / "EXH-noop001.md").write_text(content, encoding="utf-8")
        monkeypatch.setenv("VAULT_ROOT", str(paths.root))
        monkeypatch.setenv("CURATOR_DISABLE_INGEST_WORKER", "1")

        server = mcp_server.build_server()
        tool = server._tool_manager._tools["curator_update_node"].fn
        result = tool(node_id="EXH-noop001", new_content=content, workspace_path="")

        assert result["updated"] is False
        assert result["noop"] is True
        assert result["propagation"]["llm_calls"] == 0
        assert result["routing_tables_rebuilt"] is False
