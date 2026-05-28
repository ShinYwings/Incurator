import hashlib
import re
import tempfile
import unittest
from pathlib import Path

from curator import config as cfg
from curator import db, ingest_llm, ingest_raw, lint, page_writer, prompts, sync


class IntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = cfg.WikiPaths(self.root)
        for raw_dir in self.paths.raw_dirs:
            raw_dir.mkdir(parents=True, exist_ok=True)
        for layer_dir in (
            self.paths.contexts,
            self.paths.atoms,
            self.paths.concepts,
            self.paths.exhibitions,
        ):
            layer_dir.mkdir(parents=True, exist_ok=True)
        db.init_db(self.paths.state_db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_atom_contract_rewrites_malformed_llm_output(self) -> None:
        candidate = ingest_llm.AtomCandidate(
            name="Local Affine Approximation",
            type="technique",
            one_liner="Local linearization of projection.",
        )
        malformed = """---
id: ATM-wrong
type: atom
parent_source: 01_Contexts/
source_path: ""
claim_type: fact
confidence_score: bad
contradicts: []
is_verified_by_human: false
is_flagged_for_agent: false
last_updated: old
---

# Local Affine Approximation

```yaml
---
id: ATM-wrong
type: atom
parent_source: "01_Contexts/"
source_path: ""
---
```

- **Relations**:
- [[01_Contexts/]]
- [[01_Contexts/CTX-typo1234]]
"""

        repaired = ingest_llm._enforce_atom_contract(
            malformed,
            atom_id="ATM-good1234",
            candidate=candidate,
            context_id="CTX-good1234",
            relpath="04_Resources/Zotero/paper.pdf",
            today="2026-05-04T00:00:00Z",
        )
        parsed = page_writer.parse_page(repaired)

        self.assertEqual(parsed.frontmatter["id"], "ATM-good1234")
        self.assertEqual(parsed.frontmatter["parent_source"], "01_Contexts/CTX-good1234")
        self.assertEqual(parsed.frontmatter["source_path"], "[[04_Resources/Zotero/paper.pdf]]")
        self.assertEqual(parsed.frontmatter["claim_type"], "technique")
        self.assertNotIn("[[01_Contexts/]]", parsed.body)
        self.assertNotIn("[[01_Contexts/CTX-typo1234]]", parsed.body)
        self.assertNotIn("source_path: \"\"", parsed.body)
        self.assertIn("[[01_Contexts/CTX-good1234]]", parsed.body)

    def test_atom_contract_extracts_tool_wrapper_frontmatter(self) -> None:
        candidate = ingest_llm.AtomCandidate(
            name="QMD",
            type="entity",
            one_liner="Query markup document backend.",
        )
        malformed = """update_topic(strategic_intent='Generate')---
id: ATM-wrong000
type: atom
parent_source: "01_Contexts/CTX-wrong000"
source_path: ""
claim_type: concept
confidence_score: 0.8
contradicts: []
is_verified_by_human: false
is_flagged_for_agent: false
last_updated: old
---
# QMD

## Definition / Claim

QMD indexes markdown.
"""

        repaired = ingest_llm._enforce_atom_contract(
            malformed,
            atom_id="ATM-good1234",
            candidate=candidate,
            context_id="CTX-good1234",
            relpath="02_Wiki/LLM/rag-overview.md",
            today="2026-05-04T00:00:00Z",
        )
        parsed = page_writer.parse_page(repaired)

        self.assertEqual(parsed.frontmatter["id"], "ATM-good1234")
        self.assertEqual(parsed.frontmatter["claim_type"], "entity")
        self.assertNotIn("update_topic", parsed.body)
        self.assertIn("QMD indexes markdown.", parsed.body)

    def test_atom_contract_extracts_yamlish_fenced_page(self) -> None:
        candidate = ingest_llm.AtomCandidate(
            name="Dense Passage Retriever",
            type="technique",
            one_liner="Dense retrieval model.",
        )
        malformed = """update_topic(strategic_intent='Generate')```yaml
id: ATM-wrong000
type: atom
parent_source: "01_Contexts/CTX-wrong000"
source_path: ""
claim_type: technique
confidence_score: 0.8
contradicts: []
is_verified_by_human: false
is_flagged_for_agent: false
last_updated: old
---
# Dense Passage Retriever

## Definition / Claim

DPR maps queries and passages into a shared vector space.
```"""

        repaired = ingest_llm._enforce_atom_contract(
            malformed,
            atom_id="ATM-good1234",
            candidate=candidate,
            context_id="CTX-good1234",
            relpath="02_Wiki/LLM/rag-overview.md",
            today="2026-05-04T00:00:00Z",
        )
        parsed = page_writer.parse_page(repaired)

        self.assertEqual(parsed.frontmatter["id"], "ATM-good1234")
        self.assertNotIn("update_topic", parsed.body)
        self.assertIn("DPR maps queries", parsed.body)

    def test_atom_contract_rejects_tool_refusal_response(self) -> None:
        candidate = ingest_llm.AtomCandidate(
            name="Elliptical Gaussian Kernel",
            type="entity",
            one_liner="Gaussian kernel.",
        )

        with self.assertRaises(ingest_llm.LLMError):
            ingest_llm._enforce_atom_contract(
                "I am unable to write the Atom page because I do not have the write_file tool.",
                atom_id="ATM-good1234",
                candidate=candidate,
                context_id="CTX-good1234",
                relpath="04_Resources/paper.pdf",
                today="2026-05-04T00:00:00Z",
            )

    def test_concept_contract_wraps_missing_opening_frontmatter_delimiter(self) -> None:
        plan = ingest_llm.ConceptPlan(
            name="Schema Stable Concept",
            domain="graphics",
            atom_ids=["ATM-a1b2c3d4", "ATM-b2c3d4e5"],
            description="Test concept.",
        )
        malformed = """id: CON-wrong000
type: concept
dependencies: ['02_Atoms/ATM-wrong000']
domain: wrong
confidence_score: 0.66
last_updated: old
---
# Schema Stable Concept

## 2. How the Atoms Connect

Uses [[02_Atoms/ATM-a1b2c3d4]].
"""

        repaired = ingest_llm._enforce_concept_contract(
            malformed,
            concept_id="CON-good1234",
            plan=plan,
            today="2026-05-04T00:00:00Z",
        )
        parsed = page_writer.parse_page(repaired)

        self.assertEqual(parsed.frontmatter["id"], "CON-good1234")
        self.assertNotIn("dependencies", parsed.frontmatter)
        self.assertIn("## 1. Core Idea", parsed.body)
        self.assertIn("## Relations", parsed.body)
        self.assertIn("[[02_Atoms/ATM-a1b2c3d4]]", parsed.body)
        self.assertIn("[[02_Atoms/ATM-b2c3d4e5]]", parsed.body)

    def test_concept_contract_extracts_wrapped_fenced_page(self) -> None:
        plan = ingest_llm.ConceptPlan(
            name="Wrapped Concept",
            domain="graphics",
            atom_ids=["ATM-a1b2c3d4", "ATM-b2c3d4e5"],
            description="Test concept.",
        )
        malformed = """update_topic(strategic_intent='Generate```markdown
---
id: CON-wrong000
type: concept
dependencies: ['02_Atoms/ATM-wrong000']
domain: wrong
confidence_score: 0.5
last_updated: old
---
# Wrapped Concept

## 1. Core Idea

Wrapped body.

## Relations
[[02_Atoms/ATM-wrong000]]
```"""

        repaired = ingest_llm._enforce_concept_contract(
            malformed,
            concept_id="CON-good1234",
            plan=plan,
            today="2026-05-04T00:00:00Z",
        )
        parsed = page_writer.parse_page(repaired)

        self.assertEqual(parsed.frontmatter["id"], "CON-good1234")
        self.assertNotIn("update_topic", parsed.body)
        self.assertIn("Wrapped body.", parsed.body)
        self.assertIn("[[02_Atoms/ATM-a1b2c3d4]]", parsed.body)

    def test_concept_contract_unlinks_out_of_scope_atom_ids(self) -> None:
        plan = ingest_llm.ConceptPlan(
            name="Scoped Concept",
            domain="graphics",
            atom_ids=["ATM-a1b2c3d4", "ATM-b2c3d4e5"],
            description="Test concept.",
        )
        malformed = """---
id: CON-wrong000
type: concept
dependencies: ['02_Atoms/ATM-a1b2c3d4']
confidence_score: 0.7
---
# Scoped Concept

## 2. How the Atoms Connect

Uses [[02_Atoms/ATM-a1b2c3d4]] and typo [[02_Atoms/ATM-a1b2c3d5|Vector Embedding]].
"""

        repaired = ingest_llm._enforce_concept_contract(
            malformed,
            concept_id="CON-good1234",
            plan=plan,
            today="2026-05-04T00:00:00Z",
        )
        parsed = page_writer.parse_page(repaired)

        self.assertIn("[[02_Atoms/ATM-a1b2c3d4]]", parsed.body)
        self.assertIn("Vector Embedding", parsed.body)
        self.assertNotIn("ATM-a1b2c3d5", parsed.body)

    def test_lint_reports_and_fixes_empty_layer_link_and_atom_source_path(self) -> None:
        source = self.root / "03_Notes" / "source.md"
        source.write_text("# Source\n\nBody\n", encoding="utf-8")
        context_id = "CTX-good1234"
        with db.connect(self.paths.state_db) as conn:
            conn.execute(
                """INSERT INTO sources
                   (relpath, content_hash, file_type, bytes, added_at, status, context_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("03_Notes/source.md", "hash", "md", source.stat().st_size,
                 "2026-05-04T00:00:00Z", "curated", context_id),
            )

        (self.paths.contexts / f"{context_id}.md").write_text(
            """---
id: CTX-good1234
type: context
source_path: "[[03_Notes/source.md]]"
source_hash: hash
last_updated: 2026-05-04T00:00:00Z
---

# Source
""",
            encoding="utf-8",
        )
        atom_path = self.paths.atoms / "ATM-bad1234.md"
        atom_path.write_text(
            """---
id: ATM-bad1234
type: atom
parent_source: 01_Contexts/CTX-good1234
source_path: ""
claim_type: fact
last_updated: 2026-05-04T00:00:00Z
---

# Bad Atom

- [[01_Contexts/]]
""",
            encoding="utf-8",
        )

        report = lint.run_lint(self.paths)
        checks = {issue.check for issue in report.issues}
        self.assertIn(lint.CheckId.BROKEN_WIKILINK, checks)
        self.assertIn(lint.CheckId.INVALID_SOURCE_PATH, checks)

        modified = lint.apply_fixes(self.paths, report.issues)
        self.assertGreaterEqual(modified, 1)

        repaired = page_writer.read_page(atom_path)
        self.assertIsNotNone(repaired)
        self.assertEqual(repaired.frontmatter["source_path"], "[[03_Notes/source]]")
        self.assertNotIn("[[01_Contexts/]]", repaired.body)

    def test_lint_fix_does_not_delete_unresolved_broken_wikilink(self) -> None:
        atom_path = self.paths.atoms / "ATM-badlink.md"
        atom_path.write_text(
            """---
id: ATM-badlink
type: atom
parent_source: 01_Contexts/CTX-missing
source_path: "[[03_Notes/source]]"
claim_type: fact
last_updated: 2026-05-04T00:00:00Z
---

# Bad Link

- [[02_Atoms/ATM-doesnotexist]]
""",
            encoding="utf-8",
        )

        report = lint.run_lint(self.paths)
        broken = [
            issue for issue in report.issues
            if issue.check == lint.CheckId.BROKEN_WIKILINK
            and issue.context.get("old_target") == "02_Atoms/ATM-doesnotexist"
        ]
        self.assertEqual(len(broken), 1)
        self.assertTrue(broken[0].fixable)
        self.assertFalse(lint.is_safe_fixable(broken[0]))

        modified = lint.apply_fixes(self.paths, report.issues)
        self.assertEqual(modified, 0)
        content = atom_path.read_text(encoding="utf-8")
        self.assertIn("[[02_Atoms/ATM-doesnotexist]]", content)

    def test_lint_fix_reconnects_unambiguous_broken_wikilink(self) -> None:
        (self.paths.atoms / "ATM-target1234.md").write_text(
            """---
id: ATM-target1234
type: atom
parent_source: 01_Contexts/CTX-source
source_path: "[[03_Notes/source]]"
claim_type: fact
last_updated: 2026-05-04T00:00:00Z
---

# Target
""",
            encoding="utf-8",
        )
        atom_path = self.paths.concepts / "CON-badlink.md"
        atom_path.write_text(
            """---
id: CON-badlink
type: concept
domain: test
last_updated: 2026-05-04T00:00:00Z
---

# Bad Link

- [[03_Concepts/ATM-target1234]]
""",
            encoding="utf-8",
        )

        report = lint.run_lint(self.paths)
        broken = [
            issue for issue in report.issues
            if issue.check == lint.CheckId.BROKEN_WIKILINK
            and issue.context.get("old_target") == "03_Concepts/ATM-target1234"
        ]
        self.assertEqual(len(broken), 1)
        self.assertTrue(lint.is_safe_fixable(broken[0]))

        modified = lint.apply_fixes(self.paths, report.issues)
        self.assertGreaterEqual(modified, 1)
        content = atom_path.read_text(encoding="utf-8")
        self.assertIn("[[02_Atoms/ATM-target1234]]", content)
        self.assertNotIn("[[03_Concepts/ATM-target1234]]", content)

    def test_mode_c_regeneration_preserves_concept_identity_fields(self) -> None:
        class _StubClient:
            def chat(self, messages, thinking=False, temperature=0.3):  # noqa: ARG002
                return """---
id: CON-hijacked
type: concept
name: hijacked-name
dependencies: ["02_Atoms/ATM-other"]
domain: wrong
confidence_score: 0.11
last_updated: 2000-01-01T00:00:00Z
---

## 1. Core Idea

Regenerated body.
"""

        atom_id = "ATM-good1234"
        con_id = "CON-good1234"
        (self.paths.atoms / f"{atom_id}.md").write_text(
            """---
id: ATM-good1234
type: atom
parent_source: 01_Contexts/CTX-good1234
source_path: "[[03_Notes/source]]"
claim_type: fact
last_updated: 2026-05-04T00:00:00Z
---

Atom body.
""",
            encoding="utf-8",
        )
        (self.paths.concepts / f"{con_id}.md").write_text(
            """---
id: CON-good1234
type: concept
name: stable-name
domain: stable-domain
confidence_score: 0.88
last_updated: 2026-05-04T00:00:00Z
---

## 1. Core Idea

Original body.

## Relations
[[02_Atoms/ATM-good1234]]
""",
            encoding="utf-8",
        )

        ok = sync._regenerate_concept(self.paths, _StubClient(), con_id)
        self.assertTrue(ok)
        rewritten = page_writer.read_page(self.paths.concepts / f"{con_id}.md")
        self.assertIsNotNone(rewritten)
        self.assertEqual(rewritten.frontmatter["id"], con_id)
        self.assertEqual(rewritten.frontmatter["name"], "stable-name")
        self.assertNotIn("dependencies", rewritten.frontmatter)
        self.assertEqual(
            page_writer.extract_relation_targets(rewritten.body, prefix="02_Atoms/"),
            ["02_Atoms/ATM-good1234"],
        )

    def test_prompts_keep_concept_edges_in_relations_only(self) -> None:
        msgs_l3 = prompts.build_theme_page_messages(
            theme_id="CON-good1234",
            name="Stable Concept",
            domain="graphics",
            fragment_ids=["ATM-a", "ATM-b"],
            fragments_content="dummy",
            today="2026-05-04T00:00:00Z",
        )
        text_l3 = msgs_l3[-1].content
        self.assertIn("Do NOT include `dependencies`", text_l3)
        self.assertIn("## Relations", text_l3)
        self.assertNotIn("dependencies: ['02_Atoms/ATM-a", text_l3)

        msgs_l4 = prompts.build_curation_page_messages(
            curation_id="EXH-good1234",
            topic="Stable Exhibition",
            theme_ids=["CON-a", "CON-b"],
            themes_content="dummy",
            confidence=0.8,
            today="2026-05-04T00:00:00Z",
        )
        text_l4 = msgs_l4[-1].content
        self.assertIn("core_concepts: ['03_Concepts/CON-a', '03_Concepts/CON-b']", text_l4)
        self.assertNotIn("'[[03_Concepts/CON-a]]'", text_l4)

    def test_strip_llm_noise_keeps_first_yaml_fenced_page(self) -> None:
        noisy = """```yaml
---
id: CON-good1234
type: concept
dependencies: ['02_Atoms/ATM-a']
---
# First

## Relations
[[02_Atoms/ATM-a]]
```markdown
---
id: CON-good1234
type: concept
dependencies: ['02_Atoms/ATM-b']
---
# Duplicate
```"""

        cleaned = page_writer.strip_llm_noise(noisy)
        parsed = page_writer.parse_page(cleaned)
        self.assertEqual(parsed.frontmatter["id"], "CON-good1234")
        self.assertEqual(
            page_writer.extract_relation_targets(parsed.body, prefix="02_Atoms/"),
            ["02_Atoms/ATM-a"],
        )
        self.assertIn("# First", parsed.body)
        self.assertNotIn("# Duplicate", parsed.body)

    def test_lint_fix_unwraps_yaml_fenced_frontmatter(self) -> None:
        concept_path = self.paths.concepts / "CON-good1234.md"
        concept_path.write_text(
            """```yaml
---
id: CON-good1234
type: concept
domain: graphics
last_updated: 2026-05-04T00:00:00Z
---
# Good Concept
```markdown
---
id: CON-good1234
type: concept
---
# Duplicate
```""",
            encoding="utf-8",
        )

        report = lint.run_lint(self.paths)
        issue = next(i for i in report.issues if i.check == lint.CheckId.MISSING_FRONTMATTER)
        self.assertTrue(issue.fixable)

        modified = lint.apply_fixes(self.paths, report.issues)
        self.assertGreaterEqual(modified, 1)
        repaired = page_writer.read_page(concept_path)
        self.assertIsNotNone(repaired)
        self.assertEqual(repaired.frontmatter["id"], "CON-good1234")
        self.assertIn("# Good Concept", repaired.body)
        self.assertNotIn("# Duplicate", repaired.body)

    def test_empty_l3_clustering_marks_layer_error_when_atoms_exist(self) -> None:
        with db.connect(self.paths.state_db) as conn:
            cur = conn.execute(
                """INSERT INTO sources
                   (relpath, content_hash, file_type, bytes, added_at, status, context_id,
                    l1_status, l2_status, l3_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "03_Notes/source.md",
                    "hash",
                    "md",
                    10,
                    "2026-05-04T00:00:00Z",
                    "curated",
                    "CTX-good1234",
                    "done",
                    "done",
                    "pending",
                ),
            )
            source_id = cur.lastrowid
        (self.paths.atoms / "ATM-good1234.md").write_text(
            """---
id: ATM-good1234
type: atom
parent_source: 01_Contexts/CTX-good1234
source_path: "[[03_Notes/source]]"
claim_type: fact
last_updated: 2026-05-04T00:00:00Z
---

# Atom
""",
            encoding="utf-8",
        )

        ingest_llm._set_l3_result_status(self.paths, [source_id], [])

        with db.connect(self.paths.state_db) as conn:
            row = conn.execute(
                "SELECT l3_status, layer_error FROM sources WHERE id = ?",
                (source_id,),
            ).fetchone()
        self.assertEqual(row["l3_status"], "error")
        self.assertEqual(row["layer_error"], "concept_clustering_failed")

    def test_l3_success_marks_all_l2_done_sources(self) -> None:
        source_ids = []
        with db.connect(self.paths.state_db) as conn:
            for idx in range(2):
                cur = conn.execute(
                    """INSERT INTO sources
                       (relpath, content_hash, file_type, bytes, added_at, status, context_id,
                        l1_status, l2_status, l3_status, layer_error)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        f"03_Notes/source-{idx}.md",
                        f"hash-{idx}",
                        "md",
                        10,
                        "2026-05-04T00:00:00Z",
                        "curated",
                        f"CTX-good123{idx}",
                        "done",
                        "done",
                        "error",
                        "concept_clustering_failed",
                    ),
                )
                source_ids.append(cur.lastrowid)
        for idx in range(2):
            (self.paths.contexts / f"CTX-good123{idx}.md").write_text(
                f"""---
id: CTX-good123{idx}
type: context
source_path: '[[03_Notes/source-{idx}.md]]'
source_hash: hash-{idx}
domain: test
last_updated: '2026-05-04T00:00:00Z'
---

# Source {idx}
""",
                encoding="utf-8",
            )
            (self.paths.atoms / f"ATM-good123{idx}.md").write_text(
                f"""---
id: ATM-good123{idx}
type: atom
parent_source: 01_Contexts/CTX-good123{idx}
source_path: '[[03_Notes/source-{idx}.md]]'
claim_type: fact
confidence_score: 1.0
last_updated: '2026-05-04T00:00:00Z'
---

# Atom {idx}

## Relations
[[01_Contexts/CTX-good123{idx}]]
""",
                encoding="utf-8",
            )
        (self.paths.concepts / "CON-good1234.md").write_text(
            """---
id: CON-good1234
type: concept
confidence_score: 1.0
last_updated: '2026-05-04T00:00:00Z'
---

# Concept

## Relations
[[02_Atoms/ATM-good1230]]
[[02_Atoms/ATM-good1231]]
""",
            encoding="utf-8",
        )

        all_l2_done = ingest_llm._source_ids_with_l2_done(self.paths)
        ingest_llm._set_l3_result_status(
            self.paths,
            all_l2_done,
            [(self.paths.concepts / "staged.md", self.paths.concepts / "CON-good1234.md",
              ingest_llm.PageChange("CON-good1234", "03_Concepts/CON-good1234.md", "03_Concepts", "created"))],
        )

        with db.connect(self.paths.state_db) as conn:
            rows = conn.execute(
                "SELECT l3_status, layer_error FROM sources WHERE id IN (?, ?) ORDER BY id",
                source_ids,
            ).fetchall()
        self.assertEqual([row["l3_status"] for row in rows], ["done", "done"])
        self.assertEqual([row["layer_error"] for row in rows], [None, None])

    def test_existing_l3_pages_do_not_clear_sync_l3_errors(self) -> None:
        with db.connect(self.paths.state_db) as conn:
            conn.execute(
                """INSERT INTO sources
                   (relpath, content_hash, file_type, bytes, added_at, status, context_id,
                    l1_status, l2_status, l3_status, layer_error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "03_Notes/source.md",
                    "hash",
                    "md",
                    10,
                    "2026-05-04T00:00:00Z",
                    "curated",
                    "CTX-good1234",
                    "done",
                    "done",
                    "error",
                    "concept_clustering_failed",
                ),
            )
        (self.paths.concepts / "CON-good1234.md").write_text(
            """---
id: CON-good1234
type: concept
domain: test
last_updated: 2026-05-04T00:00:00Z
---

# Concept
""",
            encoding="utf-8",
        )

        ingest_llm._mark_existing_l3_done_if_present(self.paths)

        with db.connect(self.paths.state_db) as conn:
            row = conn.execute("SELECT l3_status, layer_error FROM sources").fetchone()
        self.assertEqual(row["l3_status"], "error")
        self.assertEqual(row["layer_error"], "concept_clustering_failed")

    def test_ingest_source_reads_numbered_atom_candidates_section(self) -> None:
        class _StubClient:
            optimal_chunk_chars = 12000

            def chat_stream(self, messages, thinking=False, temperature=0.0):  # noqa: ARG002
                page = """---
id: ATM-temp0000
type: atom
parent_source: "01_Contexts/CTX-good1234"
source_path: "[[03_Notes/source]]"
claim_type: fact
confidence_score: 0.75
contradicts: []
is_verified_by_human: false
is_flagged_for_agent: false
last_updated: 2026-05-04T00:00:00Z
---
# Candidate A

## Definition / Claim

Candidate detail.

## Relations
[[01_Contexts/CTX-good1234]]
"""
                yield page
                return page

        relpath = "03_Notes/source.md"
        source = self.root / relpath
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# Source\n\nBody", encoding="utf-8")
        with db.connect(self.paths.state_db) as conn:
            cur = conn.execute(
                """INSERT INTO sources
                   (relpath, content_hash, file_type, bytes, added_at, status, context_id,
                    l1_status, l2_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    relpath,
                    "hash",
                    "md",
                    source.stat().st_size,
                    "2026-05-04T00:00:00Z",
                    "pending",
                    "CTX-good1234",
                    "done",
                    "pending",
                ),
            )
            source_id = cur.lastrowid
        (self.paths.contexts / "CTX-good1234.md").write_text(
            """---
id: CTX-good1234
type: context
source_path: "[[03_Notes/source]]"
source_hash: hash
domain: test
last_updated: 2026-05-04T00:00:00Z
tags: []
---

## Summary

Summary.

## 2. Atom Candidates

- [fact] Candidate A: Candidate detail.
""",
            encoding="utf-8",
        )

        result = ingest_llm.ingest_source(
            self.paths,
            source_id,
            _StubClient(),
            ingest_llm.IngestCallbacks(),
            mode="batch",
        )

        self.assertIsNone(result.error)
        self.assertEqual(result.fragments_created, 1)
        self.assertEqual(len(list(self.paths.atoms.glob("ATM-*.md"))), 1)

    def test_atom_candidates_preserve_recall_and_only_dedupe_exact_names(self) -> None:
        candidates = [
            {"name": "2D Gaussian Splatting", "type": "technique", "one_liner": "A."},
            {"name": "2DGS", "type": "technique", "one_liner": "B."},
            {"name": "Depth Distortion Loss", "type": "equation", "one_liner": "C."},
            {"name": "Normal Consistency Loss", "type": "equation", "one_liner": "D."},
            {"name": "2DGS", "type": "technique", "one_liner": "Duplicate."},
        ]

        prepared = ingest_raw._prepare_atom_candidates(candidates)

        self.assertEqual(
            [c["name"] for c in prepared],
            [
                "2D Gaussian Splatting",
                "2DGS",
                "Depth Distortion Loss",
                "Normal Consistency Loss",
            ],
        )

    def test_relaxed_json_loader_repairs_latex_backslashes(self) -> None:
        data = ingest_raw._loads_json_relaxed(
            r"""{"summary":"Equation \alpha + \mathbf{x} + \underbrace{y}","atom_candidates":[]}"""
        )
        self.assertEqual(data["summary"], r"Equation \alpha + \mathbf{x} + \underbrace{y}")

    def test_l1_chunk_summary_falls_back_to_smaller_chunks(self) -> None:
        class _StubClient:
            def __init__(self) -> None:
                self.calls = 0

            def chat(self, messages, thinking=False, json_mode=False, temperature=0.0):  # noqa: ARG002
                self.calls += 1
                prompt = messages[-1].content
                if len(prompt) > 12000:
                    raise ingest_raw.LLMError("too large")
                return """{
  "title": "Chunked Source",
  "domain": "test",
  "summary": "Small summary.",
  "key_claims": ["Claim"],
  "atom_candidates": [{"name":"Candidate","type":"fact","one_liner":"Detail."}],
  "tags": ["chunked"]
}"""

        data, error = ingest_raw._summarize_chunk_with_fallback(
            _StubClient(),
            prompts,
            title="Chunked Source",
            chunk="A" * 22000,
            thinking=False,
            label="chunk 1",
        )

        self.assertIsNone(error)
        self.assertGreaterEqual(len(data), 2)
        self.assertEqual(data[0]["summary"], "Small summary.")

    def test_generate_l1_context_matches_v13_schema_shape(self) -> None:
        class _StubClient:
            optimal_chunk_chars = 30000

            def chat(self, messages, thinking=False, json_mode=False, temperature=0.0):  # noqa: ARG002
                return """{
  "title": "Schema Test Source",
  "domain": "test-domain",
  "summary": "Dense source summary.",
  "key_claims": ["Claim A", "Claim B"],
  "atom_candidates": [
    {"name": "Candidate A", "type": "fact", "one_liner": "Candidate detail."}
  ],
  "tags": ["schema", "test"]
}"""

        relpath = "03_Notes/schema-source.md"
        source = self.root / relpath
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# Schema Source\n\nBody", encoding="utf-8")
        content_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        with db.connect(self.paths.state_db) as conn:
            cur = conn.execute(
                """INSERT INTO sources
                   (relpath, content_hash, file_type, bytes, added_at, status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (relpath, content_hash, "md", source.stat().st_size,
                 "2026-05-04T00:00:00Z", "pending"),
            )
            source_id = cur.lastrowid

        context_id = ingest_raw.generate_l1_summary(
            self.paths,
            source_id=source_id,
            relpath=relpath,
            content_hash=content_hash,
            client=_StubClient(),
            config={},
            thinking=False,
        )

        self.assertIsNotNone(context_id)
        self.assertRegex(context_id or "", r"^CTX-[0-9a-f]{8}$")
        parsed = page_writer.read_page(self.paths.contexts / f"{context_id}.md")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.frontmatter["id"], context_id)
        self.assertEqual(parsed.frontmatter["source_hash"], content_hash)
        self.assertRegex(parsed.body, r"^## Summary")
        self.assertIn("## 1. Key Claims", parsed.body)
        self.assertIn("## 2. Atom Candidates", parsed.body)
        self.assertNotRegex(parsed.body, r"^# ", re.MULTILINE)


if __name__ == "__main__":
    unittest.main()
