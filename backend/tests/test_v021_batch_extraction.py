"""v0.2.1 spec tests: Section-Aware Batch Extraction (spec 08).

Tests cover:
- _split_into_batches(): section-marker-aware document chunking
- content_hash generation in atom page frontmatter
- _parse_batch_atoms_json(): tolerant JSON extraction from LLM output
- _build_atom_page_from_data(): template-based atom page construction

These are TDD spec tests. They will pass once ingest_orchestrator.py is implemented.
Functions are imported with graceful skip if the module does not yet exist.
"""
import hashlib
import json
import re
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Graceful import: skip module-level tests if ingest_orchestrator is not yet
# present. This lets the rest of the suite run cleanly during development.
# ---------------------------------------------------------------------------
try:
    from curator.ingest_orchestrator import (
        _build_atom_page_from_data,
        _parse_batch_atoms_json,
        _split_into_batches,
    )
    ORCHESTRATOR_AVAILABLE = True
except ImportError:
    ORCHESTRATOR_AVAILABLE = False


# ---------------------------------------------------------------------------
# Pure-logic reference implementations (used to verify expected behaviour
# independently of the production module during early development)
# ---------------------------------------------------------------------------

def _ref_split_into_batches(body: str, max_chars: int) -> list[str]:
    """Reference implementation matching spec 08 section 2.1."""
    if len(body) <= max_chars:
        return [body]
    parts = re.split(r'(?=<!-- section:)', body)
    batches: list[str] = []
    current: list[str] = []
    current_len = 0
    for part in parts:
        if current_len + len(part) > max_chars and current:
            batches.append("".join(current))
            current, current_len = [part], len(part)
        else:
            current.append(part)
            current_len += len(part)
    if current:
        batches.append("".join(current))
    return batches


def _ref_content_hash(body_text: str) -> str:
    """SHA-256 of body text, first 16 hex chars (spec 08 section 2.1)."""
    return hashlib.sha256(body_text.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# _split_into_batches
# ---------------------------------------------------------------------------

class TestSplitIntoBatches(unittest.TestCase):
    """Tests for the section-aware batch splitter."""

    def _split(self, body: str, max_chars: int) -> list[str]:
        if ORCHESTRATOR_AVAILABLE:
            return _split_into_batches(body, max_chars)
        return _ref_split_into_batches(body, max_chars)

    def test_short_document_returns_single_chunk(self) -> None:
        body = "<!-- section:s1 page:1 -->\n## Introduction\n\nShort text."
        result = self._split(body, max_chars=10_000)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], body)

    def test_long_document_split_at_section_boundaries(self) -> None:
        section_a = "<!-- section:s1 page:1 -->\n## Intro\n\n" + "A" * 300
        section_b = "<!-- section:s2 page:5 -->\n## Method\n\n" + "B" * 300
        section_c = "<!-- section:s3 page:9 -->\n## Results\n\n" + "C" * 300
        body = section_a + section_b + section_c
        # max_chars forces split between sections
        result = self._split(body, max_chars=400)
        # Each section is ~340 chars; must split into at least 2 chunks
        self.assertGreater(len(result), 1)
        # No chunk exceeds max_chars (except a single oversized section alone)
        for chunk in result:
            # A single section can exceed max_chars only if it is alone in its chunk
            section_count = chunk.count("<!-- section:")
            if section_count > 1:
                self.assertLessEqual(len(chunk), 400)

    def test_split_preserves_all_content(self) -> None:
        section_a = "<!-- section:s1 page:1 -->\n## Intro\n\n" + "X" * 200
        section_b = "<!-- section:s2 page:3 -->\n## Body\n\n" + "Y" * 200
        body = section_a + section_b
        result = self._split(body, max_chars=250)
        self.assertEqual("".join(result), body)

    def test_no_section_markers_returns_single_chunk_regardless_of_size(self) -> None:
        body = "No section markers here. " * 500  # ~12 500 chars
        result = self._split(body, max_chars=100)
        # No markers → cannot split at boundaries → single chunk
        self.assertEqual(len(result), 1)

    def test_empty_body_returns_single_empty_chunk(self) -> None:
        result = self._split("", max_chars=1000)
        self.assertEqual(result, [""])


# ---------------------------------------------------------------------------
# content_hash
# ---------------------------------------------------------------------------

