"""ROADMAP A8 (v0.69.0): the derivation happens once, in the funnel, and only
when the question is not already English.

Two facts decided this shape, both measured rather than argued.

**Why the funnel and not each boundary.** `ContextService.context_fetch` is the
single point every surface reaches: `choose_route` is called once inside it and
`build_evidence` once. Derivation lived at ONE boundary from v0.47.0, and four
sibling surfaces never caught up -- and the one that was filled in was filled in
wrong (`curator_query` passed the raw question as `english_query` until v0.68.0).
"Add it at each boundary" is not a hypothetical failure mode here; it is this
codebase's measured history.

**Why the gate.** `query.py` records that the deterministic fallback returns
1,508 hits across the same 28 sources with the same top results as the LLM's
1,500 -- "for none of the LLM's 12-50 s". So derivation buys nothing on search
terms; what it uniquely produces is `intent`.

And on the CLI, `english_query` is empty, so `working_query` is the USER'S OWN
WORDS. For an English question the route signals read what the user actually
typed -- strictly better than a derived paraphrase, which produced eight
different phrasings of one question and flipped the route 6-in-8. Paying 12-50 s
to replace real words with a sampled paraphrase is a bad trade.

For a non-English question the English-only signals cannot match at all, so the
route is `local` by construction, every time. That is the case worth an LLM call.
"""

from __future__ import annotations

import json
from pathlib import Path

from curator import config as cfg
from curator import db
from curator.retrieval.models import QueryRequest

KOREAN = "내 볼트 전체의 주제를 정리해줘"
ENGLISH = "what does a residual connection do?"


class _CountingClient:
    """Counts derivations and answers them as a synthesis-intent question."""

    model = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, *, json_mode: bool = False, temperature: float = 0.3) -> str:
        self.calls += 1
        return json.dumps({
            "search_query": "vault themes overview",
            "is_knowledge_question": True,
            "intent": "synthesis",
            "reason": "asks for a whole-corpus summary",
        })


def _vault(tmp_path: Path) -> cfg.WikiPaths:
    paths = cfg.WikiPaths(tmp_path / "vault")
    db.init_db(paths.state_db)
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
            "VALUES ('04_Resources/context.md', 'h', 'md', 1, datetime('now'))"
        )
    span = db.upsert_source_span(
        paths.state_db, source_id=1, relpath="04_Resources/context.md",
        span_type="paragraph", content_hash="c", section_title="Context",
        text_preview="Residual connections stabilize optimization.",
    )
    db.upsert_graph_entity(
        paths.state_db, canonical_name="residual connection",
        entity_type="concept", source_span_ids=[span],
    )
    return paths


def _fetch(paths, question: str, client, **kw):
    from curator import context_service as cs

    return cs.ContextService(paths, client).context_fetch(
        QueryRequest(question=question, mode="auto", **kw)
    )


def test_an_english_question_is_not_sent_to_the_model(tmp_path: Path) -> None:
    """The whole point of the gate. An English CLI question already routes on
    the user's real words; a derivation would only replace them with a sampled
    paraphrase, for 12-50 s."""
    client = _CountingClient()
    response = _fetch(_vault(tmp_path), ENGLISH, client)
    assert client.calls == 0, "an English question paid for a derivation"
    assert response["ok"]


def test_a_non_english_question_is_derived(tmp_path: Path) -> None:
    """Without this the English-only route signals cannot match, so the route is
    `local` by construction no matter what the user asked for."""
    client = _CountingClient()
    paths = _vault(tmp_path)
    response = _fetch(paths, KOREAN, client)
    assert client.calls == 1
    trace = db.get_query_trace(paths.state_db, response["trace_id"])
    assert trace is not None
    derivation = trace["retrieval_trace"]["context_service"]["derivation"]
    assert derivation["status"] == "derived"
    assert derivation["routing_intent"] == "synthesis"


def test_no_client_means_no_derivation(tmp_path: Path) -> None:
    """38 test constructions of ContextService pass no client, and the CLI's
    `fetch_context` path may not have one either. Behaviour must be unchanged."""
    paths = _vault(tmp_path)
    response = _fetch(paths, KOREAN, None)
    trace = db.get_query_trace(paths.state_db, response["trace_id"])
    assert trace["retrieval_trace"]["context_service"]["derivation"]["status"] == "unset"


def test_an_already_derived_request_is_not_derived_twice(tmp_path: Path) -> None:
    """The plugin boundary still derives, because it also decides whether the
    message is a knowledge question at all -- a chat-UX judgment the retrieval
    layer should not make for four other callers."""
    client = _CountingClient()
    _fetch(
        _vault(tmp_path), KOREAN, client,
        english_query="vault themes", english_query_status="derived", intent="synthesis",
    )
    assert client.calls == 0


