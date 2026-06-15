"""Plan A (RAG Retrieval Provenance, v0.10.0) structural tests and oracles.

Two test kinds (mirroring the Failure Atlas and Plan B/C conventions):

- ``test_struct_*`` — structural tests that PASS today; they assert the shape
  of new Plan A API surfaces (EvidencePack/EvidenceItem fields, StructuredLocator
  presence, RTR-* ID generation). These become the regression guard once P2–P4
  implement the behavior.
- ``test_oracle_*`` — behavior oracles, ``xfail(strict=True)``, that will XPASS
  when the corresponding implementation phase ships. Each oracle documents WHICH
  spec section it exercises.

No not-yet-implemented symbol is imported at module top; new behavior is probed
lazily inside each oracle or structural test so that collection never breaks.

Existing F3/F4/F5 oracles live in ``test_failure_atlas_repro.py`` and are NOT
duplicated here; Plan A turns those green in P3.
"""

from __future__ import annotations

import inspect
import tempfile
import uuid
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db
from curator.retrieval import evidence as evidence_mod
from curator.retrieval.models import EvidenceItem, EvidencePack

RELPATH = "04_Resources/pa.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def vault():
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        paths = cfg.WikiPaths(root)
        paths.internal.mkdir(parents=True, exist_ok=True)
        db.init_db(paths.state_db)
        with db.connect(paths.state_db) as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES (?, 'h', 'md', 1, datetime('now'))",
                (RELPATH,),
            )
        yield paths


def _seed_spans(paths: cfg.WikiPaths, n: int = 3) -> list[str]:
    return [
        db.upsert_source_span(
            paths.state_db, source_id=1, relpath=RELPATH,
            span_type="paragraph", content_hash=f"pa-span-{i}",
            section_title=f"Section {i}", text_preview=f"Span {i} content.",
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# §28.1 — policy parameter: structural shape
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="§28.1: build_evidence does not yet have a 'policy' parameter. "
    "Assigned to Plan A P3.",
)
def test_struct_build_evidence_accepts_policy_kwarg() -> None:
    """SYSTEM_BEHAVIOR §28.1: build_evidence must accept a 'policy' keyword arg."""
    params = inspect.signature(evidence_mod.build_evidence).parameters
    assert "policy" in params


# ---------------------------------------------------------------------------
# §22.3 — EvidencePack extended fields
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="§22.3: EvidencePack missing retrieval_execution_id. Assigned to Plan A P2.",
)
def test_struct_evidence_pack_has_retrieval_execution_id() -> None:
    """SCHEMA §22.3: EvidencePack must have retrieval_execution_id field."""
    pack = EvidencePack(route="local")
    assert hasattr(pack, "retrieval_execution_id")


@pytest.mark.xfail(
    strict=True,
    reason="§22.3: EvidencePack missing omitted_counts. Assigned to Plan A P3.",
)
def test_struct_evidence_pack_has_omitted_counts() -> None:
    """SCHEMA §22.3: EvidencePack must have omitted_counts dict field."""
    pack = EvidencePack(route="local")
    assert hasattr(pack, "omitted_counts")
    assert isinstance(pack.omitted_counts, dict)


# ---------------------------------------------------------------------------
# §29.5 — EvidenceItem.locator field
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="§29.5: EvidenceItem missing locator field. Assigned to Plan A P4.",
)
def test_struct_evidence_item_has_locator_field() -> None:
    """SYSTEM_BEHAVIOR §29.5 / SCHEMA §22.3: EvidenceItem must have locator."""
    item = EvidenceItem(id="x", kind="source_span", title="t", text="s")
    assert hasattr(item, "locator")
    assert item.locator is None


# ---------------------------------------------------------------------------
# §29.2 — StructuredLocator dataclass exists
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="§29.2: StructuredLocator not yet defined in retrieval.models. "
    "Assigned to Plan A P4.",
)
def test_struct_structured_locator_importable() -> None:
    """SYSTEM_BEHAVIOR §29.2: StructuredLocator dataclass must be in models."""
    from curator.retrieval.models import StructuredLocator  # noqa: F401
    loc = StructuredLocator(
        source_id=1, source_kind="vault_markdown",
        relpath="03_Notes/x.md", heading=None, block_id=None,
        page_number=None, toc_id=None, external_uri=None,
        locator_status="exact",
    )
    assert loc.locator_status == "exact"