class TestContentHash(unittest.TestCase):
    """content_hash is a 16-char hex prefix of SHA-256 of the body text."""

    def test_hash_length_is_16(self) -> None:
        h = _ref_content_hash("some body text")
        self.assertEqual(len(h), 16)

    def test_hash_is_hexadecimal(self) -> None:
        h = _ref_content_hash("some body text")
        self.assertTrue(all(c in "0123456789abcdef" for c in h))

    def test_same_text_same_hash(self) -> None:
        text = "# Atom\n\n## Definition\n\nSome claim here.\n"
        self.assertEqual(_ref_content_hash(text), _ref_content_hash(text))

    def test_different_text_different_hash(self) -> None:
        self.assertNotEqual(
            _ref_content_hash("claim A"),
            _ref_content_hash("claim B"),
        )

    @unittest.skipUnless(ORCHESTRATOR_AVAILABLE, "ingest_orchestrator not yet implemented")
    def test_atom_page_has_content_hash_field(self) -> None:
        atom_data = {
            "name": "Self-Attention",
            "claim_type": "fact",
            "one_liner": "Attention weights are computed as softmax(QK^T/sqrt(d_k))V.",
            "source_section_id": "s2",
            "source_section_title": "Method",
            "source_page": 4,
            "confidence": 0.95,
        }
        page = _build_atom_page_from_data(
            atom_id="ATM-abc12345",
            data=atom_data,
            context_id="CTX-xyz",
            relpath="04_Resources/paper.md",
            today="2026-05-29",
        )
        self.assertIn("content_hash:", page)
        # Extract the hash value from frontmatter
        match = re.search(r"content_hash:\s*([0-9a-f]+)", page)
        self.assertIsNotNone(match)
        self.assertEqual(len(match.group(1)), 16)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# _parse_batch_atoms_json
# ---------------------------------------------------------------------------

class TestParseBatchAtomsJson(unittest.TestCase):
    """_parse_batch_atoms_json must tolerate markdown code fences and bad JSON."""

    def _parse(self, raw: str) -> list[dict]:
        if ORCHESTRATOR_AVAILABLE:
            return _parse_batch_atoms_json(raw)
        # Reference: strip ```json ... ``` then parse
        text = re.sub(r"```json\s*", "", raw)
        text = re.sub(r"```\s*", "", text).strip()
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []

    def test_plain_json_array_parses(self) -> None:
        raw = '[{"name": "X", "one_liner": "Y"}]'
        result = self._parse(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "X")

    def test_markdown_fenced_json_parses(self) -> None:
        raw = '```json\n[{"name": "A", "one_liner": "B"}]\n```'
        result = self._parse(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "A")

    def test_invalid_json_raises_error(self) -> None:
        if not ORCHESTRATOR_AVAILABLE:
            self.assertEqual(self._parse("not valid json at all {{{"), [])
            return
        from curator.llm import LLMError
        with self.assertRaises(LLMError):
            self._parse("not valid json at all {{{")

    def test_json_object_not_array_raises_error(self) -> None:
        if not ORCHESTRATOR_AVAILABLE:
            self.assertEqual(self._parse('{"name": "X"}'), [])
            return
        from curator.llm import LLMError
        with self.assertRaises(LLMError):
            self._parse('{"name": "X"}')

    def test_empty_array_parses(self) -> None:
        result = self._parse("[]")
        self.assertEqual(result, [])

    def test_multiple_atoms_parse(self) -> None:
        atoms = [
            {"name": f"Atom {i}", "one_liner": f"Claim {i}"}
            for i in range(5)
        ]
        raw = json.dumps(atoms)
        result = self._parse(raw)
        self.assertEqual(len(result), 5)


# ---------------------------------------------------------------------------
# _build_atom_page_from_data
# ---------------------------------------------------------------------------

