"""v0.3.2: Tier-2 LLM query expander (chat client mocked — no live LLM)."""

from __future__ import annotations

from unittest.mock import patch

from curator import llm
from curator.retrieval import query_expander


class _FakeClient:
    def __init__(self, payload: str):
        self._payload = payload

    def chat(self, messages, *, json_mode=False, temperature=0.3):
        return self._payload


def test_expander_parses_lex_vec_hyde():
    payload = '{"lex": ["cell metabolism", "ATP"], "vec": ["how cells produce energy"], "hyde": "Cells make ATP via respiration."}'
    with patch.object(llm, "build_client", return_value=_FakeClient(payload)):
        exp = query_expander.build_query_expander({"search": {}}, want_hyde=True)
    assert exp is not None
    out = exp("how do cells make energy")
    assert out["lex_terms"] == ["cell metabolism", "ATP"]
    assert out["vec_texts"] == ["how cells produce energy"]
    assert out["hyde_text"].startswith("Cells make ATP")


def test_expander_disabled_returns_none():
    assert query_expander.build_query_expander({"search": {"query_expansion": False}}) is None


def test_expander_none_when_client_build_fails():
    with patch.object(llm, "build_client", side_effect=RuntimeError("no backend")):
        assert query_expander.build_query_expander({"search": {}}) is None


def test_expander_failsafe_on_bad_json():
    with patch.object(llm, "build_client", return_value=_FakeClient("not json at all")):
        exp = query_expander.build_query_expander({"search": {}})
    assert exp("q") == {} or exp("q").get("lex_terms") == []


def test_expander_failsafe_on_chat_error():
    class _Boom:
        def chat(self, *a, **k):
            raise RuntimeError("llm down")

    with patch.object(llm, "build_client", return_value=_Boom()):
        exp = query_expander.build_query_expander({"search": {}})
    assert exp("q") == {}


def test_expander_omits_hyde_when_not_wanted():
    payload = '{"lex": ["x"], "vec": ["y"], "hyde": "z"}'
    with patch.object(llm, "build_client", return_value=_FakeClient(payload)):
        exp = query_expander.build_query_expander({"search": {}}, want_hyde=False)
    out = exp("q")
    assert "hyde_text" not in out
    assert out["lex_terms"] == ["x"] and out["vec_texts"] == ["y"]


def test_expander_integrates_with_expand():
    from curator.retrieval import expansion

    payload = '{"lex": ["paraphrase term"], "vec": ["alt query"], "hyde": "hypothetical answer"}'
    with patch.object(llm, "build_client", return_value=_FakeClient(payload)):
        exp = query_expander.build_query_expander({"search": {}}, want_hyde=True)
    eq = expansion.expand("original question", expander=exp, want_hyde=True)
    assert "paraphrase term" in eq.lex_terms_expanded
    assert "alt query" in eq.vec_texts
    assert eq.hyde_text == "hypothetical answer"


def test_llama_cpp_expander_parses_structured_lines():
    class _FakeLlama:
        def create_completion(self, **kwargs):
            return {
                "choices": [{
                    "text": (
                        "hyde: authentication setup explains configuring login providers.\n"
                        "lex: authentication setup login providers\n"
                        "vec: how to configure authentication setup for an app\n"
                    )
                }]
            }

    exp = query_expander.LlamaCppExpander(
        "structured-query-expansion-1.7b",
        "/unused/model.gguf",
        _llm=_FakeLlama(),
    )
    out = exp("authentication setup")
    assert out["lex_terms"] == ["authentication setup login providers"]
    assert out["vec_texts"] == ["how to configure authentication setup for an app"]
    assert out["hyde_text"].startswith("authentication setup")


def test_llama_cpp_expander_filters_off_topic_and_falls_back():
    class _FakeLlama:
        def create_completion(self, **kwargs):
            return {"choices": [{"text": "lex: unrelated weather\nvec: another topic\n"}]}

    exp = query_expander.LlamaCppExpander(
        "structured-query-expansion-1.7b",
        "/unused/model.gguf",
        _llm=_FakeLlama(),
    )
    out = exp("database crash recovery")
    assert out["lex_terms"] == ["database crash recovery"]
    assert out["vec_texts"] == ["database crash recovery"]
    assert out["hyde_text"] == "Information about database crash recovery"
