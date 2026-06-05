"""v0.2.1 spec tests: dag_edges table and DAG traversal (spec 04, 08, 09).

Tests cover:
- dag_edges table is created by db.init_db()
- db.insert_dag_edge() inserts rows and is idempotent (INSERT OR IGNORE)
- db.get_dag_edges_for_source() returns correct edges
- downstream traversal via _expand_downstream_via_sql() (spec 08 section 9.2)

These are TDD spec tests. They depend on db.py additions and ingest_orchestrator.py.
Tests that require functions not yet implemented skip gracefully.
"""
import tempfile
import unittest
from pathlib import Path

from curator import config as cfg
from curator import db

# ---------------------------------------------------------------------------
# Graceful import for v0.2.1-only db helpers and sync helpers
# ---------------------------------------------------------------------------
try:
    _insert_edge = db.insert_dag_edge
    _get_edges = db.get_dag_edges_for_source
    DAG_EDGE_HELPERS_AVAILABLE = True
except AttributeError:
    DAG_EDGE_HELPERS_AVAILABLE = False

try:
    from curator.ingest_orchestrator import _expand_downstream_via_sql
    EXPAND_AVAILABLE = True
except ImportError:
    EXPAND_AVAILABLE = False


# ---------------------------------------------------------------------------
# Helper: insert a minimal sources row and return its INTEGER id
# ---------------------------------------------------------------------------

def _register_source(db_path: Path, slug: str) -> int:
    with db.connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (f"04_Resources/{slug}.md", "abc123abc123abc1", "md", 0),
        )
    return cur.lastrowid  # type: ignore[return-value]


