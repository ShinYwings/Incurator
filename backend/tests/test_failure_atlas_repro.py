"""Failure Atlas deterministic reproductions F1–F13 (Program 1 / Plan D1).

Two test kinds per FAILURE_ATLAS.md §6:

- ``test_f<N>_baseline_*`` assert the CURRENT defective behavior. They pass
  today by construction — they ARE the captured before-state evidence
  (capture-before-repair). If a baseline test fails, production behavior
  changed without an atlas update: that is a contract violation, not a fix.
- ``test_f<N>_oracle_*`` assert the desired contract and are
  ``xfail(strict=True)``. When a downstream program fixes the behavior they
  XPASS and fail the suite, forcing a deliberate atlas/status update in the
  same change.

All fixtures are synthetic (FAILURE_ATLAS.md §9). Provider-dependent paths run
in the declared degraded mode (embedder/reranker/expander = None); the
reproduced defects are independent of provider availability.
"""

from __future__ import annotations

import copy
import inspect
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from curator import config as cfg
from curator import db, plugin_api
from curator.pipeline import community_reports as cr
from curator.pipeline import source_spans as l1
from curator.pipeline import synthesis as syn_mod
from curator.retrieval import QueryOrchestrator, QueryRequest
from curator.retrieval import evidence as evidence_mod
from curator.retrieval import providers
from curator.retrieval import query_expander as qe_mod
from curator.retrieval.embedding import materialize_chunks
from curator.retrieval.models import EvidenceItem, EvidencePack

REPO_ROOT = Path(__file__).resolve().parents[2]
RELPATH = "04_Resources/fa.md"


class _NoChatClient:
    """fetch_context and evidence assembly must never need an LLM."""

    model = "fake"

    def chat(self, *a, **k):  # pragma: no cover - must not be called
        raise AssertionError("no LLM call expected in this diagnostic")


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


@pytest.fixture()
def degraded_search():
    """Declared degraded execution mode: lexical-only engine, no providers."""
    with (
        patch.object(cfg, "load_config", return_value=copy.deepcopy(cfg.DEFAULT_CONFIG)),
        patch.object(providers, "build_embedder", return_value=None),
        patch.object(providers, "build_reranker", return_value=None),
        patch.object(qe_mod, "build_query_expander", return_value=None),
    ):
        yield


