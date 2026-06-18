"""Plan F ContextService P1 contract fixtures and future implementation oracles."""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

from curator import config as cfg
from curator import db
from curator.retrieval.models import QueryRequest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "docs" / "specs" / "system_behavior" / "context_service_fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_context_fetch_fixture_pins_pack_contract() -> None:
    fixture = _load_fixture("context_fetch_pack.json")
    response = fixture["response"]
    assert fixture["contract_version"] == "1"
    assert fixture["operation"] == "context_fetch"
    assert re.match(r"^PACK-", response["pack_id"])
    assert re.match(r"^QTR-", response["trace_id"])
    assert re.match(r"^RTR-", response["retrieval_execution_id"])
    assert response["snapshot"]["snapshot_id"].startswith("SNAP-")
    assert response["budget"]["used_tokens"] <= response["budget"]["limit_tokens"]
    assert response["budget"]["reserved_tokens"] <= response["budget"]["limit_tokens"]
    assert response["budget"]["estimation_mode"] in {"tokenizer", "conservative"}
    assert response["coverage"]["sufficiency"] in {"sufficient", "partial", "insufficient"}
    assert response["items"], "fixture must include at least one evidence item"
    item = response["items"][0]
    required = {
        "item_id",
        "record_id",
        "record_hash",
        "kind",
        "layer",
        "summary",
        "authority_state",
        "truth_state",
        "freshness_state",
        "source_span_ids",
        "locator",
        "token_cost",
        "detail",
        "expansion_handle",
        "verification_handle",
    }
    assert required <= set(item)
    assert item["source_span_ids"], "source-supported item must preserve support spans"
    assert item["locator"]["locator_status"] in {
        "exact",
        "fallback_file",
        "fallback_source",
        "duplicate_anchor",
        "stale",
        "unavailable",
    }
    assert response["next"][0]["handle"].startswith("EXP-")


def test_snapshot_conflict_fixture_is_typed_and_non_mixing() -> None:
    fixture = _load_fixture("snapshot_conflict.json")
    response = fixture["response"]
    assert fixture["operation"] == "context_expand"
    assert response["ok"] is False
    assert response["error_type"] == "snapshot_conflict"
    assert response["expected_snapshot_id"] != response["current_snapshot_id"]
    assert response["resolution"] == "refetch_or_rebase"


def test_progressive_operation_fixtures_pin_p4_shapes() -> None:
    manifest = _load_fixture("context_manifest.json")["response"]
    assert manifest["operation"] == "context_manifest"
    assert manifest["snapshot"]["snapshot_id"].startswith("SNAP-")
    assert manifest["families"]
    assert manifest["next"][0]["handle"].startswith("EXP-")

    expand = _load_fixture("context_expand.json")["response"]
    assert expand["operation"] == "context_expand"
    assert expand["root_pack_id"].startswith("PACK-")
    assert expand["pack_id"].startswith("PACK-")
    assert expand["trace_id"].startswith("QTR-")
    assert expand["items"][0]["expansion_handle"].startswith("EXP-")

    verify = _load_fixture("context_verify.json")["response"]
    assert verify["operation"] == "context_verify"
    assert verify["pack_id"].startswith("PACK-")
    assert verify["trace_id"].startswith("QTR-")
    assert verify["item"]["verification_handle"].startswith("VER-")
    assert verify["source_span_ids"]


def test_feedback_fixture_is_append_only_by_contract() -> None:
    fixture = _load_fixture("context_feedback.json")
    request = fixture["request"]
    response = fixture["response"]
    assert fixture["operation"] == "context_feedback"
    assert request["feedback_type"] in {
        "relevant",
        "irrelevant",
        "incorrect",
        "stale",
        "insufficient",
        "duplicate",
        "new_insight",
        "correction",
        "promotion_request",
    }
    assert request["trace_id"].startswith("QTR-")
    assert request["pack_id"].startswith("PACK-")
    assert request["snapshot_id"].startswith("SNAP-")
    assert request["reviewed_source_span_ids"]
    assert response["feedback_id"].startswith("FBK-")
    assert response["ranking_or_truth_mutated"] is False


