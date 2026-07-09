from __future__ import annotations

from typing import Any

from .. import config as cfg
from .. import llm

def _normalize_link(value: str) -> str:
    return value.strip().strip("[]").removeprefix(".curator/Collections/").removesuffix(".md")


def fetch_context(
    paths: cfg.WikiPaths,
    *,
    query_text: str,
    workspace_path: str = "",
    limit_tokens: int = 8000,
) -> dict[str, Any]:
    if not query_text.strip():
        return {
            "ok": False,
            "operation": "context_fetch",
            "error": "query is required",
        }

    try:
        config = cfg.load_config(paths)
    except Exception as exc:
        return {"ok": False, "operation": "context_fetch", "error": f"Config error: {exc}"}

    try:
        from ..context_service import ContextService
        from ..retrieval import QueryRequest

        with llm.build_client(config) as client:
            return ContextService(paths, client).context_fetch(
                QueryRequest(
                    question=query_text,
                    workspace_path=workspace_path,
                    mode="auto",
                ),
                limit_tokens=max(1, int(limit_tokens)),
            )
    except Exception as exc:
        return {
            "ok": False,
            "operation": "context_fetch",
            "error": f"Context fetch error: {exc}",
        }


def expand_context(
    paths: cfg.WikiPaths,
    *,
    pack_id: str,
    handles: list[str],
    expected_snapshot_id: str,
    limit_tokens: int = 8000,
) -> dict[str, Any]:
    if not pack_id:
        return {"ok": False, "operation": "context_expand", "error": "pack_id is required"}
    if not handles:
        return {"ok": False, "operation": "context_expand", "error": "at least one handle is required"}
    if not expected_snapshot_id:
        return {
            "ok": False,
            "operation": "context_expand",
            "error": "expected_snapshot_id is required",
        }

    try:
        from ..context_service import ContextService

        return ContextService(paths).context_expand(
            pack_id=pack_id,
            handles=handles,
            expected_snapshot_id=expected_snapshot_id,
            limit_tokens=max(1, int(limit_tokens)),
        )
    except Exception as exc:
        return {
            "ok": False,
            "operation": "context_expand",
            "error": f"Context expand error: {exc}",
        }


def verify_context(
    paths: cfg.WikiPaths,
    *,
    pack_id: str,
    verification_handle: str,
    expected_snapshot_id: str,
) -> dict[str, Any]:
    if not pack_id:
        return {"ok": False, "operation": "context_verify", "error": "pack_id is required"}
    if not verification_handle:
        return {
            "ok": False,
            "operation": "context_verify",
            "error": "verification_handle is required",
        }
    if not expected_snapshot_id:
        return {
            "ok": False,
            "operation": "context_verify",
            "error": "expected_snapshot_id is required",
        }

    try:
        from ..context_service import ContextService

        return ContextService(paths).context_verify(
            pack_id=pack_id,
            verification_handle=verification_handle,
            expected_snapshot_id=expected_snapshot_id,
        )
    except Exception as exc:
        return {
            "ok": False,
            "operation": "context_verify",
            "error": f"Context verify error: {exc}",
        }


def feedback_context(
    paths: cfg.WikiPaths,
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
    if not trace_id:
        return {"ok": False, "operation": "context_feedback", "error": "trace_id is required"}
    if not pack_id:
        return {"ok": False, "operation": "context_feedback", "error": "pack_id is required"}
    if not feedback_type:
        return {
            "ok": False,
            "operation": "context_feedback",
            "error": "feedback_type is required",
        }
    if not statement:
        return {
            "ok": False,
            "operation": "context_feedback",
            "error": "statement is required",
        }

    try:
        from ..context_service import ContextService

        return ContextService(paths).context_feedback(
            trace_id=trace_id,
            pack_id=pack_id,
            feedback_type=feedback_type,
            statement=statement,
            client=client,
            purpose=purpose,
            target=target,
            reviewed_source_span_ids=reviewed_source_span_ids,
            review_status=review_status,
        )
    except Exception as exc:
        return {
            "ok": False,
            "operation": "context_feedback",
            "error": f"Context feedback error: {exc}",
        }

