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
    """Return a ContextService evidence pack.

    Everything inside the system — route selection, entity seeding, BM25/vector
    matching — operates in English by contract (USER_GUIDE: "using English only
    as the internal search/reasoning language"). Only the question the user
    typed and the answer they read are in their own language.

    The English query is derived HERE, not accepted as an argument. It is an
    invariant with no exceptions, and an invariant that depends on the caller
    remembering to pass a parameter is not an invariant: `working_query` falls
    back to `question` when unset, so a forgetful caller silently makes every
    internal component read the original language. That is precisely how a
    Korean question came to be routed by English-only signals and seeded by a
    Latin-only tokenizer, returning none of the vault's distilled layers.

    Derivation extracts a short English SEARCH QUERY; it does not translate the
    message. Translating is wrong for the requests that actually occur — "이
    문장을 한글로 번역해줘: <long body>" translated into English becomes an
    English sentence asking for a Korean translation, which would then be routed
    and matched as though it were a question about the knowledge base. The same
    step decides such a message is not a knowledge question at all, by reading
    intent rather than by matching any list of words.
    """
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
        from ..query import derive_search_query
        from ..retrieval import QueryRequest

        with llm.build_client(config) as client:
            derived = derive_search_query(paths.state_db, client, query_text)
            english_query, is_knowledge, reason = (
                derived.search_query, derived.is_knowledge_question, derived.reason
            )
            # `status == "derived"` is load-bearing, not decoration. On the
            # provider-failure path `derive_search_query` returns
            # `DerivedQuery(terms, bool(terms), ..., status="fallback")`, where
            # the verdict is a GUESS from whether scraping found any terms --
            # and `_fallback_search_terms` drops single characters, so
            # `L^T M(Q)L = 0` and `A B C` both scrape to "" and the guess is
            # False. Without this check a provider outage returned an empty pack
            # for a real question on the popover and sidechat, which v0.81.0's
            # own CHANGELOG claimed were covered. They were not.
            classified = derived.status == "derived"
            if classified and not is_knowledge:
                # Not a knowledge question — the message asks for something to be
                # done to text the user supplied, or needs no stored knowledge.
                # Returning an empty pack is the honest answer; running retrieval
                # on it would select evidence for a question nobody asked.
                return {
                    "ok": True,
                    "operation": "context_fetch",
                    "items": [],
                    "evidence": [],
                    "source_span_ids": [],
                    "community_report_ids": [],
                    "synthesis_node_ids": [],
                    "memory_path_ids": [],
                    "warnings": [f"no retrieval: {reason}"],
                    "coverage": {"sufficiency": "not_applicable"},
                }
            # Propagate HOW the query was produced -- do not assert it.
            #
            # This line read `status = "derived"` unconditionally, and that one
            # literal was the whole bug: when the provider failed,
            # `derive_search_query` fell back to scraping the raw message, which
            # keeps every script, so a Korean question came back as Korean with
            # `is_knowledge_question=True`. Marking that "derived" suppressed the
            # seeding warning below (scoped to "unset"), and English-only entity
            # seeding then matched nothing with nothing said.
            status = derived.status
            return ContextService(paths, client, config=config).context_fetch(
                QueryRequest(
                    question=query_text,
                    english_query=english_query,
                    english_query_status=status,
                    intent=derived.intent,
                    # Stated, not defaulted -- but only when a classification
                    # actually ran. Reaching here with `status == "fallback"`
                    # means scraping found terms, which is not a verdict; saying
                    # `True` there would assert what nobody judged, in the same
                    # release that removed exactly that lie from the funnel.
                    is_knowledge_question=True if classified else None,
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