def test_context_service_module_exists_for_p2() -> None:
    mod = importlib.import_module("curator.context_service")
    assert hasattr(mod, "ContextService")


def _seed_context_vault(tmp_path: Path) -> tuple[cfg.WikiPaths, str]:
    root = tmp_path / "vault"
    paths = cfg.WikiPaths(root)
    db.init_db(paths.state_db)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES ('04_Resources/context.md', 'source-hash', 'md', 1, datetime('now'))"
        )
    span_id = db.upsert_source_span(
        paths.state_db,
        source_id=1,
        relpath="04_Resources/context.md",
        span_type="paragraph",
        content_hash="span-hash",
        section_title="Context",
        text_preview="Residual connections stabilize optimization.",
    )
    db.upsert_graph_entity(
        paths.state_db,
        canonical_name="residual connection",
        entity_type="concept",
        source_span_ids=[span_id],
    )
    return paths, span_id


def test_context_service_fetch_records_one_root_snapshot_and_ordered_actions(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths, span_id = _seed_context_vault(tmp_path)
    response = ContextService(paths).context_fetch(
        QueryRequest(question="residual connection", mode="local")
    )

    assert response["ok"] is True
    assert response["pack_id"].startswith("PACK-")
    assert response["trace_id"].startswith("QTR-")
    assert response["snapshot"]["snapshot_id"].startswith("SNAP-")
    assert response["retrieval_execution_id"].startswith("RTR-")
    assert span_id in response["source_span_ids"]
    assert response["actions"] == sorted(response["actions"], key=lambda action: action["order"])
    assert [action["action_type"] for action in response["actions"]] == [
        "retrieval",
        "pack_assembly",
        "budget",
    ]

    traces = db.list_query_traces(paths.state_db)
    assert [trace["trace_id"] for trace in traces] == [response["trace_id"]]
    trace = db.get_query_trace(paths.state_db, response["trace_id"])
    assert trace is not None
    context_trace = trace["retrieval_trace"]["context_service"]
    assert context_trace["pack_id"] == response["pack_id"]
    assert context_trace["snapshot"]["snapshot_id"] == response["snapshot"]["snapshot_id"]
    assert context_trace["actions"] == response["actions"]


def test_context_service_snapshot_id_is_stable_when_corpus_is_unchanged(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths, _span_id = _seed_context_vault(tmp_path)
    service = ContextService(paths)
    first = service.context_fetch(QueryRequest(question="residual connection", mode="local"))
    second = service.context_fetch(QueryRequest(question="residual connection", mode="local"))

    assert first["trace_id"] != second["trace_id"]
    assert first["snapshot"]["snapshot_id"] == second["snapshot"]["snapshot_id"]


def test_context_service_expected_snapshot_conflict_does_not_mix_epochs(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths, _span_id = _seed_context_vault(tmp_path)
    response = ContextService(paths).context_fetch(
        QueryRequest(question="residual connection", mode="local"),
        expected_snapshot_id="SNAP-stale",
    )

    assert response["ok"] is False
    assert response["error_type"] == "snapshot_conflict"
    assert response["expected_snapshot_id"] == "SNAP-stale"
    assert response["current_snapshot_id"].startswith("SNAP-")
    assert db.list_query_traces(paths.state_db) == []


def test_context_service_source_supported_items_resolve_locators(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths, span_id = _seed_context_vault(tmp_path)
    response = ContextService(paths).context_fetch(
        QueryRequest(question="residual connection", mode="local")
    )

    supported_items = [
        item for item in response["items"] if span_id in item["source_span_ids"]
    ]
    assert supported_items
    for item in supported_items:
        assert item["truth_state"] == "source_supported"
        assert item["locator"] is not None
        assert item["locator"]["source_id"] == 1
        assert item["locator"]["relpath"] == "04_Resources/context.md"
        assert item["locator"]["locator_status"] in {
            "exact",
            "fallback_file",
            "fallback_source",
        }


def _seed_budget_vault(tmp_path: Path) -> cfg.WikiPaths:
    paths, _span_id = _seed_context_vault(tmp_path)
    for idx in range(2, 7):
        span_id = db.upsert_source_span(
            paths.state_db,
            source_id=1,
            relpath="04_Resources/context.md",
            span_type="paragraph",
            content_hash=f"span-hash-{idx}",
            section_title="Context",
            text_preview=f"Context budget evidence {idx}.",
        )
        db.upsert_graph_entity(
            paths.state_db,
            canonical_name=f"context budget evidence {idx}",
            entity_type="concept",
            description="Compact grounded evidence for budget packing.",
            source_span_ids=[span_id],
        )
    return paths


def test_context_service_budget_truncation_is_explicit_and_trace_matches_pack(
    tmp_path: Path,
) -> None:
    from curator.context_service import ContextService

    paths = _seed_budget_vault(tmp_path)
    response = ContextService(paths).context_fetch(
        QueryRequest(question="context budget evidence", mode="local"),
        limit_tokens=20,
    )

    assert response["budget"]["used_tokens"] <= response["budget"]["limit_tokens"]
    assert response["budget"]["omitted_items"] > 0
    assert response["coverage"]["sufficiency"] == "partial"
    assert response["coverage"]["omitted_counts"]["budget"] == response["budget"]["omitted_items"]
    assert response["next"], "budget omissions must expose progressive expansion handles"
    assert response["next"][0]["handle"].startswith("EXP-")
    assert response["next"][0]["reason"] == "budget"

    trace = db.get_query_trace(paths.state_db, response["trace_id"])
    assert trace is not None
    assert [item["id"] for item in trace["evidence"]] == [
        item["record_id"] for item in response["items"]
    ]
    assert trace["source_span_ids"] == response["source_span_ids"]
    assert (
        trace["retrieval_trace"]["selection"]["omitted_counts"]["budget"]
        == response["budget"]["omitted_items"]
    )


def test_context_service_pack_order_is_deterministic_for_same_snapshot(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths = _seed_budget_vault(tmp_path)
    service = ContextService(paths)
    first = service.context_fetch(QueryRequest(question="context budget evidence", mode="local"))
    second = service.context_fetch(QueryRequest(question="context budget evidence", mode="local"))

    assert first["snapshot"]["snapshot_id"] == second["snapshot"]["snapshot_id"]
    assert [
        (item["record_id"], item["record_hash"], item["token_cost"])
        for item in first["items"]
    ] == [
        (item["record_id"], item["record_hash"], item["token_cost"])
        for item in second["items"]
    ]


def test_context_service_source_section_preserves_formula_code_citation_boundaries(
    tmp_path: Path,
) -> None:
    from curator.context_service import ContextService

    root = tmp_path / "vault"
    paths = cfg.WikiPaths(root)
    db.init_db(paths.state_db)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES ('04_Resources/boundaries.md', 'boundary-source', 'md', 1, datetime('now'))"
        )

    formula = "Euler identity: e^(i*pi) + 1 = 0."
    code = "def residual(x):\n    return x + f(x)"
    citation = "Citation boundary: Smith 2024, pp. 12-13."
    expected = [
        db.upsert_source_span(
            paths.state_db,
            source_id=1,
            relpath="04_Resources/boundaries.md",
            span_type="equation",
            content_hash="formula-span",
            section_title="Formula",
            start_char=0,
            end_char=40,
            text_preview=formula,
        ),
        db.upsert_source_span(
            paths.state_db,
            source_id=1,
            relpath="04_Resources/boundaries.md",
            span_type="code",
            content_hash="code-span",
            section_title="Code",
            start_char=41,
            end_char=80,
            text_preview=code,
        ),
        db.upsert_source_span(
            paths.state_db,
            source_id=1,
            relpath="04_Resources/boundaries.md",
            span_type="paragraph",
            content_hash="citation-span",
            section_title="Citation",
            start_char=81,
            end_char=125,
            text_preview=citation,
        ),
    ]

    response = ContextService(paths).context_fetch(
        QueryRequest(
            question="show source section boundaries",
            mode="source-section",
            source_key="04_Resources/boundaries.md",
        )
    )

    assert response["ok"] is True
    assert [item["record_id"] for item in response["items"]] == expected
    assert [item["detail"] for item in response["items"]] == [formula, code, citation]
    assert [item["source_span_ids"] for item in response["items"]] == [[sid] for sid in expected]
    assert all(item["truth_state"] == "source_supported" for item in response["items"])
    assert all(item["locator"]["locator_status"] == "exact" for item in response["items"])


def test_context_service_global_route_preserves_route_and_budget_omissions(
    tmp_path: Path,
) -> None:
    from curator.context_service import ContextService

    paths, span_id = _seed_context_vault(tmp_path)
    report_ids = [
        db.upsert_community_report(
            paths.state_db,
            community_key=f"community-{idx}",
            title=f"Global theme {idx}",
            summary="Global residual evidence " + ("detail " * 8),
            findings=[{"summary": f"Finding {idx}"}],
            source_span_ids=[span_id],
            rank=float(20 - idx),
        )
        for idx in range(12)
    ]

    response = ContextService(paths).context_fetch(
        QueryRequest(question="overall residual themes", mode="global"),
        limit_tokens=35,
    )

    assert response["ok"] is True
    assert response["route"] == "global"
    assert response["budget"]["used_tokens"] <= response["budget"]["limit_tokens"]
    assert response["coverage"]["sufficiency"] == "partial"
    assert response["coverage"]["omitted_counts"]["global_reports"] == 2
    assert response["coverage"]["omitted_counts"]["budget"] > 0
    assert set(response["community_report_ids"]) < set(report_ids)
    assert set(response["community_report_ids"]) == {
        item["record_id"] for item in response["items"]
    }

    trace = db.get_query_trace(paths.state_db, response["trace_id"])
    assert trace is not None
    assert trace["community_report_ids"] == response["community_report_ids"]
    assert trace["retrieval_trace"]["selection"]["omitted_counts"] == response[
        "coverage"
    ]["omitted_counts"]


def test_context_service_source_section_budget_omits_spans_without_mixing_trace(
    tmp_path: Path,
) -> None:
    from curator.context_service import ContextService

    root = tmp_path / "vault"
    paths = cfg.WikiPaths(root)
    db.init_db(paths.state_db)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES ('04_Resources/source-budget.md', 'source-budget', 'md', 1, datetime('now'))"
        )
    span_ids = [
        db.upsert_source_span(
            paths.state_db,
            source_id=1,
            relpath="04_Resources/source-budget.md",
            span_type="paragraph",
            content_hash=f"source-budget-span-{idx}",
            section_title=f"Budget {idx}",
            start_char=idx * 10,
            end_char=idx * 10 + 9,
            text_preview=f"Source section budget item {idx}.",
        )
        for idx in range(6)
    ]

    response = ContextService(paths).context_fetch(
        QueryRequest(
            question="source budget",
            mode="source-section",
            source_key="04_Resources/source-budget.md",
        ),
        limit_tokens=20,
    )

    assert response["ok"] is True
    assert response["route"] == "source-section"
    assert response["budget"]["used_tokens"] <= response["budget"]["limit_tokens"]
    assert response["coverage"]["omitted_counts"]["budget"] > 0
    assert response["source_span_ids"] == [
        span_id for item in response["items"] for span_id in item["source_span_ids"]
    ]
    assert response["source_span_ids"] == span_ids[: len(response["items"])]
    assert set(response["source_span_ids"]) < set(span_ids)
    assert {action["item_id"] for action in response["next"]}.isdisjoint(
        {item["record_id"] for item in response["items"]}
    )

    trace = db.get_query_trace(paths.state_db, response["trace_id"])
    assert trace is not None
    assert trace["source_span_ids"] == response["source_span_ids"]


def test_context_service_cjk_budget_estimator_is_conservative() -> None:
    from curator.context_service import _estimate_tokens

    korean = "수" * 12_000
    english = "a" * 12_000

    assert _estimate_tokens(korean) >= len(korean)
    assert _estimate_tokens(korean) > (len(korean) + 3) // 4
    assert _estimate_tokens(english) >= (len(english) + 3) // 4


def test_context_service_selected_refs_preserve_pack_order() -> None:
    from curator.context_service import _selected_refs_from_payloads
    from curator.retrieval.models import EvidenceItem
    from curator.context_service import _selected_refs

    items = [
        EvidenceItem(id="item-a", kind="source_span", title="A", text="A", source_span_ids=["SPAN-b"]),
        EvidenceItem(id="item-b", kind="source_span", title="B", text="B", source_span_ids=["SPAN-a"]),
        EvidenceItem(
            id="item-c",
            kind="source_span",
            title="C",
            text="C",
            source_span_ids=["SPAN-b", "SPAN-c"],
        ),
    ]
    payloads = [
        {"source_span_ids": ["SPAN-b"]},
        {"source_span_ids": ["SPAN-a"]},
        {"source_span_ids": ["SPAN-b", "SPAN-c"]},
    ]

    assert _selected_refs(items)["source_span_ids"] == ["SPAN-b", "SPAN-a", "SPAN-c"]
    assert _selected_refs_from_payloads(payloads)["source_span_ids"] == [
        "SPAN-b",
        "SPAN-a",
        "SPAN-c",
    ]


def test_context_service_marks_orphaned_support_without_false_truth_state(
    tmp_path: Path,
) -> None:
    from curator.context_service import ContextService

    root = tmp_path / "vault"
    paths = cfg.WikiPaths(root)
    db.init_db(paths.state_db)
    db.upsert_graph_entity(
        paths.state_db,
        canonical_name="orphaned concept",
        entity_type="concept",
        source_span_ids=["SPAN-missing"],
    )

    response = ContextService(paths).context_fetch(
        QueryRequest(question="orphaned concept", mode="local")
    )

    assert response["ok"] is True
    item = next(item for item in response["items"] if item["source_span_ids"] == ["SPAN-missing"])
    assert item["truth_state"] == "orphaned_support"
    assert item["freshness_state"] == "stale"
    assert item["locator"]["locator_status"] == "unavailable"


def test_context_expand_reports_budget_refusals_without_requeueing_same_handles(
    tmp_path: Path,
) -> None:
    from curator.context_service import ContextService

    paths = _seed_budget_vault(tmp_path)
    service = ContextService(paths)
    pack = service.context_fetch(
        QueryRequest(question="context budget evidence", mode="local"),
        limit_tokens=20,
    )
    handle = pack["next"][0]["handle"]

    response = service.context_expand(
        pack_id=pack["pack_id"],
        handles=[handle],
        expected_snapshot_id=pack["snapshot"]["snapshot_id"],
        limit_tokens=1,
    )

    assert response["ok"] is True
    assert response["items"] == []
    assert response["next"] == []
    assert response["expansion_refused"] == [
        {
            "handle": handle,
            "reason": "budget_exhausted",
            "item_id": pack["next"][0]["item_id"],
            "snapshot_id": pack["snapshot"]["snapshot_id"],
            "retry": "increase_limit_tokens_or_refetch",
        }
    ]


def test_context_expand_consumes_successful_handles_once(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths = _seed_budget_vault(tmp_path)
    service = ContextService(paths)
    pack = service.context_fetch(
        QueryRequest(question="context budget evidence", mode="local"),
        limit_tokens=20,
    )
    handle = pack["next"][0]["handle"]

    first = service.context_expand(
        pack_id=pack["pack_id"],
        handles=[handle],
        expected_snapshot_id=pack["snapshot"]["snapshot_id"],
        limit_tokens=20,
    )
    second = service.context_expand(
        pack_id=pack["pack_id"],
        handles=[handle],
        expected_snapshot_id=pack["snapshot"]["snapshot_id"],
        limit_tokens=20,
    )

    assert first["ok"] is True
    assert first["items"]
    assert second["ok"] is True
    assert second["items"] == []
    assert second["warnings"] == ["expansion handles already selected"]
    trace = db.get_query_trace(paths.state_db, pack["trace_id"])
    assert trace is not None
    actions = trace["retrieval_trace"]["context_service"]["actions"]
    expansion_actions = [
        action for action in actions if action["action_type"] == "expansion"
    ]
    assert len(expansion_actions) == 1


def test_context_service_progressive_operations_exist_for_p4() -> None:
    from curator.context_service import ContextService

    assert hasattr(ContextService, "context_manifest")
    assert hasattr(ContextService, "context_expand")
    assert hasattr(ContextService, "context_verify")


def test_context_manifest_reports_bounded_context_families(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths, _span_id = _seed_context_vault(tmp_path)
    response = ContextService(paths).context_manifest(limit_families=4)

    assert response["ok"] is True
    assert response["operation"] == "context_manifest"
    assert response["snapshot"]["snapshot_id"].startswith("SNAP-")
    assert [family["family"] for family in response["families"]] == [
        "sources",
        "source_spans",
        "entities",
        "community_reports",
    ]
    assert response["families"][0]["count"] == 1
    assert response["next"][0]["handle"].startswith("EXP-")


def test_context_expand_rejects_stale_snapshot_without_mutating_trace(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths = _seed_budget_vault(tmp_path)
    service = ContextService(paths)
    pack = service.context_fetch(
        QueryRequest(question="context budget evidence", mode="local"),
        limit_tokens=20,
    )
    before = db.get_query_trace(paths.state_db, pack["trace_id"])
    assert before is not None

    response = service.context_expand(
        pack_id=pack["pack_id"],
        handles=[pack["next"][0]["handle"]],
        expected_snapshot_id="SNAP-stale",
    )

    assert response["ok"] is False
    assert response["error_type"] == "snapshot_conflict"
    assert response["expected_snapshot_id"] == "SNAP-stale"
    assert response["current_snapshot_id"] == pack["snapshot"]["snapshot_id"]
    after = db.get_query_trace(paths.state_db, pack["trace_id"])
    assert after == before


def test_context_expand_returns_bound_items_and_appends_child_action(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths = _seed_budget_vault(tmp_path)
    service = ContextService(paths)
    pack = service.context_fetch(
        QueryRequest(question="context budget evidence", mode="local"),
        limit_tokens=20,
    )
    handle = pack["next"][0]["handle"]

    response = service.context_expand(
        pack_id=pack["pack_id"],
        handles=[handle],
        expected_snapshot_id=pack["snapshot"]["snapshot_id"],
        limit_tokens=20,
    )

    assert response["ok"] is True
    assert response["operation"] == "context_expand"
    assert response["pack_id"].startswith("PACK-")
    assert response["root_pack_id"] == pack["pack_id"]
    assert response["trace_id"] == pack["trace_id"]
    assert response["snapshot"]["snapshot_id"] == pack["snapshot"]["snapshot_id"]
    assert response["items"]
    assert response["items"][0]["expansion_handle"] == handle
    assert response["budget"]["used_tokens"] <= response["budget"]["limit_tokens"]

    trace = db.get_query_trace(paths.state_db, pack["trace_id"])
    assert trace is not None
    actions = trace["retrieval_trace"]["context_service"]["actions"]
    assert actions[-1]["action_type"] == "expansion"
    assert actions[-1]["child_id"] == response["pack_id"]


def test_context_verify_resolves_exact_support_and_appends_child_action(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths, span_id = _seed_context_vault(tmp_path)
    service = ContextService(paths)
    pack = service.context_fetch(QueryRequest(question="residual connection", mode="local"))
    item = next(item for item in pack["items"] if span_id in item["source_span_ids"])

    response = service.context_verify(
        pack_id=pack["pack_id"],
        verification_handle=item["verification_handle"],
        expected_snapshot_id=pack["snapshot"]["snapshot_id"],
    )

    assert response["ok"] is True
    assert response["operation"] == "context_verify"
    assert response["trace_id"] == pack["trace_id"]
    assert response["pack_id"] == pack["pack_id"]
    assert response["item"]["record_id"] == item["record_id"]
    assert response["source_span_ids"] == item["source_span_ids"]
    assert response["source_span_ids"] == [span_id]
    assert response["locator"]["locator_status"] in {"exact", "fallback_file"}
    assert response["contradictions"] == []

    trace = db.get_query_trace(paths.state_db, pack["trace_id"])
    assert trace is not None
    actions = trace["retrieval_trace"]["context_service"]["actions"]
    assert actions[-1]["action_type"] == "verification"
    assert actions[-1]["child_id"] == item["verification_handle"]
