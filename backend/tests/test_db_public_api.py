"""DB-2 safety net: the public `db.*` surface must survive the package split.

`db.py` is being decomposed into a `db/` package (DB-2). Every caller imports the
module (`from . import db`) and uses `db.<name>`, so the package facade MUST keep
exposing the same public names. This test captures the pre-refactor surface and
asserts the live `db` package still exposes a superset.

The capture filter keeps only names OWNED by the db package (`__module__`
startswith ``"curator.db"``) plus an explicit allowlist of public bare
constants/enums (which have no usable ``__module__``). This (a) excludes
re-imported stdlib/typing names (`sqlite3`, `json`, `Path`, …) and (b) tolerates
the post-refactor ``__module__`` move from ``curator.db`` to
``curator.db.schema`` / ``curator.db._entities`` (prefix match).
"""

import curator.db as db

# Public bare constants/enums (frozensets / SCHEMA_SQL / SCHEMA_VERSION) that are
# real API but carry no module-owned ``__module__``.
_ALLOWLIST_CONSTANTS = {
    "FORMULA_STATUSES", "GENERATION_STATUSES", "GRAPH_AUDIT_CODES",
    "MERGE_DECISION_CODES", "QUARANTINE_REASON_CODES", "RESOLUTION_STATUS_CODES",
    "SUPPORT_ROLES", "SUPPORT_STATUSES", "SCHEMA_SQL", "SCHEMA_VERSION",
}

# Underscore helpers that external modules reach via ``db._<name>`` (e.g.
# claim_support / compile use ``db._maybe_conn`` / ``db._now_iso``). These are
# part of the de-facto surface and MUST stay re-exported by the facade.
_UNDERSCORE_EXTERNALS = {"_maybe_conn", "_now_iso"}

# Captured 2026-06-28 from the pre-refactor db.py (128 names). Do not shrink.
EXPECTED_PUBLIC_API = frozenset({
    "FORMULA_STATUSES", "GENERATION_STATUSES", "GRAPH_AUDIT_CODES",
    "MERGE_DECISION_CODES", "QUARANTINE_REASON_CODES", "RESOLUTION_STATUS_CODES",
    "SCHEMA_SQL", "SCHEMA_VERSION", "SUPPORT_ROLES", "SUPPORT_STATUSES",
    "accept_entity_merge", "accumulate_job_tokens", "cancel_job",
    "claim_next_job", "clear_l2_checkpoints", "clear_search_corpus",
    "clear_synthesis_nodes", "compile_relation_lifecycle", "connect",
    "connected_components", "count_active_l2_jobs", "create_compiler_generation",
    "create_insight_candidate", "delete_page_hash", "delete_search_document",
    "delete_source_spans", "dependents_of", "detect_bridge_risk_relations",
    "discard_compiler_generation", "enqueue_job", "evaluate_merge_guards",
    "find_graph_entities", "finish_prompt_run", "fts_search",
    "get_authoritative_generation", "get_community_report", "get_curation_plan",
    "get_dag_edges_for_atoms", "get_dag_edges_for_source", "get_graph_entity",
    "get_index_meta", "get_ingest_job", "get_insight_candidate",
    "get_jobs_done_today", "get_l2_checkpoint_hashes", "get_page_hashes",
    "get_pending_count", "get_pending_jobs_for_source", "get_prompt_run",
    "get_query_trace", "get_query_trace_by_context_pack", "get_search_chunk",
    "get_search_document", "get_search_embeddings", "get_source_row",
    "get_source_spans_by_ids", "get_stats", "get_synthesis_node", "graph_audit",
    "graph_config_hash", "has_l2_checkpoints", "has_search_embeddings", "init_db",
    "insert_dag_edge", "insert_l2_checkpoint", "insert_query_trace", "json_dumps",
    "list_claim_supports", "list_community_reports", "list_eligible_knowledge_units",
    "list_generation_units", "list_ingest_jobs", "list_insight_candidates",
    "list_knowledge_units_for_source", "list_memory_paths",
    "list_prompt_runs_for_query", "list_query_traces", "list_search_chunks_for_doc",
    "list_search_documents", "list_serving_units", "list_source_pages",
    "list_source_pdf_pages", "list_source_spans", "list_staged_unit_ids_for_source",
    "list_synthesis_nodes", "mark_job_done", "mark_job_failed",
    "new_query_trace_id", "propose_entity_merge", "publish_compiler_generation",
    "rebuild_graph_generation", "reconcile_source_change",
    "record_artifact_dependency", "record_curation_plan", "record_memory_path",
    "record_prompt_run", "record_source_page", "recover_stale_jobs",
    "refresh_support_freshness", "relation_neighborhood", "replace_source_pdf_pages",
    "requeue_job_for_retry", "rerun_job", "retire_knowledge_unit",
    "reverse_entity_merge", "set_index_meta", "set_source_layer_status",
    "set_sources_layer_status", "set_unit_formula_status", "set_unit_support_status",
    "source_path_to_relpath", "sources_for_spans", "update_insight_candidate_status",
    "update_job_progress", "update_page_hash", "upsert_claim_support",
    "upsert_community_report", "upsert_graph_entity", "upsert_graph_relation",
    "upsert_graph_relation_support", "upsert_knowledge_unit", "upsert_search_chunk",
    "upsert_search_document", "upsert_search_embedding", "upsert_source_span",
    "upsert_synthesis_node", "vision_cache_get", "vision_cache_put",
})


def _current_public_api() -> set[str]:
    names: set[str] = set()
    for name in dir(db):
        if name.startswith("_"):
            continue
        obj = getattr(db, name)
        mod = getattr(obj, "__module__", None)
        if (callable(obj) and mod and mod.startswith("curator.db")) or name in _ALLOWLIST_CONSTANTS:
            names.add(name)
    return names


def test_db_public_api_superset_preserved():
    missing = EXPECTED_PUBLIC_API - _current_public_api()
    assert not missing, f"db facade dropped public symbols after DB-2 split: {sorted(missing)}"


def test_db_underscore_externals_still_exported():
    # Helpers reached via db._<name> by other modules must remain accessible.
    missing = {n for n in _UNDERSCORE_EXTERNALS if not hasattr(db, n)}
    assert not missing, f"db facade dropped underscore helpers used externally: {sorted(missing)}"