def test_the_derived_query_reaches_the_caller_not_just_the_trace(tmp_path: Path) -> None:
    """`QueryOrchestrator` echoes `english_query` back in its result. If the
    funnel derives into a local copy, the orchestrator keeps reporting the raw
    question and the plugin shows the user a query the system never ran."""
    client = _CountingClient()
    response = _fetch(_vault(tmp_path), KOREAN, client)
    assert response["english_query"] == "vault themes overview"


def test_a_korean_question_can_finally_reach_global(tmp_path: Path) -> None:
    """The acceptance test for the whole item.

    Before: the route signals are English-only by contract, so this question
    matched nothing and landed on `local` every single time -- the v0.47.0
    defect, still live on the CLI and MCP through v0.68.0.
    """
    paths = _vault(tmp_path)
    db.upsert_community_report(
        paths.state_db, community_key="c1", title="Themes", summary="s",
        full_content="...", dependency_hash="d", entity_ids=[], source_span_ids=[], rank=0.5,
    )
    assert _fetch(paths, KOREAN, None)["route"] == "local"          # before
    assert _fetch(paths, KOREAN, _CountingClient())["route"] == "global"  # after


def test_the_orchestrator_reports_the_query_it_actually_ran(tmp_path: Path) -> None:
    """The gap the pack-level test above does NOT cover, and I missed it once.

    `replace()` inside the funnel rebinds a local; the orchestrator holds the
    caller's original request. Reading `request.working_query` there reports the
    raw Korean question while the system actually searched the derived English
    one -- the plugin would show the user a query that never ran, and the CLI's
    `english_query` field would be wrong in every stored result.
    """
    from curator.retrieval import QueryOrchestrator

    class _Client(_CountingClient):
        def chat(self, messages, *, json_mode: bool = False, temperature: float = 0.3) -> str:
            text = "\n".join(m.content for m in messages)
            if "search_query" in text or "INTENT" in text:
                return super().chat(messages, json_mode=json_mode, temperature=temperature)
            return json.dumps({
                "answer": "Residual connections ease optimization.",
                "source_span_ids": [],
                "used_report_ids": [],
                "confidence": 0.8,
            })

    result = QueryOrchestrator(_vault(tmp_path), _Client()).run(
        QueryRequest(question=KOREAN, mode="local")
    )
    assert result.english_query == "vault themes overview", (
        f"orchestrator reported {result.english_query!r}, not the query it ran"
    )


def test_a_caller_supplied_english_query_is_never_overwritten(tmp_path: Path) -> None:
    """Regression: the first cut of the gate checked only `english_query_status`,
    and silently discarded a query the caller had already provided.

    `plugin_api/query_api.py` accepts an `english_query` argument from the
    plugin's language bridge and does not set a status alongside it. With a
    Korean `question` the funnel saw `status == "unset"`, derived, and threw the
    caller's English query away -- replacing a translation the boundary had
    already made with a second, different one, for an extra 12-50 s.

    Caught by CI, not by the six tests I wrote first: every one of them left
    `english_query` empty.
    """
    client = _CountingClient()
    response = _fetch(
        _vault(tmp_path), KOREAN, client, english_query="what does this concept mean?"
    )
    assert client.calls == 0, "the caller's English query was thrown away"
    assert response["english_query"] == "what does this concept mean?"


def test_the_not_a_knowledge_question_verdict_is_not_thrown_away(tmp_path: Path) -> None:
    """v0.69.0 computed this in the funnel, paid for it, and read three of four
    fields.

    `derive_search_query` returns `is_knowledge_question=False` for a message
    like "이 문장을 번역해줘: <body>" — the case its own docstring exists to catch —
    and sets `search_query` to "". The funnel kept only `search_query`, `status`
    and `intent`, so `working_query` fell back to the raw body and retrieval ran
    BM25 over a translation request. Strictly worse than before the change: the
    classification is now bought and then discarded.

    The verdict is carried on the request and recorded in the trace. Retrieval is
    deliberately NOT vetoed here — that is a boundary judgement about what the
    user's message is, and silently zeroing `wiki query` from the retrieval layer
    was rejected when this was designed — but the fact is no longer invisible.
    """
    import json as _json

    class _NotAQuestion:
        model = "fake"

        def chat(self, messages, *, json_mode: bool = False, temperature: float = 0.3) -> str:
            # `intent` omitted, not empty: the contract's Literal rejects "" and
            # the whole response would fall back, losing the very verdict under
            # test. Omission defaults to "lookup", which is the documented
            # "model expressed no opinion" path.
            return _json.dumps({
                "search_query": "",
                "is_knowledge_question": False,
                "reason": "asks for something to be done to supplied text",
            })

    paths = _vault(tmp_path)
    response = _fetch(paths, "이 문장을 한글로 번역해줘: quick brown fox", _NotAQuestion())

    trace = db.get_query_trace(paths.state_db, response["trace_id"])
    assert trace is not None
    derivation = trace["retrieval_trace"]["context_service"]["derivation"]
    assert derivation["is_knowledge_question"] is False, (
        "the classification was computed, paid for, and discarded"
    )
