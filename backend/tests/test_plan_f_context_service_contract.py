"""Plan F ContextService P1 contract fixtures and future implementation oracles."""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

import pytest

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


@pytest.mark.parametrize("surface", ["context_service", "query_orchestrator"])
def test_existing_invalid_workspace_policy_fails_before_retrieval_or_trace(
    tmp_path: Path, surface: str
) -> None:
    from curator.context_service import ContextService
    from curator.retrieval import QueryOrchestrator

    paths, _span_id = _seed_context_vault(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "curate.yml").write_text(
        'project: "broken"\nreasoning:\n  allowed_modes: [bogus]\n',
        encoding="utf-8",
    )
    request = QueryRequest(
        question="residual connection",
        mode="local",
        workspace_path=str(workspace),
    )

    with pytest.raises(ValueError, match="allowed_modes"):
        if surface == "context_service":
            ContextService(paths).context_fetch(request)
        else:
            QueryOrchestrator(paths, client=None).fetch_context(request)

    assert db.list_query_traces(paths.state_db) == []


def test_context_service_snapshot_id_is_stable_when_corpus_is_unchanged(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths, _span_id = _seed_context_vault(tmp_path)
    service = ContextService(paths)
    first = service.context_fetch(QueryRequest(question="residual connection", mode="local"))
    second = service.context_fetch(QueryRequest(question="residual connection", mode="local"))

    assert first["trace_id"] != second["trace_id"]
    assert first["snapshot"]["snapshot_id"] == second["snapshot"]["snapshot_id"]


def test_context_service_source_epoch_is_compact_and_content_sensitive(tmp_path: Path) -> None:
    from curator import context_service as cs

    paths, _span_id = _seed_context_vault(tmp_path)
    first_epoch = cs._source_epoch(paths)  # noqa: SLF001 - contract oracle for compact epoch

    assert first_epoch["source_count"] == 1
    assert first_epoch["span_count"] == 1
    assert "sources" not in first_epoch
    assert "spans" not in first_epoch
    assert first_epoch["source_content_hash"]
    assert first_epoch["span_content_hash"]

    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE source_spans SET content_hash = ? WHERE id = ?",
            ("span-hash-updated", _span_id),
        )
    second_epoch = cs._source_epoch(paths)  # noqa: SLF001 - contract oracle for compact epoch

    assert second_epoch["source_count"] == first_epoch["source_count"]
    assert second_epoch["span_count"] == first_epoch["span_count"]
    assert second_epoch["source_content_hash"] == first_epoch["source_content_hash"]
    assert second_epoch["span_content_hash"] != first_epoch["span_content_hash"]


