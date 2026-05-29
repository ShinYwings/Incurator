import tempfile
import unittest
from pathlib import Path

from curator import config as cfg
from curator import db, ingest_llm


class EmbeddingClusteringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        self.paths.atoms.mkdir(parents=True, exist_ok=True)
        db.init_db(self.paths.state_db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_atom(self, atom_id: str, name: str, claim: str) -> None:
        (self.paths.atoms / f"{atom_id}.md").write_text(
            f"""---
id: {atom_id}
type: atom
parent_source: 01_Contexts/CTX-test0001
source_path: 02_Wiki/source.md
claim_type: fact
confidence_score: 0.8
contradicts: []
is_verified_by_human: false
is_flagged_for_agent: false
last_updated: 2026-05-29T00:00:00Z
---

# {name}

## Definition / Claim

{claim}

## Context

Test context.

## Constraints

- None.

## Relations

[[01_Contexts/CTX-test0001]]
""",
            encoding="utf-8",
        )

    def test_cluster_atoms_by_embedding_avoids_llm_cluster_planning(self) -> None:
        self._write_atom("ATM-a0000001", "Alpha Attention", "Attention uses query key matching.")
        self._write_atom("ATM-a0000002", "Attention Scores", "Attention scores compare queries and keys.")
        self._write_atom("ATM-b0000001", "Archive Policy", "Archives preserve inactive project files.")

        class FakeEmbeddingClient:
            def embed_texts(self, texts):  # noqa: ANN001
                return [
                    [1.0, 0.0],
                    [0.99, 0.01],
                    [0.0, 1.0],
                ][: len(texts)]

            def chat(self, *args, **kwargs):  # noqa: ANN002, ANN003
                raise AssertionError("embedding clustering must not call chat")

        clusters = ingest_llm.cluster_atoms_by_embedding(
            self.paths,
            ["ATM-a0000001", "ATM-a0000002", "ATM-b0000001"],
            FakeEmbeddingClient(),
            eps=0.05,
        )

        self.assertIsNotNone(clusters)
        assert clusters is not None
        cluster_sets = {frozenset(cluster) for cluster in clusters}
        self.assertIn(frozenset({"ATM-a0000001", "ATM-a0000002"}), cluster_sets)
        self.assertIn(frozenset({"ATM-b0000001"}), cluster_sets)


if __name__ == "__main__":
    unittest.main()
