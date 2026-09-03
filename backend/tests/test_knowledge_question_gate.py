"""`is_knowledge_question` has three states, and only one of them refuses.

The field was `bool = True`, so a message nobody had classified ASSERTED that
retrieval was wanted. These tests pin the three states, the fallback case that a
naive gate would have turned into a silent wrong answer, and the truthiness
footgun that `None` introduces.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from curator.retrieval import QueryRequest

SRC = Path(__file__).resolve().parents[1] / "src" / "curator"


def test_the_field_defaults_to_nobody_looked() -> None:
    """The default must not claim a verdict. This default WAS the bug."""
    assert QueryRequest(question="anything").is_knowledge_question is None


def _adopted_verdict(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, derived) -> bool | None:
    """What the REAL funnel records after `derive_search_query` returns `derived`.

    Not a hand copy of the ternary. The first cut of this test defined a local
    `adopt()` closure and asserted on that; a reviewer stripped the
    `status == "derived"` guard out of `context_service.py` and all 33 related
    tests still passed. A test that re-implements the branch it checks proves
    nothing about the branch.
    """
    from curator import context_service as cs
    from curator import query as query_mod

    paths = _seed_context_vault(tmp_path)
    monkeypatch.setattr(query_mod, "derive_search_query", lambda *a, **k: derived)

    class _Client:
        provider = "fake"
        model = "fake"

        def chat(self, messages, *, json_mode: bool = False, temperature: float = 0.3) -> str:
            return "{}"

    response = cs.ContextService(paths, _Client()).context_fetch(
        # Korean and no `english_query`, so the funnel's derivation gate fires.
        QueryRequest(question="이 문단이 무엇을 말하는지 알려줘", mode="local")
    )
    from curator import db

    trace = db.get_query_trace(paths.state_db, response["trace_id"])
    assert trace is not None
    return trace["retrieval_trace"]["context_service"]["derivation"]["is_knowledge_question"]


def test_a_derived_verdict_is_adopted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from curator.query import DerivedQuery

    assert _adopted_verdict(
        monkeypatch, tmp_path,
        DerivedQuery("", False, "", "not a knowledge question", status="derived"),
    ) is False


def test_a_fallback_guess_is_not_adopted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The provider failed, so nobody classified anything.

    `DerivedQuery(terms, bool(terms), ..., status="fallback")` carries a guess
    from whether scraping found terms. Adopting it would let a provider outage
    refuse retrieval for a real question.
    """
    from curator.query import DerivedQuery

    assert _adopted_verdict(
        monkeypatch, tmp_path,
        DerivedQuery("", bool(""), "", "derivation unavailable: boom", status="fallback"),
    ) is None


def test_the_fallback_really_can_scrape_a_maths_message_to_nothing() -> None:
    """The premise of the test above, measured rather than assumed."""
    from curator.query import _fallback_search_terms

    assert _fallback_search_terms("L^T M(Q)L = 0") == ""
    assert bool(_fallback_search_terms("L^T M(Q)L = 0")) is False
    # A real question still scrapes to something, so the guard is not vacuous.
    assert _fallback_search_terms("이 문단 번역해줘")


def _truthy_offenders(root: Path) -> list[str]:
    """Truthiness tests on the REQUEST's tri-state verdict.

    Scoped to `request`/`req` on purpose. THREE types carry a field of this
    name and only `QueryRequest`'s has three states:

    - `SearchQueryOutputV2.is_knowledge_question` — the LLM's parsed output,
      reached only after a successful parse, so `query.py`'s
      `if not parsed.is_knowledge_question:` is correct and must not be flagged.
    - `DerivedQuery.is_knowledge_question` — a plain `bool`, but NOT always a
      classification: on the provider-failure path it is `bool(terms)` scraped
      from the message. That is why the funnel adopts it only when
      `status == "derived"`.
    - `QueryRequest.is_knowledge_question` — can be `None`, and there truthiness
      collapses "classified no" with "nobody classified this".
    """
    bad = re.compile(
        r"if\s+not\s+(?:request|req)\.is_knowledge_question\b"
        r"|if\s+(?:request|req)\.is_knowledge_question\s*:"
    )
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if bad.search(line):
                offenders.append(f"{path.relative_to(root)}:{lineno}: {line.strip()}")
    return offenders


def test_knowledge_question_is_never_truthy_tested() -> None:
    """`None` is falsy, so `if not request.is_knowledge_question` would collapse
    "classified no" and "nobody classified this" into one branch and refuse
    retrieval for every ordinary English question on the CLI and MCP paths.

    A convention in a docstring does not survive a refactor; this does.
    """
    offenders = _truthy_offenders(SRC)
    assert not offenders, (
        "test `is_knowledge_question` with `is False` / `is True` / `is None`:\n"
        + "\n".join(offenders)
    )


def test_the_truthiness_guard_can_actually_fail(tmp_path: Path) -> None:
    """A guard that cannot fail is worse than no guard — it reports safety it
    never checked. v0.80.0 shipped one whose forward-scan window legitimately
    excused the violation it was meant to catch, and it took injecting a real
    violation elsewhere to notice. So inject one here.
    """
    (tmp_path / "surface.py").write_text(
        "def go(request):\n"
        "    if not request.is_knowledge_question:\n"
        "        return None\n"
    )
    assert _truthy_offenders(tmp_path) == ["surface.py:2: if not request.is_knowledge_question:"]

    # And it must not flag the legitimate `bool` carrier.
    (tmp_path / "surface.py").write_text(
        "def go(parsed):\n"
        "    if not parsed.is_knowledge_question:\n"
        "        return None\n"
    )
    assert _truthy_offenders(tmp_path) == []