def _has_dag_edges_table(db_path: Path) -> bool:
    with db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='dag_edges'"
        ).fetchone()
        return row is not None


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestDagEdgesTableExists(unittest.TestCase):
    """db.init_db() must create the dag_edges table."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        db.init_db(self.paths.state_db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_dag_edges_table_created(self) -> None:
        self.assertTrue(
            _has_dag_edges_table(self.paths.state_db),
            "dag_edges table must be created by db.init_db()",
        )

    def test_dag_edges_has_required_columns(self) -> None:
        with db.connect(self.paths.state_db) as conn:
            info = conn.execute("PRAGMA table_info(dag_edges)").fetchall()
        col_names = {row["name"] for row in info}
        required = {"id", "from_id", "to_id", "edge_type", "source_id", "created_at"}
        missing = required - col_names
        self.assertEqual(missing, set(), f"Missing columns: {missing}")

    def test_idx_dag_edges_from_exists(self) -> None:
        with db.connect(self.paths.state_db) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_dag_edges_from'"
            ).fetchone()
        self.assertIsNotNone(row, "Index idx_dag_edges_from must exist")

    def test_idx_dag_edges_to_exists(self) -> None:
        with db.connect(self.paths.state_db) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_dag_edges_to'"
            ).fetchone()
        self.assertIsNotNone(row, "Index idx_dag_edges_to must exist")


# ---------------------------------------------------------------------------
# insert_dag_edge and get_dag_edges_for_source
# ---------------------------------------------------------------------------

@unittest.skipUnless(DAG_EDGE_HELPERS_AVAILABLE, "db.insert_dag_edge not yet implemented")
class TestInsertDagEdge(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        db.init_db(self.paths.state_db)
        self._source_id = _register_source(self.paths.state_db, "ctx-source-01")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_insert_edge_is_retrievable(self) -> None:
        _insert_edge(
            str(self.paths.state_db),
            from_id="CTX-ctx00001",
            to_id="ATM-atm00001",
            edge_type="extracted_from",
            source_id=self._source_id,
        )
        edges = _get_edges(str(self.paths.state_db), self._source_id)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["from_id"], "CTX-ctx00001")
        self.assertEqual(edges[0]["to_id"], "ATM-atm00001")
        self.assertEqual(edges[0]["edge_type"], "extracted_from")

    def test_duplicate_insert_is_idempotent(self) -> None:
        for _ in range(3):
            _insert_edge(
                str(self.paths.state_db),
                from_id="ATM-atm00001",
                to_id="CON-con00001",
                edge_type="clustered_to",
                source_id=self._source_id,
            )
        edges = _get_edges(str(self.paths.state_db), self._source_id)
        atm_to_con = [e for e in edges if e["from_id"] == "ATM-atm00001"]
        self.assertEqual(len(atm_to_con), 1, "INSERT OR IGNORE: must have exactly 1 row")

    def test_multiple_edges_same_source(self) -> None:
        for atom_n in range(5):
            _insert_edge(
                str(self.paths.state_db),
                from_id="CTX-ctx00001",
                to_id=f"ATM-atm0000{atom_n}",
                edge_type="extracted_from",
                source_id=self._source_id,
            )
        edges = _get_edges(str(self.paths.state_db), self._source_id)
        self.assertEqual(len(edges), 5)

    def test_edge_types_are_stored_correctly(self) -> None:
        edge_types = {"extracted_from", "clustered_to", "synthesized_to"}
        pairs = [
            ("CTX-c", "ATM-a", "extracted_from"),
            ("ATM-a", "CON-c", "clustered_to"),
            ("CON-c", "SYN-e", "synthesized_to"),
        ]
        for from_id, to_id, etype in pairs:
            _insert_edge(
                str(self.paths.state_db),
                from_id=from_id,
                to_id=to_id,
                edge_type=etype,
                source_id=self._source_id,
            )
        edges = _get_edges(str(self.paths.state_db), self._source_id)
        retrieved_types = {e["edge_type"] for e in edges}
        self.assertEqual(retrieved_types, edge_types)

    def test_null_source_id_is_accepted(self) -> None:
        # synthesized_to (SYN from wiki build) may have no source_id
        _insert_edge(
            str(self.paths.state_db),
            from_id="CON-con00001",
            to_id="SYN-syn00001",
            edge_type="synthesized_to",
            source_id=None,
        )
        with db.connect(self.paths.state_db) as conn:
            row = conn.execute(
                "SELECT * FROM dag_edges WHERE from_id='CON-con00001'"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertIsNone(row["source_id"])


# ---------------------------------------------------------------------------
# _expand_downstream_via_sql
# ---------------------------------------------------------------------------

@unittest.skipUnless(
    DAG_EDGE_HELPERS_AVAILABLE and EXPAND_AVAILABLE,
    "db helpers or ingest_orchestrator not yet implemented",
)
class TestExpandDownstreamViaSql(unittest.TestCase):
    """Downstream traversal follows edges transitively."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        db.init_db(self.paths.state_db)
        self._source_id = _register_source(self.paths.state_db, "ctx-source-01")
        self._build_graph()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _build_graph(self) -> None:
        # Graph: CTX-c -> ATM-a1 -> CON-c1 -> SYN-e1
        #        CTX-c → ATM-a2 → CON-c1
        edges = [
            ("CTX-c", "ATM-a1", "extracted_from"),
            ("CTX-c", "ATM-a2", "extracted_from"),
            ("ATM-a1", "CON-c1", "clustered_to"),
            ("ATM-a2", "CON-c1", "clustered_to"),
            ("CON-c1", "SYN-e1", "synthesized_to"),
        ]
        for from_id, to_id, etype in edges:
            _insert_edge(
                str(self.paths.state_db),
                from_id=from_id,
                to_id=to_id,
                edge_type=etype,
                source_id=self._source_id,
            )

    def test_atom_change_propagates_to_concept_and_synthesis(self) -> None:
        affected = _expand_downstream_via_sql(self.paths, ["ATM-a1"])
        self.assertIn("ATM-a1", affected)
        self.assertIn("CON-c1", affected)
        self.assertIn("SYN-e1", affected)

    def test_unrelated_node_not_included(self) -> None:
        affected = _expand_downstream_via_sql(self.paths, ["ATM-a1"])
        self.assertNotIn("ATM-a2", affected)

    def test_concept_change_propagates_to_synthesis_only(self) -> None:
        affected = _expand_downstream_via_sql(self.paths, ["CON-c1"])
        self.assertIn("CON-c1", affected)
        self.assertIn("SYN-e1", affected)
        self.assertNotIn("ATM-a1", affected)
        self.assertNotIn("ATM-a2", affected)

    def test_empty_input_returns_empty_set(self) -> None:
        affected = _expand_downstream_via_sql(self.paths, [])
        self.assertEqual(affected, set())

    def test_node_with_no_edges_returns_itself_only(self) -> None:
        affected = _expand_downstream_via_sql(self.paths, ["SYN-e1"])
        self.assertEqual(affected, {"SYN-e1"})


if __name__ == "__main__":
    unittest.main()
