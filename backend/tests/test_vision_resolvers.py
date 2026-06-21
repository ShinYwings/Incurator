"""P3: vision client factory + resolver discipline + temp-PNG lifecycle (v0.22.0).

Covers SYSTEM_BEHAVIOR §26.2a invariants:
- R10: ingest's vision resolver NEVER selects `latex_extract_model`.
- R13: fallback advances ONLY on an empty slot; a configured-but-non-vision model RAISES.
- temp PNG is removed on success AND on exception; output normalization.
"""

import pytest

from curator import ingest_raw, llm, vision
from curator import config as cfg
from curator.llm import LLMError, OllamaClient


class _FakeClient:
    def __init__(self, vision_ok: bool, model: str = "m") -> None:
        self._v = vision_ok
        self.model = model

    @property
    def supports_vision(self) -> bool:
        return self._v


# --- make_client_for: independent client from an explicit provider::model ---

def test_make_client_for_builds_independent_ollama_client() -> None:
    c = llm.make_client_for("ollama::qwen2.5-vl:7b", cfg.DEFAULT_CONFIG)
    assert isinstance(c, OllamaClient)
    assert c.model == "qwen2.5-vl:7b"


def test_make_client_for_empty_is_none() -> None:
    assert llm.make_client_for("", cfg.DEFAULT_CONFIG) is None


# --- R13: fallback only on empty, raise on configured failure ---

def test_require_vision_raises_on_non_vision_and_none() -> None:
    with pytest.raises(LLMError):
        ingest_raw._require_vision(None, "vision_model")
    with pytest.raises(LLMError):
        ingest_raw._require_vision(_FakeClient(False), "vision_model")
    ok = _FakeClient(True, "vl")
    assert ingest_raw._require_vision(ok, "vision_model") is ok


def test_resolve_vision_empty_falls_through(monkeypatch) -> None:
    monkeypatch.setattr(llm, "make_client_for", lambda pm, c: _FakeClient(True, pm))
    main_vis = _FakeClient(True, "main")
    # empty vision_model + vision-capable main → main
    assert ingest_raw._resolve_vision_client({"llm": {}}, main_vis) is main_vis
    # empty vision_model + non-vision main → None (pymupdf4llm)
    assert ingest_raw._resolve_vision_client({"llm": {}}, _FakeClient(False)) is None


def test_resolve_vision_configured_bad_raises(monkeypatch) -> None:
    monkeypatch.setattr(llm, "make_client_for", lambda pm, c: _FakeClient(False, pm))
    with pytest.raises(LLMError):
        ingest_raw._resolve_vision_client(
            {"llm": {"vision_model": "ollama::qwen2.5:7b"}}, _FakeClient(True, "main")
        )


# --- R10: ingest vision resolver never borrows latex_extract_model ---

def test_ingest_vision_resolver_ignores_latex_extract_model(monkeypatch) -> None:
    monkeypatch.setattr(llm, "make_client_for", lambda pm, c: _FakeClient(True, pm))
    # vision_model EMPTY, latex_extract_model SET, main not vision → None (NOT the
    # light model). Ingest must never pick latex_extract_model.
    out = ingest_raw._resolve_vision_client(
        {"llm": {"latex_extract_model": "ollama::small-vl"}}, _FakeClient(False)
    )
    assert out is None


def test_resolve_extract_falls_to_vision_chain_on_empty(monkeypatch) -> None:
    monkeypatch.setattr(llm, "make_client_for", lambda pm, c: _FakeClient(True, pm))
    main = _FakeClient(True, "main")
    # empty latex_extract_model + empty vision_model → main (vision chain)
    assert ingest_raw._resolve_extract_client({"llm": {}}, main) is main
    # configured latex_extract_model → that client
    c = ingest_raw._resolve_extract_client(
        {"llm": {"latex_extract_model": "x::y"}}, main
    )
    assert c.model == "x::y"


# --- temp-PNG lifecycle + output normalization ---

def test_vision_temp_png_cleaned_on_success() -> None:
    seen = {}
    with vision.vision_temp_png(b"\x89PNG\r\n", run_id="utest1") as png:
        seen["path"] = png
        assert png.exists()
    assert not seen["path"].exists()  # removed in finally


def test_vision_temp_png_cleaned_on_exception() -> None:
    captured = {}
    with pytest.raises(RuntimeError):
        with vision.vision_temp_png(b"data", run_id="utest2") as png:
            captured["path"] = png
            assert png.exists()
            raise RuntimeError("boom")
    assert not captured["path"].exists()  # cleaned even on exception


def test_normalize_strips_fences_and_cli_noise() -> None:
    raw = "```latex\nE = mc^2\n$$q_{47} = \\sqrt{1337}$$\ntokens used\n36,967\n```"
    out = vision.normalize_vision_latex(raw)
    assert "```" not in out
    assert "tokens used" not in out.lower()
    assert "36,967" not in out
    # Valid LaTeX (including display $$) is preserved.
    assert "E = mc^2" in out
    assert "q_{47} = \\sqrt{1337}" in out


def test_normalize_unwraps_single_dollar_dollar_wrapper() -> None:
    # A single fully-$$-wrapped block is unwrapped to avoid nested math delimiters.
    assert vision.normalize_vision_latex("$$E = mc^2$$") == "E = mc^2"
    assert vision.normalize_vision_latex("  $$  x + y  $$  ") == "x + y"
    # Mixed content with internal $$ is NOT unwrapped (would break the math).
    mixed = "$$a = 1$$ and $$b = 2$$"
    assert vision.normalize_vision_latex(mixed) == mixed
    # Multi-line wrapped block is unwrapped.
    assert vision.normalize_vision_latex("$$\nF = ma\n$$") == "F = ma"
