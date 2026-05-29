import tempfile
from pathlib import Path

from curator import config as cfg
from curator import sync


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
            paths, FakeBackpropClient(), exh_id="EXH-test0001"
        )

        assert result.errors == []
        assert result.concepts_updated == ["CON-test0001"]
        assert result.atoms_updated == ["ATM-test0001"]
        assert result.contexts_updated == ["CTX-test0001"]
        assert "Updated Concept" in (paths.concepts / "CON-test0001.md").read_text(encoding="utf-8")
        assert "Updated Atom" in (paths.atoms / "ATM-test0001.md").read_text(encoding="utf-8")
        assert "Updated Context" in (paths.contexts / "CTX-test0001.md").read_text(encoding="utf-8")
