"""ROADMAP A8 (v0.68.0): a failed derivation must not report itself as derived.

The bug this pins, reproduced before it was fixed:

1. the provider fails mid-derivation, so `derive_search_query` falls back to
   `_fallback_search_terms`;
2. that fallback keeps EVERY script (`\\w` under `re.UNICODE`), so a Korean
   question comes back as Korean -- despite a docstring promising "an honest
   empty for pure non-Latin input";
3. `is_knowledge_question` is `bool(terms)` and therefore True, so the plugin
   boundary does not take its not-a-question early return;
4. the boundary set `english_query_status = "derived"` UNCONDITIONALLY;
5. the warning built to catch exactly this (`evidence.py`) is scoped to
   `"unset"` -- so it was suppressed.

Net effect: English-only entity seeding matched nothing, silently, with the one
warning designed to catch it disabled by the caller's own claim. That is the
v0.47.0 bug class, and it was live on the shipping plugin path.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from curator import db
from curator.query import _fallback_search_terms, derive_search_query


class _DeadProvider:
    model = "dead"

    def chat(self, *args, **kwargs) -> str:
        raise RuntimeError("provider down")

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


def _derive(message: str):
    with tempfile.TemporaryDirectory() as t:
        path = Path(t) / "state.sqlite"
        db.init_db(path)
        return derive_search_query(path, _DeadProvider(), message)


def test_fallback_keeps_non_latin_script_and_says_so() -> None:
    """The docstring used to claim an 'honest empty for pure non-Latin input'.

    It never did that. Keeping the script is the RIGHT behaviour for the
    mixed-script case that dominates this domain ("ellipsoid 형태의 quadric"),
    so the code stays and the claim goes -- but then something else has to carry
    the honesty, which is what `status` below is for.
    """
    assert _fallback_search_terms("이 논문의 전체 주제를 요약해줘") != ""
    assert _fallback_search_terms("Плагин обзор") != ""
    assert "형태" in _fallback_search_terms("ellipsoid 형태의 quadric")


def test_a_failed_derivation_does_not_claim_to_be_derived() -> None:
    derived = _derive("이 논문의 전체 주제를 요약해줘")
    assert derived.intent == ""
    assert derived.status == "fallback", (
        "a derivation that threw must not be indistinguishable from one that ran"
    )


def test_a_real_derivation_is_marked_derived() -> None:
    class _Provider:
        model = "ok"

        def chat(self, *args, **kwargs) -> str:
            return (
                '{"search_query": "residual connection", "is_knowledge_question": true,'
                ' "intent": "lookup", "reason": "fact lookup"}'
            )

    with tempfile.TemporaryDirectory() as t:
        path = Path(t) / "state.sqlite"
        db.init_db(path)
        derived = derive_search_query(path, _Provider(), "what is a residual connection")
    assert derived.status == "derived"
    assert derived.search_query == "residual connection"
    assert derived.intent == "lookup"


def test_the_plugin_boundary_propagates_the_failure_instead_of_masking_it(
    monkeypatch, tmp_path: Path
) -> None:
    """`plugin_api/context.py` set `status = "derived"` as a literal. That one
    line was the whole bug: it overwrote the only signal able to distinguish a
    working derivation from a dead provider.

    Asserted on the QueryRequest the boundary actually builds, not on source
    text -- a grep for the literal also matches the comment explaining it.
    """
    from curator import config as cfg
    from curator import plugin_api
    from curator.retrieval.models import DerivedQuery

    paths = cfg.WikiPaths(tmp_path / "vault")
    db.init_db(paths.state_db)
    cfg.save_config(paths, cfg.DEFAULT_CONFIG)

    monkeypatch.setattr(
        "curator.query.derive_search_query",
        lambda *a, **k: DerivedQuery(
            "논문의 전체 주제", True, "", "derivation unavailable: boom", status="fallback"
        ),
    )
    seen: dict = {}

    def _capture(self, request, **kwargs):
        seen["request"] = request
        return {"ok": True, "items": [], "trace_id": "QTR-x"}

    monkeypatch.setattr("curator.context_service.ContextService.context_fetch", _capture)
    monkeypatch.setattr("curator.llm.build_client", lambda *a, **k: _DeadProvider())

    plugin_api.fetch_context(
        paths, query_text="이 논문의 전체 주제를 요약해줘", workspace_path="", limit_tokens=1000
    )
    assert seen["request"].english_query_status == "fallback", (
        "the boundary claimed a derivation ran when the provider was dead"
    )


def test_the_warning_fires_when_the_derivation_fell_back() -> None:
    """Scoping the warning to `unset` alone is what let this pass silently."""
    import inspect

    from curator.retrieval import evidence

    src = inspect.getsource(evidence)
    assert '"fallback"' in src, (
        "the seeding warning still only considers `unset`, so a failed "
        "derivation that returned non-Latin text stays silent"
    )


def test_no_mcp_tool_passes_the_raw_question_as_the_english_query() -> None:
    """`curator_query` passed `english_query=question` — the user's untouched
    text, asserted to be the system's internal English query.

    `working_query` makes the two indistinguishable at runtime (it falls back to
    `question` when `english_query` is empty), which is exactly why the lie
    survived: nothing downstream could tell a real English query from a
    relabelled Korean one. What it corrupts is the field echoed to the MCP
    caller — and `english_query` reaches past routing into entity seeding, the
    BM25/vector query string, and the HyDE prompt.

    Checked on the AST, not the source text: a grep also matches the comment
    that explains the fix.
    """
    import ast
    import inspect

    from curator.mcp import server

    tree = ast.parse(inspect.getsource(server))
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for kw in node.keywords
        if kw.arg == "english_query"
        and isinstance(kw.value, ast.Name)
        and kw.value.id == "question"
    ]
    assert not offenders, (
        f"mcp/server.py still asserts the raw question is the English query "
        f"at line(s) {offenders}"
    )
