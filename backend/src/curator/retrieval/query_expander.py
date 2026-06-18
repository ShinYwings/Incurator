"""Tier-2 LLM query expander for v0.3.2 DB-native search.

Turns one natural-language question into typed expansion signals the engine fuses
via RRF: extra lexical paraphrase terms, extra vector probe queries, and a HyDE
(hypothetical answer) document. This is the lever that lifts paraphrase-heavy
queries — recall is already near-complete from Tier-1 + vectors, so better
*phrasings* mostly help fine ranking.

Uses the configured chat LLM (`llm.build_client`). It is fully optional and
fail-safe: if disabled, the client cannot be built, or the call/parse fails, the
expander returns ``{}`` and the engine runs Tier-1 (deterministic) expansion only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, cast

from .. import config as cfg

__all__ = ["LlamaCppExpander", "build_query_expander"]

_SYSTEM = (
    "You rewrite a search query into expansion signals for a hybrid retriever. "
    "Return STRICT JSON with keys: "
    '"lex" (2-4 short keyword/synonym phrases for lexical search), '
    '"vec" (1-2 alternative full-sentence paraphrases of the query), '
    '"hyde" (one concise hypothetical answer paragraph, <= 60 words). '
    "No commentary, JSON only."
)


def _coerce_list(value: object, limit: int) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        s = str(item).strip()
        if s and s not in out:
            out.append(s)
    return out[:limit]


_QMD_GRAMMAR = r"""
root ::= line+
line ::= type ": " content "\n"
type ::= "lex" | "vec" | "hyde"
content ::= [^\n]+
"""


def _query_terms(raw: str) -> list[str]:
    return re.sub(r"[^a-z0-9\s]", " ", raw.lower()).split()


def _contains_query_term(text: str, terms: list[str]) -> bool:
    if not terms:
        return True
    low = text.lower()
    return any(term in low for term in terms)


def _parse_qmd_lines(raw: str, query: str) -> dict:
    """Parse qmd's structured ``type: text`` expansion format.

    qmd filters generated lines that contain none of the original ASCII query
    terms, then falls back to original-query probes if the model produced no
    usable structured lines. This mirrors that behavior so the benchmark is an
    apples-to-apples expander comparison.
    """
    terms = _query_terms(query)
    lex: list[str] = []
    vec: list[str] = []
    hyde: list[str] = []
    for line in raw.strip().splitlines():
        kind, sep, text = line.partition(":")
        if not sep:
            continue
        kind = kind.strip()
        text = text.strip()
        if kind not in {"lex", "vec", "hyde"} or not text:
            continue
        if not _contains_query_term(text, terms):
            continue
        if kind == "lex" and text not in lex:
            lex.append(text)
        elif kind == "vec" and text not in vec:
            vec.append(text)
        elif kind == "hyde" and text not in hyde:
            hyde.append(text)

    if not (lex or vec or hyde):
        lex = [query]
        vec = [query]
        hyde = [f"Information about {query}"]

    return {
        "lex_terms": lex[:4],
        "vec_texts": vec[:2],
        "hyde_text": hyde[0] if hyde else "",
    }


class LlamaCppExpander:
    """qmd-compatible local GGUF query expander via llama-cpp-python.

    qmd's fine-tuned expander emits grammar-constrained lines:
    ``lex: ...``, ``vec: ...``, and ``hyde: ...``. This class uses the same prompt,
    decoding shape, parser, and fallback policy closely enough for parity
    measurement while staying optional for product runtime.
    """

    provider = "llama-cpp"

    def __init__(
        self,
        model: str,
        model_path: str,
        *,
        n_ctx: int = 2048,
        _llm=None,
    ) -> None:
        self.model = model
        self.model_path = model_path
        self._grammar = None
        if _llm is None:
            from llama_cpp import Llama, LlamaGrammar  # lazy optional dependency

            self._llm = Llama(model_path=model_path, n_ctx=n_ctx, verbose=False)
            self._grammar = LlamaGrammar.from_string(_QMD_GRAMMAR)
        else:
            self._llm = _llm

    @property
    def fingerprint(self) -> str:
        return f"{self.provider}::{self.model}"

    def __call__(self, raw: str) -> dict:
        prompt = f"/no_think Expand this search query: {raw}"
        try:
            result = self._llm.create_completion(
                prompt=prompt,
                grammar=self._grammar,
                max_tokens=600,
                temperature=0.7,
                top_k=20,
                top_p=0.8,
                repeat_penalty=1.1,
            )
        except Exception:
            return {}
        try:
            completion = cast(dict[str, Any], result)
            text = str(completion["choices"][0]["text"])
        except Exception:
            return {}
        return _parse_qmd_lines(text, raw)


def build_query_expander(config: dict, *, want_hyde: bool = True) -> Callable[[str], dict] | None:
    """Build an LLM-backed expander callable, or None when unavailable/disabled.

    Gated by ``search.query_expansion`` (default True). The returned callable maps
    a raw query to ``{"lex_terms": [...], "vec_texts": [...], "hyde_text": "..."}``.
    """
    search_cfg = (config or {}).get("search", {})
    if not search_cfg.get("query_expansion", True):
        return None

    provider, _, model = str(search_cfg.get("query_expander") or "").partition("::")
    model_path = str(search_cfg.get("query_expander_model_path") or "").strip()
    if provider.strip() == "llama-cpp" and model_path and Path(model_path).exists():
        try:
            return LlamaCppExpander(model.strip() or "query-expander", model_path)
        except Exception:
            return None

    try:
        from .. import llm

        client = llm.build_client(config)
    except Exception:
        return None

    from ..llm import ChatMessage

    def _expander(raw: str) -> dict:
        try:
            content = client.chat(
                [ChatMessage(role="system", content=_SYSTEM),
                 ChatMessage(role="user", content=raw)],
                json_mode=True,
                temperature=0.1,
            )
        except Exception:
            return {}
        text = content.strip()
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            data = json.loads(text[start:end + 1])
        except Exception:
            return {}
        result: dict = {
            "lex_terms": _coerce_list(data.get("lex"), 4),
            "vec_texts": _coerce_list(data.get("vec"), 2),
        }
        if want_hyde:
            hyde = data.get("hyde")
            result["hyde_text"] = hyde.strip() if isinstance(hyde, str) else ""
        return result

    return _expander


# Re-exported for callers that only have paths.
def build_from_paths(paths) -> Callable[[str], dict] | None:  # pragma: no cover - thin wrapper
    return build_query_expander(cfg.load_config(paths))