def _seed_search_docs(db_path: Path) -> dict[str, str]:
    """Search corpus whose documents declare span provenance."""
    doc_spans = {
        "ATM-fa000001": "SPAN-fa000001",
        "ATM-fa000002": "SPAN-fa000002",
    }
    bodies = {
        "ATM-fa000001": ("Residual learning", "Residual connections ease optimization in deep networks."),
        "ATM-fa000002": ("Attention mechanism", "Attention weights tokens by relevance across the sequence."),
    }
    for rid, span in doc_spans.items():
        title, body = bodies[rid]
        with db.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO source_spans
                    (id, source_id, relpath, span_type, content_hash,
                     text_preview, created_at)
                VALUES (?, 1, ?, 'paragraph', ?, ?, datetime('now'))
                """,
                (span, RELPATH, span, body),
            )
        db.upsert_search_document(
            db_path, record_type="knowledge_unit", record_id=rid, title=title,
            body=body, content_hash=rid, dependency_hash=rid,
            provenance={"source_span_ids": [span]},
        )
    materialize_chunks(db_path)
    return doc_spans


def _all_traces(db_path: Path) -> list[dict]:
    with db.connect(db_path) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM query_traces").fetchall()]


def _store_section_spans(paths: cfg.WikiPaths, text: str, title: str = "Note") -> list[str]:
    sections = [{"id": "s1", "title": title, "page": None, "text": text}]
    return l1.store_source_spans(
        paths.state_db, 1, RELPATH, l1.spans_from_sections(sections)
    )


# ---------------------------------------------------------------------------
# F1 — search-hit provenance dropped at EngineHit→SearchHit conversion
# ---------------------------------------------------------------------------

def test_f1_search_hit_items_carry_source_span_ids(vault, degraded_search) -> None:
    paths = vault
    _seed_search_docs(paths.state_db)
    pack = evidence_mod.build_evidence(
        paths, QueryRequest(question="residual optimization"), "local"
    )
    hits = [it for it in pack.items if it.kind == "search_hit"]
    assert hits, "seeded corpus must produce search hits"
    assert all(it.source_span_ids for it in hits)
    assert set(pack.source_span_ids) == {
        span_id for hit in hits for span_id in hit.source_span_ids
    }
    assert {
        span["id"] for span in db.get_source_spans_by_ids(
            paths.state_db, pack.source_span_ids
        )
    } == set(pack.source_span_ids)


def test_f1_global_search_fallback_preserves_source_span_ids(
    vault, degraded_search
) -> None:
    paths = vault
    expected = set(_seed_search_docs(paths.state_db).values())
    pack = evidence_mod.build_evidence(
        paths, QueryRequest(question="residual optimization"), "global"
    )
    hits = [item for item in pack.items if item.kind == "search_hit"]
    assert hits
    returned = {span_id for hit in hits for span_id in hit.source_span_ids}
    assert returned <= expected
    assert set(pack.source_span_ids) == returned


# ---------------------------------------------------------------------------
# F2 — one logical query persists disconnected QTR- traces
# ---------------------------------------------------------------------------

def test_f2_one_query_persists_one_authoritative_trace(vault, degraded_search) -> None:
    paths = vault
    _seed_search_docs(paths.state_db)
    out = QueryOrchestrator(paths, _NoChatClient()).fetch_context(
        QueryRequest(question="residual optimization", mode="local")
    )
    traces = _all_traces(paths.state_db)
    assert len(traces) == 1
    assert traces[0]["trace_id"] == out["trace_id"]
    retrieval_trace = json.loads(traces[0]["retrieval_trace_json"])
    assert retrieval_trace["mode"] == "hybrid"
    assert retrieval_trace["lists"]


# ---------------------------------------------------------------------------
# F3 — CurationPolicy (KRS) not enforced through evidence assembly
# ---------------------------------------------------------------------------

def test_f3_baseline_build_evidence_accepts_no_policy() -> None:
    params = inspect.signature(evidence_mod.build_evidence).parameters
    assert "policy" not in params
    assert "CurationPolicy" not in inspect.getsource(evidence_mod)


@pytest.mark.xfail(
    strict=True,
    reason="F3 reproduced: build_evidence(paths, request, route) takes no policy; "
    "assigned to program-3 (P3.1 route policy enforcement)",
)
def test_f3_oracle_build_evidence_receives_curation_policy() -> None:
    params = inspect.signature(evidence_mod.build_evidence).parameters
    assert "policy" in params


# ---------------------------------------------------------------------------
# F4 — global evidence query-independent and unbounded
# ---------------------------------------------------------------------------

def _seed_two_topic_reports(paths: cfg.WikiPaths, count_per_topic: int = 15) -> str:
    span = db.upsert_source_span(
        paths.state_db, source_id=1, relpath=RELPATH, span_type="paragraph",
        content_hash="f4span", section_title="Intro",
        text_preview="Optimization and reef ecology corpus.",
    )
    topics = [
        ("optimization", "Gradient descent convergence in deep networks."),
        ("coral reefs", "Symbiotic algae sustain reef calcification."),
    ]
    for t_idx, (topic, summary) in enumerate(topics):
        for i in range(count_per_topic):
            db.upsert_community_report(
                paths.state_db, community_key=f"comm-{topic}-{i}",
                title=f"{topic.title()} report {i}", summary=summary,
                full_content=f"{summary} (community {i})",
                dependency_hash=f"d-{t_idx}-{i}", entity_ids=[],
                source_span_ids=[span], rank=0.5,
            )
    return span


def test_f4_baseline_global_evidence_query_independent_and_unbounded(vault) -> None:
    paths = vault
    _seed_two_topic_reports(paths)
    orch = QueryOrchestrator(paths, _NoChatClient())
    out_a = orch.fetch_context(
        QueryRequest(question="deep learning optimization convergence", mode="global")
    )
    out_b = orch.fetch_context(
        QueryRequest(question="marine biology of coral reefs", mode="global")
    )
    ids_a = [it["id"] for it in out_a["evidence"]]
    ids_b = [it["id"] for it in out_b["evidence"]]
    # Defect: selection never consults the query, and every report is loaded.
    assert ids_a == ids_b
    assert len(ids_a) >= 30


@pytest.mark.xfail(
    strict=True,
    reason="F4 reproduced: _report_items loads all reports query-independently; "
    "assigned to program-3 (bounded query-relevant routes)",
)
def test_f4_oracle_global_evidence_bounded_and_query_dependent(vault) -> None:
    paths = vault
    _seed_two_topic_reports(paths)
    orch = QueryOrchestrator(paths, _NoChatClient())
    out_a = orch.fetch_context(
        QueryRequest(question="deep learning optimization convergence", mode="global")
    )
    out_b = orch.fetch_context(
        QueryRequest(question="marine biology of coral reefs", mode="global")
    )
    ids_a = [it["id"] for it in out_a["evidence"]]
    ids_b = [it["id"] for it in out_b["evidence"]]
    assert len(ids_a) <= 10 and len(ids_b) <= 10  # bounded
    assert set(ids_a) != set(ids_b)  # query-relevant selection


# ---------------------------------------------------------------------------
# F5 — fixed 16,000-char cutoff with silent omission
# ---------------------------------------------------------------------------

def _twenty_item_pack() -> EvidencePack:
    items = [
        EvidenceItem(
            id=f"RPT-{i:02d}", kind="community_report",
            title=f"Report {i}", text="x" * 1000,
        )
        for i in range(20)
    ]
    return EvidencePack(route="global", items=items)


def test_f5_baseline_evidence_block_truncates_silently() -> None:
    pack = _twenty_item_pack()
    block = pack.evidence_block()
    rendered = [i for i in range(20) if f"RPT-{i:02d}]" in block]
    assert len(block) <= 16000
    assert len(rendered) < 20  # items dropped...
    low = block.lower()
    assert "omit" not in low and "truncat" not in low  # ...with no marker


@pytest.mark.xfail(
    strict=True,
    reason="F5 reproduced: evidence_block silently drops items at a char budget; "
    "assigned to program-3 (token budgets / explicit omissions, P3.2)",
)
def test_f5_oracle_evidence_block_reports_explicit_omissions() -> None:
    pack = _twenty_item_pack()
    block = pack.evidence_block()
    assert "omitted" in block.lower()


# ---------------------------------------------------------------------------
# F6 — synthesis items without declared spans grounded to ALL upstream spans
# ---------------------------------------------------------------------------

class _SynthesisFakeClient:
    """Returns one cross-cutting synthesis that declares NO supporting spans."""

    model = "fake"

    def chat(self, messages, *, json_mode=False, temperature=0.3) -> str:
        return json.dumps({
            "syntheses": [
                {
                    "title": "Cross-cutting insight",
                    "statement": "A claim the model did not ground in any span.",
                    "full_content": "",
                    "source_span_ids": [],
                    "confidence": 0.4,
                }
            ]
        })


def _seed_reports_with_spans(paths: cfg.WikiPaths) -> list[str]:
    spans = [
        db.upsert_source_span(
            paths.state_db, source_id=1, relpath=RELPATH, span_type="paragraph",
            content_hash=f"f6span{i}", section_title=f"Sec {i}",
            text_preview=f"Span {i} content.",
        )
        for i in range(4)
    ]
    db.upsert_community_report(
        paths.state_db, community_key="comm-a", title="Community A",
        summary="A", full_content="A", dependency_hash="da",
        entity_ids=[], source_span_ids=spans[:2], rank=0.5,
    )
    db.upsert_community_report(
        paths.state_db, community_key="comm-b", title="Community B",
        summary="B", full_content="B", dependency_hash="db",
        entity_ids=[], source_span_ids=spans[2:], rank=0.5,
    )
    return spans


def test_f6_baseline_synthesis_empty_spans_fall_back_to_all_upstream(vault) -> None:
    paths = vault
    spans = _seed_reports_with_spans(paths)
    node_ids = syn_mod.generate_synthesis(paths, _SynthesisFakeClient())
    assert len(node_ids) == 1
    node = db.list_synthesis_nodes(paths.state_db)[0]
    # Defect: zero declared spans stored as if grounded in EVERY upstream span.
    assert sorted(node["source_span_ids"]) == sorted(spans)
    with db.connect(paths.state_db) as conn:
        dep_count = conn.execute(
            "SELECT COUNT(*) FROM artifact_dependencies WHERE artifact_id = ?",
            (node["id"],),
        ).fetchone()[0]
    assert dep_count == len(spans)


@pytest.mark.xfail(
    strict=True,
    reason="F6 reproduced: synthesis.py:110 grounds undeclared items to all upstream "
    "spans; assigned to program-2 (0 broad fallbacks, P2.3)",
)
def test_f6_oracle_synthesis_spans_match_declared_support(vault) -> None:
    paths = vault
    _seed_reports_with_spans(paths)
    syn_mod.generate_synthesis(paths, _SynthesisFakeClient())
    node = db.list_synthesis_nodes(paths.state_db)[0]
    assert node["source_span_ids"] == []  # exactly the declared (empty) support


# ---------------------------------------------------------------------------
# F7 — no dependency-closure invalidation; stale L1 rows linger after edits
# ---------------------------------------------------------------------------

def test_f7_baseline_no_dependency_invalidation_and_stale_spans_linger(vault) -> None:
    paths = vault
    spans1 = _store_section_spans(paths, "Original derivation of the bound.")
    # Partial pass recorded in the atlas: unchanged re-store is id-stable at L1.
    assert _store_section_spans(paths, "Original derivation of the bound.") == spans1

    syn_id = db.upsert_synthesis_node(
        paths.state_db, title="Depends on the bound",
        statement="Claim citing the original span.", dependency_hash="dep1",
        source_span_ids=[spans1[0]], confidence=0.5,
    )
    db.record_artifact_dependency(
        paths.state_db, artifact_id=syn_id, artifact_type="synthesis_node",
        depends_on_id=spans1[0], depends_on_type="source_span",
        dependency_hash="dep1",
    )

    spans2 = _store_section_spans(paths, "Edited derivation of the bound, corrected.")
    assert set(spans2).isdisjoint(spans1)  # edit minted new ids
    with db.connect(paths.state_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM source_spans").fetchone()[0]
    # Defect: stale rows linger and the stale-citing artifact is untouched.
    assert count == len(spans1) + len(spans2)
    node = db.list_synthesis_nodes(paths.state_db)[0]
    assert node["source_span_ids"] == [spans1[0]]
    # Defect: no API exists to enumerate/invalidate stale dependents.
    assert not [n for n in dir(db) if "invalidate" in n.lower()]


@pytest.mark.xfail(
    strict=True,
    reason="F7 reproduced: source edit leaves stale spans and stale-citing artifacts; "
    "assigned to program-2 (reconciliation/dependency closure, P2.2)",
)
def test_f7_oracle_source_edit_reconciles_stale_spans(vault) -> None:
    paths = vault
    spans1 = _store_section_spans(paths, "Original derivation of the bound.")
    spans2 = _store_section_spans(paths, "Edited derivation of the bound, corrected.")
    assert set(spans2).isdisjoint(spans1)
    with db.connect(paths.state_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM source_spans").fetchone()[0]
    assert count == len(spans2)  # stale rows reconciled away


# ---------------------------------------------------------------------------
# F8 — exact-name homonym merge and connected-component giant community
# ---------------------------------------------------------------------------

def test_f8_baseline_exact_name_merge_and_giant_component(vault) -> None:
    paths = vault
    span_a = db.upsert_source_span(
        paths.state_db, source_id=1, relpath=RELPATH, span_type="paragraph",
        content_hash="f8a", section_title="Power grids",
        text_preview="A transformer steps voltage up or down.",
    )
    span_b = db.upsert_source_span(
        paths.state_db, source_id=1, relpath=RELPATH, span_type="paragraph",
        content_hash="f8b", section_title="Deep learning",
        text_preview="The Transformer relies on self-attention.",
    )
    e1 = db.upsert_graph_entity(
        paths.state_db, canonical_name="Transformer", entity_type="concept",
        description="electrical device", source_span_ids=[span_a],
    )
    e2 = db.upsert_graph_entity(
        paths.state_db, canonical_name="Transformer", entity_type="concept",
        description="neural architecture", source_span_ids=[span_b],
    )
    # Defect: unrelated homonyms silently merged, span refs unioned.
    assert e1 == e2
    merged = db.find_graph_entities(paths.state_db, "Transformer", limit=5)
    assert len(merged) == 1
    assert set(merged[0]["source_span_ids"]) == {span_a, span_b}

    # Defect: one weak chain collapses everything into a giant community.
    ids = [
        db.upsert_graph_entity(
            paths.state_db, canonical_name=f"Concept {i}", entity_type="concept",
            source_span_ids=[span_a],
        )
        for i in range(10)
    ]
    for a, b in zip(ids, ids[1:]):
        db.upsert_graph_relation(
            paths.state_db, source_entity_id=a, target_entity_id=b,
            relation_type="related_to", confidence=0.05,
            source_span_ids=[span_a], assertion_source="system_infers",
        )
    plans = cr.detect_communities(paths.state_db)
    assert len(plans) == 1
    assert len(plans[0].entity_ids) == 10


@pytest.mark.xfail(
    strict=True,
    reason="F8 reproduced: exact-name merge and connected-component communities; "
    "assigned to program-2 (entity resolution / hierarchy, P2.4)",
)
def test_f8_oracle_homonyms_distinct_and_no_giant_component(vault) -> None:
    paths = vault
    span = db.upsert_source_span(
        paths.state_db, source_id=1, relpath=RELPATH, span_type="paragraph",
        content_hash="f8o", section_title="Mixed",
        text_preview="Mixed domains.",
    )
    e1 = db.upsert_graph_entity(
        paths.state_db, canonical_name="Transformer", entity_type="concept",
        description="electrical device", source_span_ids=[span],
    )
    e2 = db.upsert_graph_entity(
        paths.state_db, canonical_name="Transformer", entity_type="concept",
        description="neural architecture", source_span_ids=[span],
    )
    assert e1 != e2  # homonym protection (or explicit reviewable merge proposal)


# ---------------------------------------------------------------------------
# F9 — authored wikilinks never compiled into topology
# ---------------------------------------------------------------------------

def _counts(db_path: Path) -> tuple[int, int]:
    with db.connect(db_path) as conn:
        rel = conn.execute("SELECT COUNT(*) FROM graph_relations").fetchone()[0]
        dag = conn.execute("SELECT COUNT(*) FROM dag_edges").fetchone()[0]
    return rel, dag


def test_f9_baseline_authored_wikilinks_not_compiled(vault) -> None:
    paths = vault
    spans = _store_section_spans(
        paths,
        "This note links [[Residual Learning]] and [[Euler Method]] explicitly.",
    )
    assert spans
    # Defect: the strongest authored signal produces zero topology records.
    assert _counts(paths.state_db) == (0, 0)


@pytest.mark.xfail(
    strict=True,
    reason="F9 reproduced: pipeline never compiles authored links; "
    "assigned to program-2 (note-native IR, P2.1)",
)
def test_f9_oracle_authored_links_compiled_as_topology(vault) -> None:
    paths = vault
    _store_section_spans(
        paths,
        "This note links [[Residual Learning]] and [[Euler Method]] explicitly.",
    )
    rel, dag = _counts(paths.state_db)
    assert rel + dag > 0


# ---------------------------------------------------------------------------
# F10 — span evidence capped at 200-char preview
# ---------------------------------------------------------------------------

def test_f10_baseline_span_evidence_capped_at_preview(vault) -> None:
    paths = vault
    long_text = (
        "Lemma 4.2 bounds the spectral norm of the layer-wise Jacobian under "
        "residual reparameterization, with constants depending on depth. " * 8
        + "QED-MARKER-END"
    )
    assert len(long_text) > 200
    spans = _store_section_spans(paths, long_text, title="Proof")
    assert len(spans) == 1
    pack = evidence_mod.build_evidence(
        paths,
        QueryRequest(question="bound proof", mode="source-section", source_key="1"),
        "source-section",
    )
    assert pack.items
    item = pack.items[0]
    # Defect: pack evidence is the 200-char preview; the tail is unreachable.
    assert len(item.text) <= 200
    assert "QED-MARKER-END" not in item.text


def test_f10_oracle_full_span_text_retrievable(vault) -> None:
    # Plan B P6 / SEARCH_ENGINE §10.2: evidence hydrates full span text from the
    # registered source file. Materialize the source so hydration can read it.
    paths = vault
    long_text = "Spectral norm derivation. " * 20 + "QED-MARKER-END"
    src = paths.root / RELPATH
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(long_text, encoding="utf-8")
    _store_section_spans(paths, long_text, title="Proof")
    pack = evidence_mod.build_evidence(
        paths,
        QueryRequest(question="bound proof", mode="source-section", source_key="1"),
        "source-section",
    )
    assert any("QED-MARKER-END" in item.text for item in pack.items)
    # Full text is hydrated and flagged ok (not the silently-substituted preview).
    assert all(it.evidence_status == "ok" for it in pack.items if it.kind == "source_span")


# ---------------------------------------------------------------------------
# F11 — explore is a single prompt pass
# ---------------------------------------------------------------------------

class _ExploreFakeClient:
    model = "fake"

    def chat(self, messages, *, json_mode=False, temperature=0.3) -> str:
        text = "\n".join(m.content for m in messages)
        spans = [w for w in text.split() if w.startswith("SPAN-")]
        first = spans[0] if spans else "SPAN-00000000"
        return json.dumps({
            "followup_questions": ["How does residual learning relate to ODE solvers?"],
            "insight_candidates": [
                {
                    "statement": "Residual blocks approximate Euler steps.",
                    "rationale": "structural similarity",
                    "source_span_ids": [first],
                    "confidence": 0.5,
                    "needs_human_review": True,
                }
            ],
        })


def _seed_explore_graph(paths: cfg.WikiPaths) -> str:
    span = db.upsert_source_span(
        paths.state_db, source_id=1, relpath=RELPATH, span_type="paragraph",
        content_hash="f11", section_title="Intro",
        text_preview="Residual connections ease optimization.",
    )
    a = db.upsert_graph_entity(
        paths.state_db, canonical_name="residual learning", entity_type="concept",
        source_span_ids=[span],
    )
    b = db.upsert_graph_entity(
        paths.state_db, canonical_name="Euler discretization", entity_type="concept",
        source_span_ids=[span],
    )
    db.upsert_graph_relation(
        paths.state_db, source_entity_id=a, target_entity_id=b,
        relation_type="reinterpreted_as", confidence=0.8,
        source_span_ids=[span], assertion_source="system_infers",
    )
    db.upsert_community_report(
        paths.state_db, community_key="comm-1", title="Residual community",
        summary="ResNet eases optimization.", full_content="...",
        dependency_hash="d1", entity_ids=[a, b], source_span_ids=[span], rank=0.7,
    )
    return span


def test_f11_baseline_explore_single_pass(vault) -> None:
    paths = vault
    _seed_explore_graph(paths)
    res = QueryOrchestrator(paths, _ExploreFakeClient()).run(
        QueryRequest(question="what else connects residual learning?", mode="explore")
    )
    assert res.route == "explore"
    # Defect: exactly one expansion prompt; follow-ups rendered as text only.
    assert len(res.prompt_trace_ids) == 1
    assert "How does residual learning relate to ODE solvers?" in res.answer
    assert len(_all_traces(paths.state_db)) == 1


@pytest.mark.xfail(
    strict=True,
    reason="F11 reproduced: _run_explore never executes follow-ups; "
    "assigned to program-3 (bounded iterative retrieval, P3.3)",
)
def test_f11_oracle_explore_executes_followups_bounded(vault) -> None:
    paths = vault
    _seed_explore_graph(paths)
    res = QueryOrchestrator(paths, _ExploreFakeClient()).run(
        QueryRequest(question="what else connects residual learning?", mode="explore")
    )
    assert len(res.prompt_trace_ids) > 1  # follow-up retrieval actually executed


# ---------------------------------------------------------------------------
# F12 — MCP and plugin context shapes diverge
# ---------------------------------------------------------------------------

def test_f12_baseline_mcp_plugin_shapes_diverge(vault, degraded_search) -> None:
    paths = vault
    _seed_search_docs(paths.state_db)
    mcp_out = QueryOrchestrator(paths, _NoChatClient()).fetch_context(
        QueryRequest(question="residual optimization", mode="local")
    )
    plugin_out = plugin_api.curator_query(paths, question="residual optimization")
    assert plugin_out["ok"]
    assert plugin_out.get("fallback") == "l3_incomplete"
    # MCP surface: orchestrator pack with QTR identity and span provenance.
    assert "trace_id" in mcp_out and "evidence" in mcp_out and "source_span_ids" in mcp_out
    # Defect: the plugin surface shares none of that contract.
    assert "trace_id" not in plugin_out
    assert "evidence" not in plugin_out
    assert "source_span_ids" not in plugin_out


@pytest.mark.xfail(
    strict=True,
    reason="F12 reproduced: plugin_api.curator_query is an independent code path; "
    "assigned to program-3 (Plan F ContextService parity)",
)
def test_f12_oracle_normalized_pack_parity(vault, degraded_search) -> None:
    paths = vault
    _seed_search_docs(paths.state_db)
    plugin_out = plugin_api.curator_query(paths, question="residual optimization")
    assert {"route", "trace_id", "evidence", "source_span_ids"} <= set(plugin_out)


# ---------------------------------------------------------------------------
# F13 — active scenario validates retired architecture
# ---------------------------------------------------------------------------

_SCENARIO_PLAN = REPO_ROOT / "tests" / "scenarios" / "testbed_template" / "MASTER_PLAN.md"


def test_f13_scenario_targets_current_architecture() -> None:
    plan = _SCENARIO_PLAN.read_text(encoding="utf-8")
    script = _SCENARIO_PLAN.parent / "dialogues" / "verify_current_architecture.sh"
    script_text = script.read_text(encoding="utf-8")
    assert "EXH" not in plan
    assert "04_Exhibitions" not in plan
    for current_contract in (
        "CTX-*", "ATM-*", "CON-*", "SYN-*", "DB-Native Search",
        "Agent Reuse And Traceability", "Incremental Correctness",
    ):
        assert current_contract in plan
    for executable_gate in (
        "knowledge_units", "graph_entities", "community_reports",
        "synthesis_nodes", "source_spans", "query_traces",
        "retrieval_trace_json", "wiki update", "fetch_context",
        "test_rename_as_new_source_duplicates_every_span",
    ):
        assert executable_gate in script_text
