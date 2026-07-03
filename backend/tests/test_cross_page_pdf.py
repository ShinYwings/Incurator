"""
Tests for cross-page PDF lookup feature (v0.26.0):
  G08-1: db.get_source_row supports content_hash lookup
  G12-2: parse_page_window uses bounded pages= argument
  Page cache: cache-read/write logic (tested standalone, not through MCP closure)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from curator import db


# ─── G08-1: content_hash lookup in db.get_source_row ────────────────────────

class TestGetSourceRowByHash:
    def _seed_source(self, tmp_path: Path, content_hash: str) -> None:
        db.init_db(tmp_path / "state.sqlite")
        with db.connect(tmp_path / "state.sqlite") as conn:
            conn.execute(
                "INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("docs/paper.pdf", content_hash, "pdf", 1024, "2026-01-01T00:00:00"),
            )

    def test_lookup_by_content_hash(self, tmp_path: Path) -> None:
        chash = "abc123def456" * 4
        self._seed_source(tmp_path, chash)

        row = db.get_source_row(
            tmp_path / "state.sqlite",
            tmp_path,
            content_hash=chash,
        )
        assert row is not None
        assert row["relpath"] == "docs/paper.pdf"

    def test_lookup_by_hash_not_found(self, tmp_path: Path) -> None:
        db.init_db(tmp_path / "state.sqlite")
        row = db.get_source_row(
            tmp_path / "state.sqlite",
            tmp_path,
            content_hash="nonexistent",
        )
        assert row is None

    def test_relpath_tried_first_then_hash_fallback(self, tmp_path: Path) -> None:
        """Relpath is tried first; if it doesn't match, content_hash is used as fallback."""
        chash = "aabbcc" * 8
        self._seed_source(tmp_path, chash)
        # relpath doesn't exist in DB, so hash fallback should find the row
        row = db.get_source_row(
            tmp_path / "state.sqlite",
            tmp_path,
            relpath="nonexistent/path.pdf",
            content_hash=chash,
        )
        assert row is not None
        assert row["relpath"] == "docs/paper.pdf"

    def test_source_id_lookup_unchanged(self, tmp_path: Path) -> None:
        """Existing source_id lookup still works after G08-1 change."""
        chash = "feedfeed" * 8
        self._seed_source(tmp_path, chash)
        with db.connect(tmp_path / "state.sqlite") as conn:
            source_id = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        row = db.get_source_row(tmp_path / "state.sqlite", tmp_path, source_id=source_id)
        assert row is not None
        assert row["content_hash"] == chash


# ─── G12-2: parse_page_window bounded parse ─────────────────────────────────

class TestParsePageWindowBounded:
    def _make_fake_pymupdf(self, fake_chunks: list[dict]) -> MagicMock:
        mock = MagicMock()
        mock.to_markdown.return_value = fake_chunks
        return mock

    def test_pages_argument_passed_as_zero_based(self) -> None:
        """parse_page_window must forward a zero-based pages= list to pymupdf4llm."""
        fake_chunks: list[dict] = []  # empty — we only care that the arg was passed

        mock_pymupdf = self._make_fake_pymupdf(fake_chunks)
        with (
            patch.dict("sys.modules", {"pymupdf4llm": mock_pymupdf}),
            patch("curator.parsers.pdf._chunk_page_number", return_value=1),
        ):
            from curator.parsers.pdf import parse_page_window
            parse_page_window(Path("dummy.pdf"), {1, 5})

        call_kwargs = mock_pymupdf.to_markdown.call_args
        passed_pages = call_kwargs.kwargs.get("pages")
        assert passed_pages is not None, "pages= must be forwarded to pymupdf4llm"
        assert 0 in passed_pages, "page 1 → 0-based index 0"
        assert 4 in passed_pages, "page 5 → 0-based index 4"
        assert len(passed_pages) == 2, "only requested pages, nothing extra"
        assert call_kwargs.kwargs.get("use_ocr") is False

    def test_returns_empty_on_import_error(self) -> None:
        """Returns {} gracefully when pymupdf4llm is not installed."""
        with patch.dict("sys.modules", {"pymupdf4llm": None}):
            from curator.parsers.pdf import parse_page_window
            result = parse_page_window(Path("nonexistent.pdf"), {1})
        assert result == {}

    def test_out_of_range_pages_clamped_before_pymupdf(self) -> None:
        """Out-of-range page numbers are dropped before calling pymupdf4llm so a
        valid page in the same batch is not silently lost due to an exception."""
        import curator.parsers.pdf as pdf_mod

        fake_chunks = [{"metadata": {"page_number": 2}, "text": "valid page text"}]
        mock_pymupdf = self._make_fake_pymupdf(fake_chunks)

        # Patch directly on the already-loaded module to sidestep module-cache isolation.
        with (
            patch.dict("sys.modules", {"pymupdf4llm": mock_pymupdf}),
            patch.object(pdf_mod, "get_page_count", return_value=3),
            patch.object(pdf_mod, "_chunk_page_number", return_value=2),
        ):
            result = pdf_mod.parse_page_window(Path("dummy.pdf"), {2, 999})

        # Only page 2 (valid) should be passed to pymupdf4llm; page 999 must be excluded.
        call_kwargs = mock_pymupdf.to_markdown.call_args
        passed_pages = call_kwargs.kwargs.get("pages") or []
        assert 998 not in passed_pages, "page 999 (0-based 998) must be excluded by clamping"
        assert 1 in passed_pages, "page 2 (0-based 1) must be included"
        assert len(passed_pages) == 1, "only one valid page forwarded"
        assert 2 in result