@unittest.skipUnless(ORCHESTRATOR_AVAILABLE, "ingest_orchestrator not yet implemented")
class TestBuildAtomPage(unittest.TestCase):
    """Template-based atom page generation (no LLM required)."""

    def _build(self, overrides: dict | None = None) -> str:
        base_data: dict = {
            "name": "Test Atom",
            "claim_type": "fact",
            "one_liner": "A single verifiable fact.",
            "source_section_id": "s1",
            "source_section_title": "Introduction",
            "source_page": 1,
            "confidence": 0.9,
        }
        if overrides:
            base_data.update(overrides)
        return _build_atom_page_from_data(
            atom_id="ATM-test0001",
            data=base_data,
            context_id="CTX-ctx00001",
            relpath="04_Resources/paper.md",
            today="2026-05-29",
        )

    def test_page_has_yaml_frontmatter(self) -> None:
        page = self._build()
        self.assertTrue(page.startswith("---\n"))
        self.assertIn("\n---\n", page)

    def test_frontmatter_contains_required_fields(self) -> None:
        page = self._build()
        for field in ("id:", "type:", "content_hash:", "is_verified_by_human:",
                      "is_flagged_for_agent:", "last_updated:"):
            self.assertIn(field, page)

    def test_type_is_atom(self) -> None:
        page = self._build()
        self.assertIn("type: atom", page)

    def test_confidence_clamped_to_unit_interval(self) -> None:
        page_low = self._build({"confidence": -0.5})
        page_high = self._build({"confidence": 1.5})
        self.assertIn("confidence_score: 0.0", page_low)
        self.assertIn("confidence_score: 1.0", page_high)

    def test_missing_claim_type_defaults_to_fact(self) -> None:
        data = {
            "name": "No claim type",
            "one_liner": "A claim without type.",
        }
        page = _build_atom_page_from_data(
            atom_id="ATM-noct0001",
            data=data,
            context_id="CTX-ctx00001",
            relpath="04_Resources/paper.md",
            today="2026-05-29",
        )
        self.assertIn("claim_type: fact", page)


# ---------------------------------------------------------------------------
# run_l2_batch_extraction — integration with mocked LLM
# ---------------------------------------------------------------------------

