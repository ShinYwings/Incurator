import json
import tempfile
import unittest
from pathlib import Path

from curator import config as cfg
from curator import __version__
from curator import db
from curator import runtime_state


def _string_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _string_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _string_values(child)


def _absolute_strings(payload: dict) -> list[str]:
    return [value for value in _string_values(payload) if value.startswith("/")]


class TestRuntimeStateSnapshots(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = cfg.WikiPaths(Path(self.tmp.name))
        db.init_db(self.paths.state_db)
        self.paths.contexts.mkdir(parents=True, exist_ok=True)
        self.paths.atoms.mkdir(parents=True, exist_ok=True)
        (self.paths.contexts / "CTX-test.md").write_text("# Context\n", encoding="utf-8")
        with db.connect(self.paths.state_db) as conn:
            conn.execute(
                """
                INSERT INTO sources
                (relpath, content_hash, file_type, bytes, added_at, status,
                 context_id, l1_status, l2_status, l3_status, l4_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "04_Resources/paper.pdf",
                    "abc",
                    "pdf",
                    123,
                    "2026-06-02T00:00:00Z",
                    "curated",
                    "CTX-test",
                    "done",
                    "done",
                    "pending",
                    "pending",
                ),
            )
            source_id = conn.execute("SELECT id FROM sources").fetchone()["id"]
            conn.execute(
                """
                INSERT INTO ingest_jobs
                (source_id, job_type, trigger, state, phase, progress,
                 progress_current, progress_total, source_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    "l2_atoms",
                    "wiki_add",
                    "queued",
                    "queued",
                    0.0,
                    0,
                    10,
                    "paper.pdf",
                    "2026-06-02T00:00:00Z",
                ),
            )
            conn.execute(
                """
                INSERT INTO ingest_jobs
                (source_id, job_type, trigger, state, phase, progress,
                 progress_current, progress_total, source_name, created_at, finished_at, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    "l2_atoms",
                    "wiki_add",
                    "failed",
                    "failed",
                    0.0,
                    0,
                    10,
                    "failed.pdf",
                    "2026-06-02T00:00:00Z",
                    "2026-06-02T00:01:00Z",
                    "boom",
                ),
            )
            conn.execute(
                """
                INSERT INTO ingest_jobs
                (source_id, job_type, trigger, state, phase, progress,
                 progress_current, progress_total, source_name, created_at, finished_at, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    "l3_concepts",
                    "wiki_add",
                    "cancelled",
                    "cancelled",
                    0.0,
                    0,
                    10,
                    "cancelled.pdf",
                    "2026-06-02T00:00:00Z",
                    "2026-06-02T00:01:00Z",
                    "Cancelled by user",
                ),
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_write_runtime_snapshots(self) -> None:
        status = runtime_state.write_runtime_snapshots(self.paths, {"llm": {"primary": "codex-cli::gpt-5.5"}})

        runtime_dir = runtime_state.runtime_dir(self.paths)
        self.assertEqual(status["layer_counts"]["contexts"], 1)
        self.assertEqual(status["sources"]["total"], 1)
        self.assertEqual(status["jobs"]["queued"], 1)
        self.assertEqual(status["sources"]["l1_done"], 1)
        self.assertEqual(status["sources"]["l2_done"], 1)
        self.assertEqual(status["sources"]["l3_done"], 0)
        self.assertEqual(status["backend_version"], __version__)

        for name in ("status", "sources", "jobs"):
            path = runtime_dir / f"{name}.json"
            self.assertTrue(path.exists(), f"{name}.json was not written")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(payload["ok"])

        sources = json.loads((runtime_dir / "sources.json").read_text(encoding="utf-8"))
        self.assertEqual(sources["sources"][0]["relpath"], "04_Resources/paper.pdf")

        jobs = json.loads((runtime_dir / "jobs.json").read_text(encoding="utf-8"))
        self.assertEqual(jobs["queued"][0]["source_name"], "paper.pdf")
        self.assertEqual(jobs["failed"][0]["source_name"], "failed.pdf")
        self.assertEqual(jobs["cancelled"][0]["source_name"], "cancelled.pdf")

    def test_status_json_payload_shape(self) -> None:
        # `wiki status --json` emits exactly this consolidated payload, which the
        # plugin dashboard reads LIVE (instead of the on-disk snapshot file). The
        # three sub-objects must be present, JSON-serialisable, and carry the keys
        # the dashboard depends on.
        payload = {
            "status": runtime_state.build_status_snapshot(
                self.paths, {"llm": {"primary": "codex-cli::gpt-5.5"}}
            ),
            "sources": runtime_state.build_sources_snapshot(self.paths),
            "jobs": runtime_state.build_jobs_snapshot(self.paths),
        }
        reparsed = json.loads(json.dumps(payload, ensure_ascii=False))
        self.assertEqual(set(reparsed.keys()), {"status", "sources", "jobs"})
        self.assertIn("layer_counts", reparsed["status"])
        self.assertEqual(reparsed["status"]["llm"]["primary"], "codex-cli::gpt-5.5")
        self.assertIsInstance(reparsed["sources"].get("sources"), list)
        self.assertIn("queued", reparsed["jobs"])

    def test_status_snapshot_uses_search_contract_only(self) -> None:
        status = runtime_state.build_status_snapshot(self.paths, {"search": {}})
        forbidden_prefix = "q" + "md"

        self.assertEqual(status["search_engine"], "native")
        self.assertTrue(status["search_ready"])
        self.assertIn("search_version", status)
        self.assertFalse(
            [key for key in status if key.startswith(f"{forbidden_prefix}_")]
        )

    def test_status_snapshot_does_not_export_absolute_paths(self) -> None:
        from curator import device_registry

        registry_path = device_registry.registry_path(self.paths.root)
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(
            json.dumps(
                {
                    "local_device_id": "local",
                    "devices": {
                        "local": {
                            "name": "This Device",
                            "platform": {
                                "system": "Linux",
                                "python": "/machine/.venv/bin/python",
                            },
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        status = runtime_state.build_status_snapshot(
            self.paths,
            {
                "llm": {"primary": "codex-cli::gpt-5.5"},
                "search": {
                    "embedding": "llama-cpp::qwen3-embedding-0.6b",
                    "embedding_model_path": "/machine/cache/embed.gguf",
                    "reranker": "llama-cpp::qwen3-reranker-0.6b",
                    "reranker_model_path": "/machine/cache/rerank.gguf",
                    "query_expander_model_path": "/machine/cache/expand.gguf",
                    "embedding_gguf_file": "embed.gguf",
                    "reranker_gguf_file": "rerank.gguf",
                },
                "external": {
                    "roots": ["/machine/library"],
                    "zotero": {"enabled": True, "roots": ["/machine/Zotero"]},
                },
            },
        )

        self.assertEqual(status["vault_root"], "")
        self.assertEqual(status["collections"], ".curator/Collections")
        self.assertEqual(status["search"]["embedding_model_path"], "")
        self.assertEqual(status["search"]["reranker_model_path"], "")
        self.assertEqual(status["search"]["query_expander_model_path"], "")
        self.assertEqual(status["external"]["roots"], [])
        self.assertEqual(status["external"]["zotero"]["roots"], [])
        self.assertEqual(status["search_models"]["embed"]["path"], "")
        self.assertEqual(status["search_models"]["reranker"]["path"], "")
        self.assertEqual(status["search_models"]["cache_dir"], "")
        self.assertEqual(status["devices"][0]["platform"], {"system": "Linux"})
        self.assertEqual(_absolute_strings(status), [])

    def test_zotero_source_snapshot_uses_portable_source_path(self) -> None:
        with db.connect(self.paths.state_db) as conn:
            conn.execute("DELETE FROM sources")
            conn.execute(
                """
                INSERT INTO sources
                (relpath, content_hash, file_type, bytes, added_at, status,
                 external_ref, is_reference, logical_source_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "04_Resources/References/paper.md",
                    "zotero-hash",
                    "pdf",
                    123,
                    "2026-06-02T00:00:00Z",
                    "curated",
                    None,
                    1,
                    "zotero:ATTKEY",
                ),
            )

        sources = runtime_state.build_sources_snapshot(self.paths)

        self.assertEqual(sources["sources"][0]["relpath"], "04_Resources/References/paper.md")
        self.assertEqual(
            sources["sources"][0]["source_path"],
            "zotero://open-pdf/library/items/ATTKEY",
        )
        self.assertEqual(sources["sources"][0]["external_ref"], "")
        self.assertFalse(sources["sources"][0]["has_external_ref"])
        self.assertEqual(_absolute_strings(sources), [])

    def test_absolute_legacy_relpath_is_not_exported_to_source_snapshot(self) -> None:
        with db.connect(self.paths.state_db) as conn:
            conn.execute("DELETE FROM sources")
            conn.execute(
                """
                INSERT INTO sources
                (relpath, content_hash, file_type, bytes, added_at, status,
                 external_ref, is_reference, logical_source_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "/home/user/Documents/paper.pdf",
                    "external-hash",
                    "pdf",
                    123,
                    "2026-06-02T00:00:00Z",
                    "curated",
                    "@documents/paper.pdf",
                    1,
                    "ref-abc123",
                ),
            )

        sources = runtime_state.build_sources_snapshot(self.paths)

        self.assertEqual(sources["sources"][0]["relpath"], "")
        self.assertEqual(sources["sources"][0]["source_path"], "ref-abc123")
        self.assertEqual(sources["sources"][0]["external_ref"], "@documents/paper.pdf")
        self.assertTrue(sources["sources"][0]["has_external_ref"])
        self.assertEqual(_absolute_strings(sources), [])