# ─── Page cache: standalone cache logic ──────────────────────────────────────

def _run_cache_logic(
    paths_root: Path,
    hash_for_cache: str,
    req_page: int,
    req_end: int = 0,
    fetched_by_parse: dict[int, str] | None = None,
) -> dict:
    """Inline replica of the fast-path cache logic from fetch_document_section.
    Tests the cache read/write behaviour without going through the MCP closure."""
    pages_needed: set[int] = (
        set(range(req_page, req_end + 1)) if req_end >= req_page else {req_page}
    )
    cache_dir = paths_root / ".cache" / "pdf_pages" / hash_for_cache
    cached_pages: dict[int, str] = {}
    missing_pages: set[int] = set()
    for pn in pages_needed:
        cache_file = cache_dir / f"{pn}.txt"
        if cache_file.exists():
            cached_pages[pn] = cache_file.read_text(encoding="utf-8")
        else:
            missing_pages.add(pn)
    if missing_pages:
        fetched = fetched_by_parse or {}
        cache_dir.mkdir(parents=True, exist_ok=True)
        for pn, txt in fetched.items():
            (cache_dir / f"{pn}.txt").write_text(txt, encoding="utf-8")
            cached_pages[pn] = txt
    pages_text = [cached_pages.get(pn, "") for pn in sorted(pages_needed)]
    combined = "\n\n".join(t for t in pages_text if t)
    return {
        "text": combined,
        "context_source": "pdf_page_cache" if not missing_pages else "pdf_page_cache_partial",
        "cache_hits": sorted(cached_pages.keys() - missing_pages),
        "cache_misses": sorted(missing_pages),
    }


class TestPageCacheLogic:
    def test_cache_hit_returns_stored_text(self, tmp_path: Path) -> None:
        chash = "deadbeef" * 8
        cache_dir = tmp_path / ".cache" / "pdf_pages" / chash
        cache_dir.mkdir(parents=True)
        (cache_dir / "3.txt").write_text("cached page 3 content", encoding="utf-8")

        result = _run_cache_logic(tmp_path, chash, req_page=3)

        assert result["text"] == "cached page 3 content"
        assert result["context_source"] == "pdf_page_cache"
        assert 3 in result["cache_hits"]
        assert result["cache_misses"] == []

    def test_cache_miss_writes_and_returns_parsed_text(self, tmp_path: Path) -> None:
        chash = "cafecafe" * 8

        result = _run_cache_logic(
            tmp_path,
            chash,
            req_page=7,
            fetched_by_parse={7: "parsed page 7 text"},
        )

        assert result["text"] == "parsed page 7 text"
        assert 7 in result["cache_misses"]
        cache_file = tmp_path / ".cache" / "pdf_pages" / chash / "7.txt"
        assert cache_file.exists()
        assert cache_file.read_text() == "parsed page 7 text"

    def test_partial_cache_serves_hits_and_fetches_misses(self, tmp_path: Path) -> None:
        chash = "babe1234" * 8
        cache_dir = tmp_path / ".cache" / "pdf_pages" / chash
        cache_dir.mkdir(parents=True)
        (cache_dir / "5.txt").write_text("page 5 cached", encoding="utf-8")

        result = _run_cache_logic(
            tmp_path,
            chash,
            req_page=5,
            req_end=6,
            fetched_by_parse={6: "page 6 parsed"},
        )

        assert "page 5 cached" in result["text"]
        assert "page 6 parsed" in result["text"]
        assert result["context_source"] == "pdf_page_cache_partial"
        assert 5 in result["cache_hits"]
        assert 6 in result["cache_misses"]