@unittest.skipUnless(ORCHESTRATOR_AVAILABLE, "ingest_orchestrator not yet implemented")
class TestRunL2BatchExtraction(unittest.TestCase):
    """End-to-end integration tests for run_l2_batch_extraction with a mock client."""

    def setUp(self) -> None:
        import tempfile
        from curator import config as cfg, db
        from curator.ingest_orchestrator import run_l2_batch_extraction

        self.run_l2 = run_l2_batch_extraction
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        db.init_db(self.paths.state_db)
        self.staging = self.root / "staging"
        self.staging.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_ctx(self, context_id: str, body: str) -> Path:
        ctx_path = self.paths.contexts / f"{context_id}.md"
        ctx_path.parent.mkdir(parents=True, exist_ok=True)
        ctx_path.write_text(
            f"---\nid: {context_id}\ntype: context\n---\n\n{body}",
            encoding="utf-8",
        )
        return ctx_path

    def _write_ctx_with_frontmatter(self, context_id: str, body: str, extra: str) -> Path:
        ctx_path = self.paths.contexts / f"{context_id}.md"
        ctx_path.parent.mkdir(parents=True, exist_ok=True)
        ctx_path.write_text(
            f"---\nid: {context_id}\ntype: context\n{extra}---\n\n{body}",
            encoding="utf-8",
        )
        return ctx_path

    def _make_client(self, atoms_json: str):
        from unittest.mock import Mock
        client = Mock()
        client.chat = Mock(return_value=atoms_json)
        return client

    def test_atoms_created_in_staging_from_llm_response(self) -> None:
        atoms = [
            {"name": "Self-Attention", "claim_type": "fact",
             "one_liner": "Attention is all you need.", "source_section_id": "s1",
             "source_section_title": "Method", "source_page": 3, "confidence": 0.9},
        ]
        ctx = self._write_ctx("CTX-test0001", "<!-- section:s1 page:3 -->\n## Method\n\nBody text.")
        client = self._make_client(json.dumps(atoms))

        results = self.run_l2(
            self.paths, client, ctx, "CTX-test0001",
            "04_Resources/paper.pdf", "2026-05-29", self.staging,
        )

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].staged_path.exists())
        content = results[0].staged_path.read_text(encoding="utf-8")
        self.assertIn("Self-Attention", content)
        self.assertIn("type: atom", content)

    def test_empty_llm_response_returns_no_atoms(self) -> None:
        ctx = self._write_ctx("CTX-test0002", "## Short doc\n\nFew words.")
        client = self._make_client("[]")

        results = self.run_l2(
            self.paths, client, ctx, "CTX-test0002",
            "04_Resources/paper.pdf", "2026-05-29", self.staging,
        )

        self.assertEqual(results, [])

    def test_multiple_atoms_all_staged(self) -> None:
        atoms = [
            {"name": f"Atom {i}", "claim_type": "fact",
             "one_liner": f"Claim {i}.", "source_section_id": f"s{i}",
             "source_section_title": f"Section {i}", "source_page": i, "confidence": 0.8}
            for i in range(3)
        ]
        ctx = self._write_ctx("CTX-test0003", "<!-- section:s1 page:1 -->\nContent.")
        client = self._make_client(json.dumps(atoms))

        results = self.run_l2(
            self.paths, client, ctx, "CTX-test0003",
            "04_Resources/paper.pdf", "2026-05-29", self.staging,
        )

        self.assertEqual(len(results), 3)
        atom_ids = {r.atom_id for r in results}
        self.assertEqual(len(atom_ids), 3, "All atom IDs must be unique")
        for r in results:
            self.assertTrue(r.staged_path.exists())

    def test_atom_without_name_skipped(self) -> None:
        atoms = [
            {"claim_type": "fact", "one_liner": "No name provided."},
            {"name": "Valid Atom", "claim_type": "fact", "one_liner": "Has name."},
        ]
        ctx = self._write_ctx("CTX-test0004", "Some content.")
        client = self._make_client(json.dumps(atoms))

        results = self.run_l2(
            self.paths, client, ctx, "CTX-test0004",
            "04_Resources/paper.pdf", "2026-05-29", self.staging,
        )

        self.assertEqual(len(results), 1)
        self.assertIn("Valid Atom", results[0].staged_path.read_text(encoding="utf-8"))

    def test_large_doc_split_into_multiple_llm_calls(self) -> None:
        # Build a body with two large sections that exceed MAX_BATCH_CHARS
        from curator.ingest_orchestrator import MAX_BATCH_CHARS
        section_body = "X" * (MAX_BATCH_CHARS // 2 + 100)
        body = (
            f"<!-- section:s1 page:1 -->\n## Part 1\n\n{section_body}"
            f"<!-- section:s2 page:10 -->\n## Part 2\n\n{section_body}"
        )
        ctx = self._write_ctx("CTX-test0005", body)
        call_count = []

        def counting_chat(messages, **kwargs):
            call_count.append(1)
            return '[{"name": "Atom A", "claim_type": "fact", "one_liner": "Claim.", "source_section_id": "s1", "source_section_title": "S1", "source_page": 1, "confidence": 0.8}]'

        from unittest.mock import Mock
        client = Mock()
        client.chat = counting_chat

        results = self.run_l2(
            self.paths, client, ctx, "CTX-test0005",
            "04_Resources/big.pdf", "2026-05-29", self.staging,
        )

        self.assertGreater(len(call_count), 1, "Large doc must trigger multiple LLM calls")
        self.assertEqual(len(results), len(call_count))

    def test_multiple_batches_use_cloned_clients_when_available(self) -> None:
        from unittest.mock import patch

        class CloneableClient:
            def __init__(self, state: dict | None = None) -> None:
                self.state = state if state is not None else {"clones": 0, "calls": 0}

            def clone(self):
                self.state["clones"] += 1
                return CloneableClient(self.state)

            def chat(self, messages, **kwargs):  # noqa: ARG002
                self.state["calls"] += 1
                idx = self.state["calls"]
                return json.dumps([
                    {
                        "name": f"Parallel Atom {idx}",
                        "claim_type": "fact",
                        "one_liner": f"Claim {idx}.",
                        "source_section_id": f"s{idx}",
                    }
                ])

        body = "\n\n".join(
            f"<!-- section:s{i} page:1 -->\n## Section {i}\n\n" + ("X" * 140)
            for i in range(1, 4)
        )
        ctx = self._write_ctx("CTX-test0006", body)
        client = CloneableClient()

        with patch("curator.ingest_orchestrator.MAX_BATCH_CHARS", 180):
            results = self.run_l2(
                self.paths, client, ctx, "CTX-test0006",
                "04_Resources/parallel.pdf", "2026-05-29", self.staging,
            )

        self.assertGreater(len(results), 1)
        self.assertGreater(client.state["clones"], 1)
        self.assertEqual(client.state["calls"], len(results))

    def test_batch_size_respects_client_optimal_chunk_chars(self) -> None:
        class SmallChunkClient:
            optimal_chunk_chars = 180

            def __init__(self) -> None:
                self.calls = 0

            def chat(self, messages, **kwargs):  # noqa: ARG002
                self.calls += 1
                return json.dumps([
                    {
                        "name": f"Small Chunk Atom {self.calls}",
                        "claim_type": "fact",
                        "one_liner": f"Claim {self.calls}.",
                        "source_section_id": f"s{self.calls}",
                    }
                ])

        body = "\n\n".join(
            f"<!-- section:s{i} page:1 -->\n## Section {i}\n\n" + ("X" * 140)
            for i in range(1, 4)
        )
        ctx = self._write_ctx("CTX-test0007", body)
        client = SmallChunkClient()

        results = self.run_l2(
            self.paths, client, ctx, "CTX-test0007",
            "04_Resources/small-chunks.pdf", "2026-05-29", self.staging,
        )

        self.assertGreater(client.calls, 1)
        self.assertEqual(len(results), client.calls)

    def test_llm_failure_falls_back_to_l1_atom_candidates(self) -> None:
        from curator.llm import LLMError

        class FailingClient:
            optimal_chunk_chars = 50000

            def chat(self, messages, **kwargs):  # noqa: ARG002
                raise LLMError("provider unavailable")

        body = """## Summary

Structural L1 context.

## 1. Key Claims

- `s1` p.3 **Method**: Residual blocks add an identity shortcut.

## Source Guide

### Section Previews
- `s1` p.3 — **Method**: Residual blocks add an identity shortcut.

## 2. Atom Candidates

- [fact] Method: Extract the atomic claims, methods, entities, equations, and constraints from section 'Method' starting on page 3. Preview: Residual blocks add an identity shortcut.

## Source Sections

<!-- section:s1 page:3 -->
## Method

Residual blocks add an identity shortcut.
"""
        ctx = self._write_ctx("CTX-test0008", body)

        results = self.run_l2(
            self.paths, FailingClient(), ctx, "CTX-test0008",
            "04_Resources/paper.pdf", "2026-05-29", self.staging,
        )

        self.assertEqual(len(results), 1)
        content = results[0].staged_path.read_text(encoding="utf-8")
        self.assertIn("Method", content)
        self.assertIn("confidence_score: 0.3", content)
        self.assertIn("source_section_id: s1", content)
        self.assertIn("source_page: 3", content)

    def test_on_demand_l1_hydrates_original_source_for_l2(self) -> None:
        source_relpath = "03_Notes/large-original.md"
        source = self.root / source_relpath
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            "# Large Original\n\n"
            "## Method\n\n"
            "DEEP_ORIGINAL_EVIDENCE appears only in the source file.\n",
            encoding="utf-8",
        )
        body = """## Summary

Compact L1.

## Source Sections

<!-- section:s1 page:1 -->
## Large Original

Raw source text is not duplicated in this L1 page because the source is large.
"""
        ctx = self._write_ctx_with_frontmatter(
            "CTX-ondemand",
            body,
            "source_text_policy: on_demand\nsource_sections_inline: false\n",
        )

        class RecordingClient:
            optimal_chunk_chars = 50000

            def __init__(self) -> None:
                self.prompt = ""

            def chat(self, messages, **kwargs):  # noqa: ARG002
                self.prompt = messages[-1].content
                return json.dumps([
                    {
                        "name": "Hydrated Evidence",
                        "claim_type": "fact",
                        "one_liner": "The source contains deep original evidence.",
                        "source_section_id": "s2",
                        "source_section_title": "Method",
                        "source_page": 1,
                        "confidence": 0.8,
                    }
                ])

        client = RecordingClient()
        results = self.run_l2(
            self.paths, client, ctx, "CTX-ondemand",
            source_relpath, "2026-05-29", self.staging,
        )

        self.assertEqual(len(results), 1)
        self.assertIn("DEEP_ORIGINAL_EVIDENCE", client.prompt)


if __name__ == "__main__":
    unittest.main()