def _seed_context_vault(tmp_path: Path):
    """Smallest vault ContextService will serve a local route from.

    A local copy, matching this repo's convention -- no test module imports
    another.
    """
    from curator import config as cfg
    from curator import db

    paths = cfg.WikiPaths(tmp_path / "vault")
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
    return paths


def _fetch(paths, verdict: bool | None) -> dict:
    """Through the REAL `context_fetch`, not a copy of its branch.

    The first cut of these tests defined a local `gate()` helper "the exact
    expression context_service uses" and asserted on that -- a hand copy, which
    proves nothing about the code. v0.79.0 shipped that same mistake and the
    review caught it here before merge.
    """
    from curator import context_service as cs

    return cs.ContextService(paths).context_fetch(
        QueryRequest(
            question="what does a residual connection do?",
            english_query="residual connection",
            english_query_status="derived",
            is_knowledge_question=verdict,
            mode="local",
        )
    )


def test_a_classified_no_returns_no_evidence_through_the_real_funnel(tmp_path: Path) -> None:
    paths = _seed_context_vault(tmp_path)
    response = _fetch(paths, False)

    assert response["items"] == []
    assert response["source_span_ids"] == []
    assert any("not a knowledge question" in w for w in response.get("warnings", []))


def test_an_unclassified_message_still_retrieves(tmp_path: Path) -> None:
    """`None` must behave exactly as before. Refusing on it would break every
    ordinary English question on the CLI and MCP paths, which never classify."""
    paths = _seed_context_vault(tmp_path)
    response = _fetch(paths, None)

    assert response["items"], "nobody classified it -- retrieval must still run"
    assert not any("not a knowledge question" in w for w in response.get("warnings", []))


def test_a_classified_yes_retrieves_too(tmp_path: Path) -> None:
    paths = _seed_context_vault(tmp_path)
    assert _fetch(paths, True)["items"]


def test_the_gate_expression_is_the_one_in_the_funnel() -> None:
    """Pin the source, so the test above cannot drift away from the code.

    A test that re-implements the branch it is checking proves nothing about the
    branch — v0.79.0 shipped exactly that mistake, asserting on a monkeypatched
    stand-in for the real materializer.
    """
    source = (SRC / "context_service.py").read_text()
    assert "if request.is_knowledge_question is False:" in source
    assert "if not request.is_knowledge_question" not in source


def test_the_refusal_pack_states_its_cause_and_names_no_mechanism() -> None:
    """The warning must say why retrieval was skipped, not which router ran.

    The first cut interpolated `request.intent` — the ROUTING intent that steers
    query expansion — and produced "no retrieval: lookup": a mechanism the
    reader never asked about, stated as if it were the cause.
    """
    source = (SRC / "context_service.py").read_text()
    assert '"no retrieval: not a knowledge question"' in source
    assert "no retrieval: {request.intent" not in source


def test_the_refusal_pack_does_not_leave_a_silent_hole_in_the_trace() -> None:
    """`build_evidence` always assigns an `RTR-` id; the refusal pack cannot.

    The context action list records `child_id: pack.retrieval_execution_id`, so
    a refusal writes a "retrieval" action pointing at nothing. That empty child
    is legitimate — no retrieval executed — but it must be explained rather than
    left for a reader to puzzle over.
    """
    from curator.retrieval import evidence as evidence_mod

    pack = evidence_mod.EvidencePack(
        route="local",
        warnings=["no retrieval: not a knowledge question"],
        retrieval_trace={"skipped": "not a knowledge question"},
    )
    assert pack.retrieval_execution_id == ""
    assert pack.retrieval_trace["skipped"] == "not a knowledge question"
    # And the funnel really builds it that way.
    source = (SRC / "context_service.py").read_text()
    assert '"skipped": "not a knowledge question"' in source


def test_a_provider_outage_does_not_empty_the_popover_pack(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The boundary the popover and sidechat actually use.

    `plugin_api.fetch_context` gated on `derived.is_knowledge_question` with no
    `status` check. On the provider-failure path that value is `bool(terms)`
    scraped from the message, and `_fallback_search_terms` drops single
    characters — so `L^T M(Q)L = 0` scraped to "", the guess became False, and a
    real question got an empty pack. v0.81.0's CHANGELOG claimed these surfaces
    were covered; they were not, and two review lenses reproduced it here.
    """
    from curator import llm
    from curator.plugin_api import context as context_api

    paths = _seed_context_vault(tmp_path)

    class _DeadClient:
        provider = "fake"
        model = "fake"

        def chat(self, *a, **k):
            raise RuntimeError("provider down")

        def __enter__(self):
            return self

        def __exit__(self, *exc) -> bool:
            return False

    monkeypatch.setattr(llm, "build_client", lambda *a, **k: _DeadClient())

    response = context_api.fetch_context(paths, query_text="L^T M(Q)L = 0")

    assert response["ok"] is True
    # Retrieval must still have run: nobody classified this, so nothing may
    # refuse it. The empty-pack refusal is reserved for a real "no".
    assert not any(
        "not a knowledge question" in w for w in response.get("warnings", [])
    ), response.get("warnings")
    assert "coverage" not in response or response["coverage"].get(
        "sufficiency"
    ) != "not_applicable", response.get("coverage")