# ---------------------------------------------------------------------------
# §30.1 — RTR-* ID generation oracle
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="§30.1: build_evidence does not yet generate an RTR-* retrieval "
    "execution id; EvidencePack has no retrieval_execution_id field. "
    "Assigned to Plan A P2.",
)
def test_oracle_build_evidence_generates_rtr_id(vault) -> None:
    """build_evidence must attach an RTR-* id to the returned pack (§30.1)."""
    from curator.retrieval.models import QueryRequest
    request = QueryRequest(question="test query")
    pack = evidence_mod.build_evidence(vault, request, "local")
    assert pack.retrieval_execution_id.startswith("RTR-"), (
        "§30.1: retrieval_execution_id must be a RTR-* id"
    )


@pytest.mark.xfail(
    strict=True,
    reason="§30.1: two calls to build_evidence must produce different RTR-* ids. "
    "Assigned to Plan A P2.",
)
def test_oracle_rtr_ids_are_unique(vault) -> None:
    """Each build_evidence call must produce a fresh unique RTR-* id (§30.1)."""
    from curator.retrieval.models import QueryRequest
    request = QueryRequest(question="test query")
    pack1 = evidence_mod.build_evidence(vault, request, "local")
    pack2 = evidence_mod.build_evidence(vault, request, "local")
    assert pack1.retrieval_execution_id != pack2.retrieval_execution_id


# ---------------------------------------------------------------------------
# §28.2 / §22.6 — global route bounded oracle
# (F4 canonical oracle lives in test_failure_atlas_repro.py)
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="§28.2: build_evidence global route does not record omitted_counts "
    "for dropped community reports. Assigned to Plan A P3.",
)
def test_oracle_global_omissions_recorded(vault) -> None:
    """Dropped reports in global route must appear in omitted_counts (§28.2 / §22.6)."""
    from curator.retrieval.models import QueryRequest
    paths = vault
    span = db.upsert_source_span(
        paths.state_db, source_id=1, relpath=RELPATH, span_type="paragraph",
        content_hash="g-span", section_title="Intro",
        text_preview="Corpus span.",
    )
    for i in range(15):
        db.upsert_community_report(
            paths.state_db, community_key=f"cr-{i}", title=f"Report {i}",
            summary=f"Topic {i % 2} content.", full_content="",
            dependency_hash=f"d-{i}", entity_ids=[], source_span_ids=[span],
            rank=0.5,
        )
    request = QueryRequest(question="deep learning optimization", mode="global")
    pack = evidence_mod.build_evidence(paths, request, "global")
    assert "global_reports" in pack.omitted_counts, (
        "§28.2: global route must record omitted report count in omitted_counts"
    )
    assert pack.omitted_counts["global_reports"] > 0


# ---------------------------------------------------------------------------
# §28.3 / §22.7 — evidence_block omission oracle
# (F5 canonical oracle lives in test_failure_atlas_repro.py)
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="§28.3: evidence_block does not yet append an omission marker when "
    "items are dropped. Assigned to Plan A P3.",
)
def test_oracle_evidence_block_omission_count_in_marker() -> None:
    """Omission marker must include the numeric count (§28.3 / §22.7)."""
    import re
    items = [
        EvidenceItem(id=f"X-{i:02d}", kind="source_span", title=f"T{i}", text="a" * 1200)
        for i in range(20)
    ]
    pack = EvidencePack(route="local", items=items)
    block = pack.evidence_block(max_chars=6000)
    # Must contain a number followed by "omitted" (or vice versa).
    assert re.search(r"\d+\s*items?\s*omitted|\bomitted\b.*\d+", block, re.IGNORECASE), (
        "§28.3: evidence_block marker must include numeric omitted count"
    )