def test_context_fetch_persists_query_trace_once(tmp_path: Path, monkeypatch) -> None:
    from curator import context_service as cs

    paths, _span_id = _seed_context_vault(tmp_path)
    calls = 0
    real_insert = cs.db.insert_query_trace

    def counted_insert(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_insert(*args, **kwargs)

    monkeypatch.setattr(cs.db, "insert_query_trace", counted_insert)
    response = cs.ContextService(paths).context_fetch(
        QueryRequest(question="residual connection", mode="local")
    )

    assert response["ok"] is True
    assert calls == 1
    assert db.get_query_trace(paths.state_db, response["trace_id"]) is not None


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

    # A budget large enough for the cumulative pack so the first expansion lands.
    first = service.context_expand(
        pack_id=pack["pack_id"],
        handles=[handle],
        expected_snapshot_id=pack["snapshot"]["snapshot_id"],
        limit_tokens=400,
    )
    second = service.context_expand(
        pack_id=pack["pack_id"],
        handles=[handle],
        expected_snapshot_id=pack["snapshot"]["snapshot_id"],
        limit_tokens=400,
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

    # Expand with a larger budget so the cumulative pack (already-selected fetch
    # items + this expansion) fits — the realistic `increase_limit_tokens` retry.
    response = service.context_expand(
        pack_id=pack["pack_id"],
        handles=[handle],
        expected_snapshot_id=pack["snapshot"]["snapshot_id"],
        limit_tokens=400,
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


def test_budget_payloads_accounts_for_already_used_tokens() -> None:
    from curator import context_service as cs

    items = [{"token_cost": 100, "expansion_handle": "EXP-a"}]
    # Fresh budget: the 100-token item fits under a 200-limit (minus reserve).
    selected, omitted, budget = cs._budget_payloads(items, limit_tokens=200)
    assert [i["expansion_handle"] for i in selected] == ["EXP-a"]
    assert omitted == []

    # With the budget already (nearly) consumed by prior selections, the SAME item
    # no longer fits — it is omitted instead of granted a fresh full budget.
    selected2, omitted2, budget2 = cs._budget_payloads(
        items, limit_tokens=200, already_used=190
    )
    assert selected2 == []
    assert [i["expansion_handle"] for i in omitted2] == ["EXP-a"]
    assert budget2["used_tokens"] == 190  # seeded, not reset to 0


def test_budget_payloads_handles_null_detail_without_charging_literal_none() -> None:
    from curator import context_service as cs

    # detail explicitly None (valid JSON) must cost 1 token, not the 4-char "None".
    assert cs._payload_token_cost({"detail": None}) == 1
    assert cs._payload_token_cost({"detail": ""}) == 1


def test_context_expand_keeps_cumulative_pack_within_budget(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths = _seed_budget_vault(tmp_path)
    service = ContextService(paths)
    pack = service.context_fetch(
        QueryRequest(question="context budget evidence", mode="local"),
        limit_tokens=20,
    )
    already_used = pack["budget"]["used_tokens"]
    handle = pack["next"][0]["handle"]

    response = service.context_expand(
        pack_id=pack["pack_id"],
        handles=[handle],
        expected_snapshot_id=pack["snapshot"]["snapshot_id"],
        limit_tokens=20,
    )

    # The expansion budget is seeded with the fetch's already-used tokens, so the
    # cumulative selected set never exceeds limit_tokens (no fresh full budget).
    assert response["ok"] is True
    assert response["budget"]["used_tokens"] >= already_used
    assert response["budget"]["used_tokens"] <= response["budget"]["limit_tokens"]


def test_context_expand_finds_pack_without_recent_trace_scan(tmp_path: Path, monkeypatch) -> None:
    from curator import context_service as cs

    paths = _seed_budget_vault(tmp_path)
    service = cs.ContextService(paths)
    pack = service.context_fetch(
        QueryRequest(question="context budget evidence", mode="local"),
        limit_tokens=20,
    )

    def fail_scan(*_args, **_kwargs):
        raise AssertionError("context_expand must not scan recent query traces")

    monkeypatch.setattr(cs.db, "list_query_traces", fail_scan)
    response = service.context_expand(
        pack_id=pack["pack_id"],
        handles=[pack["next"][0]["handle"]],
        expected_snapshot_id=pack["snapshot"]["snapshot_id"],
        limit_tokens=20,
    )

    assert response["ok"] is True
    assert response["trace_id"] == pack["trace_id"]


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


def test_context_verify_finds_pack_without_recent_trace_scan(tmp_path: Path, monkeypatch) -> None:
    from curator import context_service as cs

    paths, span_id = _seed_context_vault(tmp_path)
    service = cs.ContextService(paths)
    pack = service.context_fetch(QueryRequest(question="residual connection", mode="local"))
    item = next(item for item in pack["items"] if span_id in item["source_span_ids"])

    def fail_scan(*_args, **_kwargs):
        raise AssertionError("context_verify must not scan recent query traces")

    monkeypatch.setattr(cs.db, "list_query_traces", fail_scan)
    response = service.context_verify(
        pack_id=pack["pack_id"],
        verification_handle=item["verification_handle"],
        expected_snapshot_id=pack["snapshot"]["snapshot_id"],
    )

    assert response["ok"] is True
    assert response["trace_id"] == pack["trace_id"]


# ---------------------------------------------------------------------------
# P7 — Feedback And Promotion Lineage (SYSTEM_BEHAVIOR §31.6, SCHEMA §23.2 FBK-*)
# ---------------------------------------------------------------------------

_FEEDBACK_TYPES = (
    "relevant",
    "irrelevant",
    "incorrect",
    "stale",
    "insufficient",
    "duplicate",
    "new_insight",
    "correction",
    "promotion_request",
)


def test_context_service_feedback_operation_exists_for_p7() -> None:
    from curator.context_service import ContextService

    assert hasattr(ContextService, "context_feedback")


def test_context_feedback_records_append_only_event_without_mutation(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths, span_id = _seed_context_vault(tmp_path)
    service = ContextService(paths)
    pack = service.context_fetch(QueryRequest(question="residual connection", mode="local"))
    item = next(item for item in pack["items"] if span_id in item["source_span_ids"])
    trace_before = db.get_query_trace(paths.state_db, pack["trace_id"])
    assert trace_before is not None
    selected_before = trace_before["retrieval_trace"]["context_service"]["selected_items"]

    response = service.context_feedback(
        trace_id=pack["trace_id"],
        pack_id=pack["pack_id"],
        feedback_type="incorrect",
        statement="The cited paragraph does not support this claim.",
        client="obsidian",
        purpose="ground",
        target={"item_id": item["record_id"], "record_id": span_id, "claim_id": None},
        reviewed_source_span_ids=[span_id],
    )

    assert response["ok"] is True
    assert response["operation"] == "context_feedback"
    assert response["feedback_id"].startswith("FBK-")
    assert response["feedback_type"] == "incorrect"
    assert response["trace_id"] == pack["trace_id"]
    assert response["pack_id"] == pack["pack_id"]
    assert response["snapshot"]["snapshot_id"] == pack["snapshot"]["snapshot_id"]
    assert response["review_status"] == "pending"
    # Quarantine guarantee: feedback never mutates ranking or truth.
    assert response["ranking_or_truth_mutated"] is False

    trace = db.get_query_trace(paths.state_db, pack["trace_id"])
    assert trace is not None
    context = trace["retrieval_trace"]["context_service"]
    event_action = context["actions"][-1]
    assert event_action["action_type"] == "feedback"
    assert event_action["child_id"] == response["feedback_id"]
    event = event_action["payload"]
    assert event["feedback_type"] == "incorrect"
    assert event["pack_id"] == pack["pack_id"]
    assert event["snapshot_id"] == pack["snapshot"]["snapshot_id"]
    assert event["client"] == "obsidian"
    assert event["purpose"] == "ground"
    assert event["target"] == {"item_id": item["record_id"], "record_id": span_id, "claim_id": None}
    assert event["reviewed_source_span_ids"] == [span_id]
    assert event["statement"]
    # Lineage fields exist but are unresolved until a reviewed policy applies them.
    assert event["classification"] is None
    assert event["review_actor"] is None
    assert event["review_time"] is None
    assert event["resulting_lineage"] == {
        "insight_candidate_id": None,
        "promotion_relpath": None,
        "correction_node_ids": [],
    }
    # Source-supported selected evidence is untouched by feedback.
    assert context["selected_items"] == selected_before


def test_context_feedback_rejects_unknown_type_without_appending(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths, _ = _seed_context_vault(tmp_path)
    service = ContextService(paths)
    pack = service.context_fetch(QueryRequest(question="residual connection", mode="local"))
    before = db.get_query_trace(paths.state_db, pack["trace_id"])
    assert before is not None
    actions_before = len(before["retrieval_trace"]["context_service"]["actions"])

    response = service.context_feedback(
        trace_id=pack["trace_id"],
        pack_id=pack["pack_id"],
        feedback_type="not_a_real_type",
        statement="bogus",
    )

    assert response["ok"] is False
    assert response["error_type"] == "invalid_feedback_type"
    after = db.get_query_trace(paths.state_db, pack["trace_id"])
    assert after is not None
    assert len(after["retrieval_trace"]["context_service"]["actions"]) == actions_before


def test_context_feedback_unknown_pack_is_reported(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths, _ = _seed_context_vault(tmp_path)
    response = ContextService(paths).context_feedback(
        trace_id="QTR-does-not-exist",
        pack_id="PACK-does-not-exist",
        feedback_type="relevant",
        statement="n/a",
    )
    assert response["ok"] is False
    assert response["error_type"] == "pack_not_found"


def test_context_feedback_is_append_only_across_repeated_events(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths, span_id = _seed_context_vault(tmp_path)
    service = ContextService(paths)
    pack = service.context_fetch(QueryRequest(question="residual connection", mode="local"))

    first = service.context_feedback(
        trace_id=pack["trace_id"],
        pack_id=pack["pack_id"],
        feedback_type="relevant",
        statement="useful evidence",
    )
    second = service.context_feedback(
        trace_id=pack["trace_id"],
        pack_id=pack["pack_id"],
        feedback_type="stale",
        statement="evidence is now stale",
    )

    assert first["feedback_id"] != second["feedback_id"]
    trace = db.get_query_trace(paths.state_db, pack["trace_id"])
    assert trace is not None
    feedback_actions = [
        a
        for a in trace["retrieval_trace"]["context_service"]["actions"]
        if a["action_type"] == "feedback"
    ]
    assert [a["child_id"] for a in feedback_actions] == [
        first["feedback_id"],
        second["feedback_id"],
    ]
    orders = [a["order"] for a in feedback_actions]
    assert orders == sorted(orders)
    assert all(t in _FEEDBACK_TYPES for t in ("relevant", "stale"))


def test_context_feedback_new_insight_creates_provisional_candidate(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths, span_id = _seed_context_vault(tmp_path)
    service = ContextService(paths)
    pack = service.context_fetch(QueryRequest(question="residual connection", mode="local"))

    response = service.context_feedback(
        trace_id=pack["trace_id"],
        pack_id=pack["pack_id"],
        feedback_type="new_insight",
        statement="Residual connections also stabilize very deep training.",
        client="obsidian",
        purpose="discover",
        reviewed_source_span_ids=[span_id],
    )

    assert response["ok"] is True
    # Quarantine holds: a provisional candidate for review is not a truth/ranking change.
    assert response["ranking_or_truth_mutated"] is False
    candidate_id = response["resulting_lineage"]["insight_candidate_id"]
    assert candidate_id is not None
    assert candidate_id.startswith("INS-")

    candidate = db.get_insight_candidate(paths.state_db, candidate_id)
    assert candidate is not None
    # Provisional: pending review, never applied to source/ranking.
    assert candidate["status"] == "pending"
    assert candidate["classification"] == "derived_insight"
    assert candidate["statement"] == "Residual connections also stabilize very deep training."

    # The stored feedback event carries the same lineage.
    trace = db.get_query_trace(paths.state_db, pack["trace_id"])
    assert trace is not None
    event = trace["retrieval_trace"]["context_service"]["actions"][-1]["payload"]
    assert event["resulting_lineage"]["insight_candidate_id"] == candidate_id


def test_context_feedback_non_insight_type_creates_no_candidate(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths, _ = _seed_context_vault(tmp_path)
    service = ContextService(paths)
    pack = service.context_fetch(QueryRequest(question="residual connection", mode="local"))

    response = service.context_feedback(
        trace_id=pack["trace_id"],
        pack_id=pack["pack_id"],
        feedback_type="incorrect",
        statement="The cited span does not support this.",
    )

    assert response["resulting_lineage"]["insight_candidate_id"] is None
    assert db.list_insight_candidates(paths.state_db) == []


def test_context_feedback_uses_explicit_trace_lookup_not_recent_scan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from curator.context_service import ContextService
    from curator import context_service as context_service_module

    paths, _ = _seed_context_vault(tmp_path)
    service = ContextService(paths)
    pack = service.context_fetch(QueryRequest(question="residual connection", mode="local"))

    def fail_scan(*_args, **_kwargs):
        raise AssertionError("context_feedback must not scan recent query traces")

    monkeypatch.setattr(context_service_module.db, "list_query_traces", fail_scan)
    response = service.context_feedback(
        trace_id=pack["trace_id"],
        pack_id=pack["pack_id"],
        feedback_type="relevant",
        statement="This evidence is useful.",
    )

    assert response["ok"] is True
    assert response["trace_id"] == pack["trace_id"]


def test_context_feedback_rejects_pack_not_owned_by_trace_without_appending(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths, _ = _seed_context_vault(tmp_path)
    service = ContextService(paths)
    first_pack = service.context_fetch(QueryRequest(question="residual connection", mode="local"))
    second_pack = service.context_fetch(QueryRequest(question="residual connection", mode="local"))
    before = db.get_query_trace(paths.state_db, first_pack["trace_id"])
    assert before is not None
    actions_before = len(before["retrieval_trace"]["context_service"]["actions"])

    response = service.context_feedback(
        trace_id=first_pack["trace_id"],
        pack_id=second_pack["pack_id"],
        feedback_type="relevant",
        statement="wrong trace/pack pair",
    )

    assert response["ok"] is False
    assert response["error_type"] == "pack_not_found"
    assert response["trace_id"] == first_pack["trace_id"]
    assert response["pack_id"] == second_pack["pack_id"]
    after = db.get_query_trace(paths.state_db, first_pack["trace_id"])
    assert after is not None
    assert len(after["retrieval_trace"]["context_service"]["actions"]) == actions_before


def test_context_feedback_new_insight_drops_empty_record_id(tmp_path: Path) -> None:
    from curator.context_service import ContextService

    paths, span_id = _seed_context_vault(tmp_path)
    service = ContextService(paths)
    pack = service.context_fetch(QueryRequest(question="residual connection", mode="local"))

    response = service.context_feedback(
        trace_id=pack["trace_id"],
        pack_id=pack["pack_id"],
        feedback_type="new_insight",
        statement="Residual connections are also a stability prior.",
        target={"item_id": "", "record_id": "", "claim_id": None},
        reviewed_source_span_ids=[span_id],
    )

    assert response["ok"] is True
    candidate_id = response["resulting_lineage"]["insight_candidate_id"]
    candidate = db.get_insight_candidate(paths.state_db, candidate_id)
    assert candidate is not None
    assert candidate["affected_node_ids"] == []


# ---------------------------------------------------------------------------
# P8 — Plan-A Route Admission And Context-Service Integration
# ---------------------------------------------------------------------------


def test_admit_route_gates_experimental_and_disabled_routes() -> None:
    from curator import context_service as cs

    # Plan-A-gated, pack-integrated routes pass through untouched — `explore` is
    # now admitted into the ContextService pack path (SYSTEM_BEHAVIOR §31.8).
    assert cs._admit_route("local", "r", frozenset()) == ("local", "r", None)
    assert cs._admit_route("global", "r", frozenset()) == ("global", "r", None)
    assert cs._admit_route("source-section", "r", frozenset()) == (
        "source-section",
        "r",
        None,
    )
    assert cs._admit_route("explore", "discovery", frozenset()) == (
        "explore",
        "discovery",
        None,
    )

    # A genuinely unknown route still degrades to the local baseline.
    served, reason, downgraded = cs._admit_route("teleport", "weird", frozenset())
    assert served == "local"
    assert downgraded == "teleport"
    assert "not admitted" in reason

    # Admitted experimental routes can be rolled back independently -> degrade.
    for experimental in ("global", "explore"):
        served, reason, downgraded = cs._admit_route(
            experimental, "broad", frozenset({experimental})
        )
        assert served == "local"
        assert downgraded == experimental
        assert "disabled (rollback)" in reason

    # Safe baseline routes are never disabled even if named.
    assert cs._admit_route("local", "r", frozenset({"local"})) == ("local", "r", None)


def test_disabled_routes_parsed_from_env(monkeypatch) -> None:
    from curator import context_service as cs

    monkeypatch.setenv("INCURATOR_DISABLED_ROUTES", " global , explore ,")
    paths = cfg.WikiPaths(Path("/tmp/does-not-matter"))
    service = cs.ContextService(paths)
    assert service.disabled_routes == frozenset({"global", "explore"})


def test_context_fetch_admits_explore_route(tmp_path: Path, monkeypatch) -> None:
    from curator import context_service as cs
    from curator.retrieval import router

    paths, span_id = _seed_context_vault(tmp_path)
    monkeypatch.setattr(router, "choose_route", lambda *a, **k: ("explore", "discovery signal"))

    response = cs.ContextService(paths).context_fetch(
        QueryRequest(question="residual connection", mode="auto")
    )

    # explore now grounds on the unified pack path (SYSTEM_BEHAVIOR §31.8): it is
    # served as explore, not degraded, and exposed in the admitted set.
    assert response["ok"] is True
    assert response["route"] == "explore"
    admission = response["route_admission"]
    assert admission["requested"] == "explore"
    assert admission["served"] == "explore"
    assert admission["downgraded"] is False
    assert "explore" in admission["admitted_routes"]

    # Still exactly one RTR retrieval execution under the one QTR root — admission
    # changes which route runs, never how many.
    retrieval_actions = [a for a in response["actions"] if a["action_type"] == "retrieval"]
    assert len(retrieval_actions) == 1
    assert retrieval_actions[0]["child_id"] == response["retrieval_execution_id"]
    traces = db.list_query_traces(paths.state_db)
    assert [t["trace_id"] for t in traces] == [response["trace_id"]]
    # The explore pack resolves real evidence through the normalized path.
    assert span_id in response["source_span_ids"]


def test_context_fetch_can_disable_explore_route_for_rollback(tmp_path: Path, monkeypatch) -> None:
    from curator import context_service as cs
    from curator.retrieval import router

    paths, span_id = _seed_context_vault(tmp_path)
    monkeypatch.setattr(router, "choose_route", lambda *a, **k: ("explore", "discovery signal"))

    # explore is admitted but NOT a safe baseline: it can be rolled back to local.
    service = cs.ContextService(paths, disabled_routes={"explore"})
    response = service.context_fetch(QueryRequest(question="residual connection", mode="auto"))

    assert response["route"] == "local"
    admission = response["route_admission"]
    assert admission["requested"] == "explore"
    assert admission["served"] == "local"
    assert admission["downgraded"] is True
    assert span_id in response["source_span_ids"]


def test_context_fetch_route_rollback_degrades_disabled_route(tmp_path: Path, monkeypatch) -> None:
    from curator import context_service as cs
    from curator.retrieval import router

    paths, _ = _seed_context_vault(tmp_path)
    monkeypatch.setattr(router, "choose_route", lambda *a, **k: ("global", "broad-synthesis signal"))

    service = cs.ContextService(paths, disabled_routes={"global"})
    response = service.context_fetch(QueryRequest(question="overview of the field", mode="auto"))

    assert response["route"] == "local"
    admission = response["route_admission"]
    assert admission["requested"] == "global"
    assert admission["served"] == "local"
    assert admission["disabled_routes"] == ["global"]
    # Admission is persisted on the root trace for inspection.
    trace = db.get_query_trace(paths.state_db, response["trace_id"])
    assert trace is not None
    assert trace["retrieval_trace"]["context_service"]["route_admission"]["requested"] == "global"


def test_context_fetch_admits_plan_a_route_without_downgrade(tmp_path: Path) -> None:
    from curator import context_service as cs

    paths, _ = _seed_context_vault(tmp_path)
    # Default seed routes to the admitted local route; it is served unchanged.
    response = cs.ContextService(paths).context_fetch(
        QueryRequest(question="residual connection", mode="local")
    )
    assert response["route"] == "local"
    assert response["route_admission"]["downgraded"] is False
    assert response["route_admission"]["requested"] == "local"


def test_context_expand_admits_a_next_handle_at_the_budget_that_produced_it(
    tmp_path: Path,
) -> None:
    """§31.1: an expanded item is admitted if it fits within ``limit_tokens``.

    Regression for the double-subtracted expansion reserve. ``_apply_budget``
    withholds ``reserved`` at fetch so expansion has headroom; ``_budget_payloads``
    used to withhold it a second time against the same ``limit_tokens``. Because
    both sides share a cost function and ``used`` is monotonic, that made every
    handle advertised in ``next`` provably inadmissible at the very budget that
    advertised it — the reserve was capital nothing could spend.
    """
    from curator.context_service import ContextService

    paths = _seed_budget_vault(tmp_path)
    service = ContextService(paths)

    limit = 60
    pack = service.context_fetch(
        QueryRequest(question="context budget evidence", mode="local"),
        limit_tokens=limit,
    )
    assert pack["next"], "fixture must omit at least one item to offer a handle"
    assert pack["budget"]["reserved_tokens"] > 0, (
        "fetch must actually withhold a reserve for this regression to bite"
    )

    expanded = service.context_expand(
        pack_id=pack["pack_id"],
        handles=[pack["next"][0]["handle"]],
        expected_snapshot_id=pack["snapshot"]["snapshot_id"],
        limit_tokens=limit,  # the SAME budget that produced the handle
    )

    assert expanded["ok"] is True
    assert expanded["items"], (
        "a handle offered by `next` must be admissible at the budget that "
        f"offered it; got warnings={expanded['warnings']}"
    )
    # The cumulative pack still respects limit_tokens — expansion spends the
    # reserve, it does not grant a fresh full budget.
    assert expanded["budget"]["used_tokens"] <= limit
    assert expanded["budget"]["reserved_tokens"] == 0
