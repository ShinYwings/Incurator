"""Unified context service boundary for agent-facing evidence packs."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from . import config as cfg
from . import curate_yml, db, asset_identity
from .retrieval import evidence as evidence_mod
from .retrieval import router
from .retrieval.models import EvidenceItem, EvidencePack, QueryRequest, StructuredLocator

__all__ = ["ContextService"]

_DEFAULT_BUDGET_LIMIT = 16000
_DEFAULT_RESERVED_TOKENS = 1000

# Plan F P8 route admission (SYSTEM_BEHAVIOR §31.8). ContextService serves every
# Plan-A route whose evidence is mapped into the progressive pack path. As of the
# explore-unification work (v0.20.0) `explore` is admitted: its grounding evidence
# flows through the shared pack path and its follow-up/insight generation is a
# synthesis-phase consumer (QueryOrchestrator), not a divergent retrieval pipeline.
# Any non-admitted or operationally disabled route degrades to `local`.
_ADMITTED_ROUTES = frozenset({"local", "source-section", "global", "explore"})
# Always-available safe baselines; never subject to rollback disabling.
_SAFE_ROUTES = frozenset({"local", "source-section"})
_DEGRADE_ROUTE = "local"
_DISABLED_ROUTES_ENV = "INCURATOR_DISABLED_ROUTES"


def _disabled_routes_from_env() -> frozenset[str]:
    raw = os.environ.get(_DISABLED_ROUTES_ENV, "")
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def _admit_route(
    route: str, reason: str, disabled_routes: frozenset[str]
) -> tuple[str, str, str | None]:
    """Gate the chosen route to the ContextService-admitted set.

    Returns ``(served_route, reason, downgraded_from)``. ``downgraded_from`` is the
    originally chosen route when it was rejected (experimental/unadmitted or rolled
    back), else ``None``. Safe baseline routes are never disabled. No retrieval runs
    for a rejected route — admission happens before `build_evidence`, so a rejected
    route never produces a second/divergent retrieval path.
    """
    if route not in _SAFE_ROUTES and route in disabled_routes:
        return _DEGRADE_ROUTE, f"{reason}; route '{route}' disabled (rollback) → local", route
    if route not in _ADMITTED_ROUTES:
        return _DEGRADE_ROUTE, f"{reason}; route '{route}' not admitted to ContextService → local", route
    return route, reason, None


# Locked feedback types (SYSTEM_BEHAVIOR §31.6). Append-only `FBK-*` events.
_FEEDBACK_TYPES = frozenset(
    {
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
)


def _new_prefixed_id(prefix: str, payload: str) -> str:
    return f"{prefix}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:12]}"


def _question_hash(request: QueryRequest) -> str:
    raw = request.working_query.strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _evidence_json(items: list[EvidenceItem]) -> list[dict[str, Any]]:
    return [
        {
            "id": item.id,
            "kind": item.kind,
            "title": item.title,
            "score": item.score,
            "source_span_ids": item.source_span_ids,
            "community_report_id": item.community_report_id,
            "synthesis_node_id": item.synthesis_node_id,
            "memory_path_id": item.memory_path_id,
        }
        for item in items
    ]


def _build_retrieval_trace(
    pack: EvidencePack,
    route: str,
    reason: str,
    *,
    selected_items: list[EvidenceItem],
    omitted_counts: dict[str, int],
) -> dict[str, Any]:
    base = pack.retrieval_trace.copy() if pack.retrieval_trace else {}
    base.update({
        "contract_version": "1",
        "retrieval_execution_id": pack.retrieval_execution_id,
        "route": {"selected": route, "reason": reason},
        "selection": {
            "candidate_count": len(pack.items) + sum(pack.omitted_counts.values()),
            "selected_count": len(selected_items),
            "omitted_counts": omitted_counts,
        },
        "warnings": pack.warnings,
    })
    return base


def _hash_epoch_rows(conn, sql: str) -> tuple[int, str]:
    hasher = hashlib.sha256()
    count = 0
    for row in conn.execute(sql):
        count += 1
        hasher.update(str(row[0]).encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(str(row[1] or "").encode("utf-8"))
        hasher.update(b"\n")
    return count, hasher.hexdigest()


def _source_epoch(paths: cfg.WikiPaths) -> dict[str, Any]:
    with db.connect(paths.state_db) as conn:
        source_count, source_hash = _hash_epoch_rows(
            conn,
            "SELECT id, content_hash FROM sources ORDER BY id",
        )
        span_count, span_hash = _hash_epoch_rows(
            conn,
            "SELECT id, content_hash FROM source_spans ORDER BY id",
        )
    return {
        "algorithm": "id_content_hash_v1",
        "source_count": source_count,
        "span_count": span_count,
        "source_content_hash": source_hash,
        "span_content_hash": span_hash,
    }


def _snapshot(paths: cfg.WikiPaths, *, policy_hash: str, request: QueryRequest) -> dict[str, Any]:
    closure = {
        "contract_version": "1",
        "schema_version": db.SCHEMA_VERSION,
        "workspace_path": str(paths.root.resolve()),
        "source_epoch": _source_epoch(paths),
        "policy_hash": policy_hash,
        "request": {
            "mode": request.mode,
            "source_key": request.source_key,
            "workspace_path": request.workspace_path,
        },
        "tokenizer": "conservative",
    }
    digest = hashlib.sha256(json.dumps(closure, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "snapshot_id": f"SNAP-{digest[:12]}",
        "source_epoch_hash": hashlib.sha256(
            json.dumps(closure["source_epoch"], sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "db_schema_version": db.SCHEMA_VERSION,
        "policy_hash": policy_hash,
        "tokenizer": "conservative",
    }


def _estimate_tokens(text: str) -> int:
    char_estimate = (len(text) + 3) // 4
    byte_estimate = (len(text.encode("utf-8")) + 2) // 3
    return max(1, char_estimate, byte_estimate)


def _expansion_handle(item_id: str) -> str:
    return f"EXP-{hashlib.sha256(item_id.encode('utf-8')).hexdigest()[:12]}"


def _verification_handle(item_id: str) -> str:
    return f"VER-{hashlib.sha256(item_id.encode('utf-8')).hexdigest()[:12]}"


def _apply_budget(
    items: list[EvidenceItem],
    *,
    limit_tokens: int,
) -> tuple[list[EvidenceItem], list[EvidenceItem], dict[str, int | str]]:
    limit = max(0, limit_tokens)
    reserved = min(_DEFAULT_RESERVED_TOKENS, max(0, limit // 4))
    available = max(0, limit - reserved)
    selected: list[EvidenceItem] = []
    omitted: list[EvidenceItem] = []
    used = 0
    for item in items:
        cost = _estimate_tokens(item.text)
        if used + cost <= available:
            selected.append(item)
            used += cost
        else:
            omitted.append(item)
    budget: dict[str, int | str] = {
        "limit_tokens": limit_tokens,
        "used_tokens": used,
        "reserved_tokens": reserved,
        "omitted_items": len(omitted),
        "estimation_mode": "conservative",
    }
    return selected, omitted, budget


def _selected_refs(items: list[EvidenceItem]) -> dict[str, list[str]]:
    source_span_ids: list[str] = []
    community_report_ids: list[str] = []
    synthesis_node_ids: list[str] = []
    memory_path_ids: list[str] = []
    seen_spans: set[str] = set()
    seen_reports: set[str] = set()
    seen_synthesis: set[str] = set()
    seen_paths: set[str] = set()
    for item in items:
        for span_id in item.source_span_ids:
            if span_id not in seen_spans:
                source_span_ids.append(span_id)
                seen_spans.add(span_id)
        if item.community_report_id and item.community_report_id not in seen_reports:
            community_report_ids.append(item.community_report_id)
            seen_reports.add(item.community_report_id)
        if item.synthesis_node_id and item.synthesis_node_id not in seen_synthesis:
            synthesis_node_ids.append(item.synthesis_node_id)
            seen_synthesis.add(item.synthesis_node_id)
        if item.memory_path_id and item.memory_path_id not in seen_paths:
            memory_path_ids.append(item.memory_path_id)
            seen_paths.add(item.memory_path_id)
    return {
        "source_span_ids": source_span_ids,
        "community_report_ids": community_report_ids,
        "synthesis_node_ids": synthesis_node_ids,
        "memory_path_ids": memory_path_ids,
    }


def _selected_refs_from_payloads(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    source_span_ids: list[str] = []
    community_report_ids: list[str] = []
    synthesis_node_ids: list[str] = []
    memory_path_ids: list[str] = []
    seen_spans: set[str] = set()
    seen_reports: set[str] = set()
    seen_synthesis: set[str] = set()
    seen_paths: set[str] = set()
    for item in items:
        for sid in item.get("source_span_ids", []):
            sid_str = str(sid)
            if sid_str not in seen_spans:
                source_span_ids.append(sid_str)
                seen_spans.add(sid_str)
        report_id = item.get("community_report_id")
        if report_id:
            report_id_str = str(report_id)
            if report_id_str not in seen_reports:
                community_report_ids.append(report_id_str)
                seen_reports.add(report_id_str)
        synthesis_id = item.get("synthesis_node_id")
        if synthesis_id:
            synthesis_id_str = str(synthesis_id)
            if synthesis_id_str not in seen_synthesis:
                synthesis_node_ids.append(synthesis_id_str)
                seen_synthesis.add(synthesis_id_str)
        path_id = item.get("memory_path_id")
        if path_id:
            path_id_str = str(path_id)
            if path_id_str not in seen_paths:
                memory_path_ids.append(path_id_str)
                seen_paths.add(path_id_str)
    return {
        "source_span_ids": source_span_ids,
        "community_report_ids": community_report_ids,
        "synthesis_node_ids": synthesis_node_ids,
        "memory_path_ids": memory_path_ids,
    }


def _source_meta_by_ids(db_path: Path, source_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not source_ids:
        return {}
    with db.connect(db_path) as conn:
        placeholders = ",".join("?" for _ in source_ids)
        rows = conn.execute(
            f"""
            SELECT id, relpath, file_type, external_ref, import_origin_ref,
                   logical_source_id, is_reference
              FROM sources
             WHERE id IN ({placeholders})
            """,
            tuple(source_ids),
        ).fetchall()
    return {int(row["id"]): dict(row) for row in rows}


def _locator_from_span(span: dict[str, Any], source: dict[str, Any] | None) -> StructuredLocator:
    # Single identity authority (SYSTEM_BEHAVIOR §29.6): is_reference and the
    # authoritative external open target (abs_path) come from one place.
    ident = asset_identity.from_source_row(source)
    relpath = span.get("relpath") or ident.relpath
    file_type = (source or {}).get("file_type", "md")
    if file_type == "pdf":
        source_kind = "vault_pdf"
    elif ident.is_reference:
        source_kind = "external_uri"
    elif relpath and str(relpath).lstrip("/").startswith("02_Wiki/"):
        source_kind = "promoted_wiki"
    else:
        source_kind = "vault_markdown"

    logical = str((source or {}).get("logical_source_id") or "")
    external_uri = None
    if ident.is_reference:
        external_uri = (
            f"zotero://open-pdf/library/items/{logical.split(':', 1)[1]}"
            if logical.startswith("zotero:")
            else ((source or {}).get("external_ref") or (source or {}).get("import_origin_ref"))
        )

    heading = span.get("section_title")
    toc_id = span.get("toc_id")
    page_number = span.get("page_number")
    if not relpath:
        locator_status = "fallback_source"
    elif heading or toc_id or page_number:
        locator_status = "exact"
    else:
        locator_status = "fallback_file"

    return StructuredLocator(
        source_id=span.get("source_id"),
        source_kind=source_kind,
        relpath=relpath,
        heading=heading,
        block_id=None,
        page_number=page_number,
        toc_id=toc_id,
        external_uri=external_uri,
        locator_status=locator_status,
    )


def _locator_map(db_path: Path, items: list[EvidenceItem]) -> dict[str, StructuredLocator]:
    span_ids = sorted({span_id for item in items for span_id in item.source_span_ids})
    spans = db.get_source_spans_by_ids(db_path, span_ids)
    sources = _source_meta_by_ids(
        db_path,
        sorted({int(span["source_id"]) for span in spans if span.get("source_id") is not None}),
    )
    return {
        span["id"]: _locator_from_span(span, sources.get(int(span["source_id"])))
        for span in spans
        if span.get("id") is not None and span.get("source_id") is not None
    }


def _locator_payload(locator: StructuredLocator | None) -> dict[str, Any] | None:
    if locator is None:
        return None
    return {
        "source_id": locator.source_id,
        "source_kind": locator.source_kind,
        "relpath": locator.relpath,
        "heading": locator.heading,
        "block_id": locator.block_id,
        "page_number": locator.page_number,
        "toc_id": locator.toc_id,
        "external_uri": locator.external_uri,
        "locator_status": locator.locator_status,
    }


def _item_locator(
    item: EvidenceItem,
    locators_by_span: dict[str, StructuredLocator],
) -> StructuredLocator | None:
    if item.locator is not None:
        return item.locator
    for span_id in item.source_span_ids:
        locator = locators_by_span.get(span_id)
        if locator is not None:
            return locator
    if item.source_span_ids:
        return StructuredLocator(
            source_id=None,
            source_kind="vault_markdown",
            relpath=None,
            heading=None,
            block_id=None,
            page_number=None,
            toc_id=None,
            external_uri=None,
            locator_status="unavailable",
        )
    return None


def _item_payload(
    item: EvidenceItem,
    locators_by_span: dict[str, StructuredLocator],
) -> dict[str, Any]:
    locator = _locator_payload(_item_locator(item, locators_by_span))
    orphaned_support = bool(
        item.source_span_ids
        and (
            locator is None
            or locator.get("locator_status") == "unavailable"
            or locator.get("source_id") is None
        )
    )
    truth_state = (
        "orphaned_support"
        if orphaned_support
        else "source_supported" if item.source_span_ids else "derived"
    )
    freshness_state = "stale" if orphaned_support else item.evidence_status
    return {
        "item_id": item.id,
        "record_id": item.id,
        "record_hash": hashlib.sha256(
            f"{item.kind}:{item.id}:{item.text}".encode("utf-8")
        ).hexdigest(),
        "kind": item.kind,
        "layer": item.kind,
        "summary": item.title,
        "detail": item.text,
        "title": item.title,
        "text": item.text,
        "score": item.score,
        "community_report_id": item.community_report_id,
        "synthesis_node_id": item.synthesis_node_id,
        "memory_path_id": item.memory_path_id,
        "authority_state": "derived",
        "truth_state": truth_state,
        # Claim support is served as a LABEL now that it no longer gates the
        # index. A reader (human or agent) must be able to tell a validated
        # claim from an unvalidated one; serving both without saying which is
        # which would trade a silent omission for a silent overstatement.
        #
        # Only knowledge units have claim support. Spans, entities, community
        # reports and synthesis nodes have none, and defaulting them to
        # "unchecked" would report a validation failure that never applied to
        # them — the same overstatement in the opposite direction.
        "support_state": item.support_status or "not_applicable",
        "freshness_state": freshness_state,
        "source_span_ids": item.source_span_ids,
        "locator": locator,
        "token_cost": _estimate_tokens(item.text),
        "expansion_handle": _expansion_handle(item.id),
        "verification_handle": _verification_handle(item.id),
    }


def _payload_token_cost(item: dict[str, Any]) -> int:
    return int(item.get("token_cost", _estimate_tokens(str(item.get("detail") or ""))))


def _budget_payloads(
    items: list[dict[str, Any]],
    *,
    limit_tokens: int,
    already_used: int = 0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int | str]]:
    """Pack ``items`` into the remaining budget.

    ``already_used`` is the token cost already consumed by items selected in prior
    operations on the same pack (e.g. a ``context_fetch`` selection that a later
    ``context_expand`` adds to). Seeding ``used`` with it keeps the *cumulative*
    selected set within ``limit_tokens`` instead of granting each expansion a fresh
    full budget, which would let the combined pack overflow the LLM window.

    The admission ceiling is the FULL ``limit_tokens``, not ``limit - reserved``.
    ``_apply_budget`` withholds the reserve at fetch time precisely so expansion
    has headroom; withholding it a second time here would spend nothing and make
    the reserve dead capital. Because both sides use the same cost function and
    ``used`` is monotonic, re-subtracting made every handle advertised in ``next``
    provably inadmissible at the budget that produced it: fetch omitted item *i*
    because ``used_i + cost_i > limit - reserved``, so ``already_used + cost_i``
    (with ``already_used >= used_i``) always exceeded that same ceiling. §31.1
    admits an expanded item "if it fits within ``limit_tokens`` alongside
    everything already selected" — ``limit_tokens``, not the reserved remainder.
    """
    limit = max(0, limit_tokens)
    available = limit
    selected: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    used = max(0, already_used)
    for item in items:
        cost = _payload_token_cost(item)
        if used + cost <= available:
            selected.append(item)
            used += cost
        else:
            omitted.append(item)
    budget: dict[str, int | str] = {
        "limit_tokens": limit_tokens,
        "used_tokens": used,
        # Nothing is withheld on the expand path — the fetch-time reserve is
        # exactly what this operation is spending.
        "reserved_tokens": 0,
        "omitted_items": len(omitted),
        "estimation_mode": "conservative",
    }
    return selected, omitted, budget


def _conflict_response(expected_snapshot_id: str, current_snapshot_id: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error_type": "snapshot_conflict",
        "expected_snapshot_id": expected_snapshot_id,
        "current_snapshot_id": current_snapshot_id,
        "resolution": "refetch_or_rebase",
    }


class ContextService:
    """Application façade for normalized context-pack operations."""

    def __init__(
        self,
        paths: cfg.WikiPaths,
        client: Any | None = None,
        *,
        disabled_routes: Iterable[str] | None = None,
    ) -> None:
        self.paths = paths
        self.client = client
        # P8 rollback seam: a route can be disabled here (tests/programmatic) or via
        # the INCURATOR_DISABLED_ROUTES env var, degrading it to the safe local route.
        self.disabled_routes: frozenset[str] = (
            frozenset(disabled_routes)
            if disabled_routes is not None
            else _disabled_routes_from_env()
        )

    def context_fetch(
        self,
        request: QueryRequest,
        *,
        expected_snapshot_id: str | None = None,
        limit_tokens: int = _DEFAULT_BUDGET_LIMIT,
    ) -> dict[str, Any]:
        started = time.monotonic()
        policy, policy_hash = curate_yml.resolve_curate_policy(
            request.workspace_path
        )
        snapshot = _snapshot(self.paths, policy_hash=policy_hash, request=request)
        if expected_snapshot_id and expected_snapshot_id != snapshot["snapshot_id"]:
            return _conflict_response(expected_snapshot_id, snapshot["snapshot_id"])

        status = router.graph_status(self.paths.state_db)
        route, reason = router.choose_route(request, policy, status)
        route, reason, downgraded_from = _admit_route(route, reason, self.disabled_routes)
        route_admission = {
            "requested": downgraded_from or route,
            "served": route,
            "admitted_routes": sorted(_ADMITTED_ROUTES),
            "disabled_routes": sorted(self.disabled_routes),
            "downgraded": downgraded_from is not None,
        }
        pack = evidence_mod.build_evidence(self.paths, request, route, policy=policy)
        selected_items, budget_omitted_items, budget = _apply_budget(
            pack.items,
            limit_tokens=limit_tokens,
        )
        selected_refs = _selected_refs(selected_items)
        omitted_counts = {
            key: int(value)
            for key, value in pack.omitted_counts.items()
            if int(value) > 0
        }
        if budget_omitted_items:
            omitted_counts["budget"] = omitted_counts.get("budget", 0) + len(
                budget_omitted_items
            )
        locators_by_span = _locator_map(
            self.paths.state_db,
            [*selected_items, *budget_omitted_items],
        )
        selected_payloads = [
            _item_payload(item, locators_by_span) for item in selected_items
        ]
        omitted_payloads = [
            _item_payload(item, locators_by_span) for item in budget_omitted_items
        ]
        trace_id = db.new_query_trace_id()
        pack_id = _new_prefixed_id("PACK", f"{trace_id}:{snapshot['snapshot_id']}")
        actions = [
            {
                "action_id": _new_prefixed_id("CTXA", f"{trace_id}:1:retrieval"),
                "trace_id": trace_id,
                "order": 1,
                "action_type": "retrieval",
                "child_id": pack.retrieval_execution_id,
            },
            {
                "action_id": _new_prefixed_id("CTXA", f"{trace_id}:2:pack_assembly"),
                "trace_id": trace_id,
                "order": 2,
                "action_type": "pack_assembly",
                "child_id": pack_id,
            },
            {
                "action_id": _new_prefixed_id("CTXA", f"{trace_id}:3:budget"),
                "trace_id": trace_id,
                "order": 3,
                "action_type": "budget",
                "child_id": pack_id,
            },
        ]
        retrieval_trace = _build_retrieval_trace(
            pack,
            route,
            reason,
            selected_items=selected_items,
            omitted_counts=omitted_counts,
        )
        retrieval_trace["context_service"] = {
            "contract_version": "1",
            "pack_id": pack_id,
            "snapshot": snapshot,
            "actions": actions,
            "budget": budget,
            "route_admission": route_admission,
            "selected_items": selected_payloads,
            "omitted_items": omitted_payloads,
        }
        db.insert_query_trace(
            self.paths.state_db,
            trace_id=trace_id,
            workspace_id=policy.workspace_id,
            question_hash=_question_hash(request),
            route=route,
            route_reason=reason,
            evidence=_evidence_json(selected_items),
            source_span_ids=selected_refs["source_span_ids"],
            community_report_ids=selected_refs["community_report_ids"],
            synthesis_node_ids=selected_refs["synthesis_node_ids"],
            memory_path_ids=selected_refs["memory_path_ids"],
            retrieval_trace=retrieval_trace,
            warnings=pack.warnings,
            latency_ms=int((time.monotonic() - started) * 1000),
        )

        items = selected_payloads
        coverage = "partial" if pack.warnings or omitted_counts else "sufficient"
        next_actions = [
            {
                "handle": item["expansion_handle"],
                "reason": "budget",
                "item_id": item["record_id"],
                "snapshot_id": snapshot["snapshot_id"],
            }
            for item in omitted_payloads
        ]
        return {
            "ok": True,
            "contract_version": "1",
            "operation": "context_fetch",
            "pack_id": pack_id,
            "trace_id": trace_id,
            "retrieval_execution_id": pack.retrieval_execution_id,
            "snapshot": snapshot,
            "actions": actions,
            "route": route,
            "route_reason": reason,
            "route_admission": route_admission,
            "workspace_id": policy.workspace_id,
            "budget": budget,
            "coverage": {
                "sufficiency": coverage,
                "omitted_counts": omitted_counts,
            },
            "items": items,
            "evidence": [
                {
                    "id": item.id,
                    "kind": item.kind,
                    "title": item.title,
                    "text": item.text,
                    "score": item.score,
                    "source_span_ids": item.source_span_ids,
                    "community_report_id": item.community_report_id,
                    "synthesis_node_id": item.synthesis_node_id,
                    "memory_path_id": item.memory_path_id,
                    "locator": _locator_payload(_item_locator(item, locators_by_span)),
                }
                for item in selected_items
            ],
            "source_span_ids": selected_refs["source_span_ids"],
            "community_report_ids": selected_refs["community_report_ids"],
            "synthesis_node_ids": selected_refs["synthesis_node_ids"],
            "memory_path_ids": selected_refs["memory_path_ids"],
            "warnings": pack.warnings,
            "next": next_actions,
        }

    def context_manifest(self, *, limit_families: int = 5) -> dict[str, Any]:
        request = QueryRequest(question="", mode="auto")
        _policy, policy_hash = curate_yml.resolve_curate_policy("")
        snapshot = _snapshot(self.paths, policy_hash=policy_hash, request=request)
        with db.connect(self.paths.state_db) as conn:
            families = [
                {
                    "family": "sources",
                    "count": int(conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]),
                },
                {
                    "family": "source_spans",
                    "count": int(conn.execute("SELECT COUNT(*) FROM source_spans").fetchone()[0]),
                },
                {
                    "family": "entities",
                    "count": int(conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0]),
                },
                {
                    "family": "community_reports",
                    "count": int(conn.execute("SELECT COUNT(*) FROM community_reports").fetchone()[0]),
                },
                {
                    "family": "synthesis",
                    "count": int(conn.execute("SELECT COUNT(*) FROM synthesis_nodes").fetchone()[0]),
                },
            ][: max(0, limit_families)]
        return {
            "ok": True,
            "contract_version": "1",
            "operation": "context_manifest",
            "snapshot": snapshot,
            "families": families,
            "next": [
                {
                    "handle": _expansion_handle(f"manifest:{family['family']}"),
                    "family": family["family"],
                    "detail": "index",
                }
                for family in families
            ],
        }

    def context_expand(
        self,
        *,
        pack_id: str,
        handles: list[str],
        expected_snapshot_id: str,
        limit_tokens: int = _DEFAULT_BUDGET_LIMIT,
    ) -> dict[str, Any]:
        trace, context = self._find_context_pack_by_pack_id(pack_id)
        if trace is None or context is None:
            return {"ok": False, "error_type": "pack_not_found", "pack_id": pack_id}
        snapshot = context["snapshot"]
        current_snapshot_id = str(snapshot["snapshot_id"])
        if expected_snapshot_id != current_snapshot_id:
            return _conflict_response(expected_snapshot_id, current_snapshot_id)

        omitted_candidates = list(context.get("omitted_items", []))
        selected_candidates = list(context.get("selected_items", []))
        wanted = set(handles)
        matched = [
            item for item in omitted_candidates if item.get("expansion_handle") in wanted
        ]
        already_selected = [
            handle
            for handle in handles
            if any(
                item.get("expansion_handle") == handle for item in selected_candidates
            )
        ]
        already_used = sum(_payload_token_cost(item) for item in selected_candidates)
        selected, omitted, budget = _budget_payloads(
            matched, limit_tokens=limit_tokens, already_used=already_used
        )
        if not selected and not omitted:
            warning = (
                "expansion handles already selected"
                if already_selected
                else "no expansion handles matched"
            )
            return {
                "ok": True,
                "contract_version": "1",
                "operation": "context_expand",
                "root_pack_id": pack_id,
                "pack_id": _new_prefixed_id(
                    "PACK",
                    f"{pack_id}:expand-empty:{','.join(handles)}",
                ),
                "trace_id": trace["trace_id"],
                "snapshot": snapshot,
                "budget": budget,
                "items": [],
                "source_span_ids": [],
                "warnings": [warning],
                "next": [],
                "expansion_refused": [],
            }
        expanded_pack_id = _new_prefixed_id(
            "PACK",
            f"{pack_id}:expand:{','.join(handles)}:{len(context.get('actions', []))}",
        )
        selected_handles = {str(item.get("expansion_handle")) for item in selected}
        expansion_refused = [
            {
                "handle": item["expansion_handle"],
                "reason": "budget_exhausted",
                "item_id": item["record_id"],
                "snapshot_id": current_snapshot_id,
                "retry": "increase_limit_tokens_or_refetch",
            }
            for item in omitted
        ]
        if selected:
            selected_record_ids = {
                str(item.get("record_id")) for item in selected_candidates
            }
            updated_selected = [
                *selected_candidates,
                *[
                    item
                    for item in selected
                    if str(item.get("record_id")) not in selected_record_ids
                ],
            ]
            updated_omitted = [
                item
                for item in omitted_candidates
                if str(item.get("expansion_handle")) not in selected_handles
            ]
            self._append_context_action(
                trace,
                context,
                action_type="expansion",
                child_id=expanded_pack_id,
                payload={
                    "handles": handles,
                    "selected_item_ids": [item["record_id"] for item in selected],
                    "omitted_item_ids": [item["record_id"] for item in omitted],
                    "budget": budget,
                    "expansion_refused": expansion_refused,
                },
                context_updates={
                    "selected_items": updated_selected,
                    "omitted_items": updated_omitted,
                },
            )
        refs = _selected_refs_from_payloads(selected)
        return {
            "ok": True,
            "contract_version": "1",
            "operation": "context_expand",
            "root_pack_id": pack_id,
            "pack_id": expanded_pack_id,
            "trace_id": trace["trace_id"],
            "snapshot": snapshot,
            "budget": budget,
            "items": selected,
            "source_span_ids": refs["source_span_ids"],
            "warnings": [] if matched else ["no expansion handles matched"],
            "next": [],
            "expansion_refused": expansion_refused,
        }

    def context_verify(
        self,
        *,
        pack_id: str,
        verification_handle: str,
        expected_snapshot_id: str,
    ) -> dict[str, Any]:
        trace, context = self._find_context_pack_by_pack_id(pack_id)
        if trace is None or context is None:
            return {"ok": False, "error_type": "pack_not_found", "pack_id": pack_id}
        snapshot = context["snapshot"]
        current_snapshot_id = str(snapshot["snapshot_id"])
        if expected_snapshot_id != current_snapshot_id:
            return _conflict_response(expected_snapshot_id, current_snapshot_id)

        candidates = list(context.get("selected_items", [])) + list(
            context.get("omitted_items", [])
        )
        item = next(
            (
                candidate
                for candidate in candidates
                if candidate.get("verification_handle") == verification_handle
            ),
            None,
        )
        if item is None:
            return {
                "ok": False,
                "error_type": "verification_handle_not_found",
                "pack_id": pack_id,
                "verification_handle": verification_handle,
            }

        self._append_context_action(
            trace,
            context,
            action_type="verification",
            child_id=verification_handle,
            payload={"record_id": item["record_id"]},
        )
        return {
            "ok": True,
            "contract_version": "1",
            "operation": "context_verify",
            "pack_id": pack_id,
            "trace_id": trace["trace_id"],
            "snapshot": snapshot,
            "item": item,
            "source_span_ids": item.get("source_span_ids", []),
            "locator": item.get("locator"),
            "dependencies": [],
            "contradictions": [],
        }

    def context_feedback(
        self,
        *,
        trace_id: str,
        pack_id: str,
        feedback_type: str,
        statement: str,
        client: str = "",
        purpose: str = "",
        target: dict[str, Any] | None = None,
        reviewed_source_span_ids: list[str] | None = None,
        review_status: str = "pending",
    ) -> dict[str, Any]:
        """Append a single append-only ``FBK-*`` feedback event to a pack's root.

        SYSTEM_BEHAVIOR §31.6 / SCHEMA §23.2: every event links to the root
        ``QTR-*``, ``PACK-*``, and ``SNAP-*`` and records client/purpose, target,
        reviewed evidence, statement, classification, review status, and any
        resulting lineage. Feedback is quarantined: it never mutates ranking,
        truth status, source files, or generated records here. The lineage fields
        stay unresolved until a separately specified reviewed policy applies them.
        """
        if feedback_type not in _FEEDBACK_TYPES:
            return {
                "ok": False,
                "error_type": "invalid_feedback_type",
                "feedback_type": feedback_type,
                "allowed": sorted(_FEEDBACK_TYPES),
            }
        trace, context = self._find_context_pack(trace_id, pack_id)
        if trace is None or context is None:
            return {
                "ok": False,
                "error_type": "pack_not_found",
                "trace_id": trace_id,
                "pack_id": pack_id,
            }

        snapshot = context["snapshot"]
        snapshot_id = str(snapshot["snapshot_id"])
        order = len(context.get("actions", [])) + 1
        feedback_id = _new_prefixed_id(
            "FBK",
            f"{trace['trace_id']}:{pack_id}:{feedback_type}:{order}:{statement}",
        )
        normalized_target = {
            "item_id": (target or {}).get("item_id"),
            "record_id": (target or {}).get("record_id"),
            "claim_id": (target or {}).get("claim_id"),
        }
        resulting_lineage: dict[str, Any] = {
            "insight_candidate_id": None,
            "promotion_relpath": None,
            "correction_node_ids": [],
        }
        event = {
            "feedback_id": feedback_id,
            "feedback_type": feedback_type,
            "trace_id": trace["trace_id"],
            "pack_id": pack_id,
            "snapshot_id": snapshot_id,
            "client": client,
            "purpose": purpose,
            "target": normalized_target,
            "reviewed_source_span_ids": list(reviewed_source_span_ids or []),
            "statement": statement,
            "review_status": review_status,
            # Quarantined: resolved only when a reviewed policy explicitly applies
            # the feedback (classification, insight candidate, promotion, or
            # correction). Recording feedback alone changes nothing downstream.
            "classification": None,
            "review_actor": None,
            "review_time": None,
            "resulting_lineage": resulting_lineage,
        }
        # Lifecycle integration (quarantined): a `new_insight` event records a
        # provisional `pending` insight candidate for later human review. This
        # never edits source truth, generated records, or ranking — it only
        # enqueues a candidate, exactly like `curator_propose_correction`.
        # `correction` patching and `02_Wiki/` promotion stay behind their
        # existing explicit human-approval tools.
        if feedback_type == "new_insight":
            from . import insight_lifecycle
            from .backprop_classifier import BackpropClassification

            record_id = normalized_target.get("record_id")
            affected_nodes = [str(record_id)] if record_id else []
            classification = BackpropClassification(
                classification="derived_insight",
                affected_nodes=affected_nodes,
                recommended_action="create_insight_candidate",
                reason="context_feedback new_insight",
                trace_id=feedback_id,
                ok=True,
            )
            candidate_id = insight_lifecycle.create_insight_from_classification(
                self.paths.state_db,
                classification,
                statement=statement,
                source_event_id=feedback_id,
                evidence=list(reviewed_source_span_ids or []),
            )
            event["resulting_lineage"]["insight_candidate_id"] = candidate_id
        self._append_context_action(
            trace,
            context,
            action_type="feedback",
            child_id=feedback_id,
            payload=event,
        )
        return {
            "ok": True,
            "contract_version": "1",
            "operation": "context_feedback",
            "feedback_id": feedback_id,
            "feedback_type": feedback_type,
            "trace_id": trace["trace_id"],
            "pack_id": pack_id,
            "snapshot": snapshot,
            "target": normalized_target,
            "reviewed_source_span_ids": list(reviewed_source_span_ids or []),
            "review_status": review_status,
            "resulting_lineage": event["resulting_lineage"],
            "ranking_or_truth_mutated": False,
        }

    def _find_context_pack(
        self,
        trace_id: str,
        pack_id: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        trace = db.get_query_trace(self.paths.state_db, trace_id)
        if not trace:
            return None, None
        context = (trace.get("retrieval_trace") or {}).get("context_service")
        if isinstance(context, dict) and context.get("pack_id") == pack_id:
            return trace, context
        return trace, None

    def _find_context_pack_by_pack_id(
        self,
        pack_id: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        trace = db.get_query_trace_by_context_pack(self.paths.state_db, pack_id)
        if not trace:
            return None, None
        context = (trace.get("retrieval_trace") or {}).get("context_service")
        if isinstance(context, dict) and context.get("pack_id") == pack_id:
            return trace, context
        return trace, None

    def _append_context_action(
        self,
        trace: dict[str, Any],
        context: dict[str, Any],
        *,
        action_type: str,
        child_id: str,
        payload: dict[str, Any],
        context_updates: dict[str, Any] | None = None,
    ) -> None:
        actions = list(context.get("actions", []))
        order = len(actions) + 1
        action = {
            "action_id": _new_prefixed_id(
                "CTXA",
                f"{trace['trace_id']}:{order}:{action_type}:{child_id}",
            ),
            "trace_id": trace["trace_id"],
            "order": order,
            "action_type": action_type,
            "child_id": child_id,
            "payload": payload,
        }
        actions.append(action)
        retrieval_trace = dict(trace.get("retrieval_trace") or {})
        updated_context = dict(context)
        if context_updates:
            updated_context.update(context_updates)
        updated_context["actions"] = actions
        retrieval_trace["context_service"] = updated_context
        db.insert_query_trace(
            self.paths.state_db,
            trace_id=trace["trace_id"],
            workspace_id=trace["workspace_id"],
            question_hash=trace["question_hash"],
            route=trace["route"],
            route_reason=trace["route_reason"],
            evidence=trace["evidence"],
            source_span_ids=trace["source_span_ids"],
            community_report_ids=trace["community_report_ids"],
            synthesis_node_ids=trace["synthesis_node_ids"],
            memory_path_ids=trace["memory_path_ids"],
            prompt_trace_ids=trace["prompt_trace_ids"],
            insight_candidate_ids=trace["insight_candidate_ids"],
            retrieval_trace=retrieval_trace,
            warnings=trace["warnings"],
            latency_ms=trace["latency_ms"],
            created_at=trace.get("created_at"),
        )