# ---------------------------------------------------------------------------
# §29 — StructuredLocator resolution oracle
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="§29.4: build_evidence does not yet resolve StructuredLocator for "
    "evidence items. Assigned to Plan A P4.",
)
def test_oracle_evidence_items_have_locators(vault, tmp_path) -> None:
    """Each source-span-backed EvidenceItem must carry a StructuredLocator (§29.5)."""
    paths = vault
    # Write a real markdown file for the source so locator resolution can read it.
    note_dir = tmp_path / "04_Resources"
    note_dir.mkdir()
    note_file = note_dir / "pa.md"
    note_file.write_text("# Intro\n\nSpan content.\n")
    # Point the source relpath at the real file.
    with db.connect(paths.state_db) as conn:
        conn.execute("UPDATE sources SET relpath = ? WHERE id = 1",
                     (str(note_file.relative_to(tmp_path)),))

    _seed_spans(paths)
    from curator.retrieval.models import QueryRequest
    request = QueryRequest(question="span content query")
    pack = evidence_mod.build_evidence(paths, request, "local")
    span_items = [it for it in pack.items if it.kind == "source_span"]
    assert span_items, "expected at least one source_span item"
    for item in span_items:
        assert item.locator is not None, (
            f"§29.5: source_span item {item.id} must have a StructuredLocator"
        )
        assert item.locator.locator_status in (
            "exact", "fallback_file", "fallback_source",
            "duplicate_anchor", "stale", "unavailable",
        ), f"locator_status {item.locator.locator_status!r} not in allowed set"


# ---------------------------------------------------------------------------
# §22.4 — retrieval_trace_json contract oracle
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="§22.4: query_traces.retrieval_trace_json does not yet contain the "
    "Plan A contract fields (contract_version, retrieval_execution_id). "
    "Assigned to Plan A P2.",
)
def test_oracle_retrieval_trace_has_contract_version(vault) -> None:
    """retrieval_trace_json must carry contract_version and RTR-* id (§22.4)."""
    import json
    from curator.retrieval import QueryOrchestrator
    from curator.retrieval.models import QueryRequest

    class _NoClient:
        model = "fake"
        def chat(self, *a, **k): raise AssertionError("no LLM in this test")

    paths = vault
    orch = QueryOrchestrator(paths, _NoClient())
    result = orch.fetch_context(QueryRequest(question="test"))
    trace_id = result.get("trace_id", "")
    assert trace_id.startswith("QTR-")
    traces = db.list_query_traces(paths.state_db, limit=1)
    assert traces
    trace_json = json.loads(traces[0].get("retrieval_trace_json") or "{}")
    assert trace_json.get("contract_version") == "1", (
        "§22.4: retrieval_trace_json must contain contract_version=1"
    )
    assert trace_json.get("retrieval_execution_id", "").startswith("RTR-"), (
        "§22.4: retrieval_trace_json must contain RTR-* retrieval_execution_id"
    )


# ---------------------------------------------------------------------------
# §28.1 — policy parameter passthrough oracle
# (F3 canonical oracle lives in test_failure_atlas_repro.py)
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="§28.1: orchestrator does not yet forward CurationPolicy to "
    "build_evidence. Assigned to Plan A P3.",
)
def test_oracle_orchestrator_forwards_policy_to_build_evidence(vault) -> None:
    """Orchestrator must forward policy; build_evidence must use it (§28.1)."""
    from unittest.mock import patch
    from curator.retrieval import QueryOrchestrator
    from curator.retrieval.models import QueryRequest

    class _NoClient:
        model = "fake"
        def chat(self, *a, **k): raise AssertionError("no LLM in this test")

    called_with_policy = {}

    original_build = evidence_mod.build_evidence

    def _spy(*args, policy=None, **kwargs):
        called_with_policy["policy"] = policy
        return original_build(*args, policy=policy, **kwargs)

    paths = vault
    with patch.object(evidence_mod, "build_evidence", side_effect=_spy):
        orch = QueryOrchestrator(paths, _NoClient())
        orch.fetch_context(QueryRequest(question="test", workspace_path=""))
    assert "policy" in called_with_policy, (
        "§28.1: orchestrator must call build_evidence with a policy keyword arg"
    )
    assert called_with_policy["policy"] is not None, (
        "§28.1: orchestrator must pass a resolved (non-None) CurationPolicy"
    )
