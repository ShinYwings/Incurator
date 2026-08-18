"""An interrupted vision run must keep the pages it already transcribed.

`vision_max_pages_per_run` caps one run and `vision_page_cache` skips pages
already done, so a long book is meant to be ingested across several runs — the
case that matters when a 673-page textbook cannot finish in one sitting.

That only holds if a page is cached when it completes. Until v0.58.0 the cache
was written in a single loop AFTER the whole `ThreadPoolExecutor` block, so a
run that never reached the end cached nothing at all. Measured: a 673-page book
transcribed for 26 minutes and left `vision_page_cache` exactly as it found it.

Note which failure this is. A provider error on one page is caught per page and
falls back to parser text, so the run still finishes and the old batch write
still ran — that path was never broken. What was broken is an interruption that
escapes that handler: Ctrl-C, a `SystemExit`, anything deriving from
`BaseException`. `ThreadPoolExecutor` captures those on the future and `ex.map`
re-raises them in the consuming loop, which aborted the function before the
batch write. So the discriminating test below interrupts with `KeyboardInterrupt`
— with the old code it leaves an empty cache, with the new code it leaves the
pages that finished.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from curator import db, ingest_raw

PAGES = 5
MODEL = "fake-vision"


def _cache_key(i: int) -> str:
    """Mirrors the hash the ingest path derives from a rendered page."""
    return hashlib.sha256(f"image-{i}".encode()).hexdigest()[:16]


def _cached(db_path: Path, i: int) -> str | None:
    return db.vision_cache_get(db_path, _cache_key(i), MODEL)


class FakeVisionClient:
    """Transcribes pages; optionally interrupts the run partway through.

    `interrupt_after` raises `KeyboardInterrupt` — a `BaseException`, so it goes
    straight past the per-page `except Exception` and aborts the whole run, the
    way Ctrl-C on a multi-hour ingest does.
    """

    model = MODEL
    supports_concurrent_calls = False

    def __init__(self, interrupt_after: int | None = None) -> None:
        self.calls = 0
        self.interrupt_after = interrupt_after

    def describe_image(self, image: bytes, prompt: str = "") -> str:
        self.calls += 1
        if self.interrupt_after is not None and self.calls > self.interrupt_after:
            raise KeyboardInterrupt
        return f"page text {self.calls}"


def _parsed(page_count: int) -> SimpleNamespace:
    return SimpleNamespace(
        text="",
        metadata={
            "pdf_pages": [{"text": f"parser text {i}"} for i in range(page_count)]
        },
    )


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "state.sqlite"
    db.init_db(p)
    return p


@pytest.fixture(autouse=True)
def _fake_render(monkeypatch: pytest.MonkeyPatch) -> None:
    """Render is irrelevant here; distinct bytes give distinct cache keys."""
    from curator import vision

    monkeypatch.setattr(
        vision,
        "render_pdf_pages",
        lambda *_a, **_k: [f"image-{i}".encode() for i in range(PAGES)],
    )


def test_an_interrupted_run_keeps_what_it_finished(db_path: Path) -> None:
    """The claim the resumability docs rest on. Fails on a batched cache write."""
    client = FakeVisionClient(interrupt_after=2)

    with pytest.raises(KeyboardInterrupt):
        ingest_raw._apply_vlm_pdf_extraction(
            _parsed(PAGES), Path("book.pdf"), client, {}, db_path
        )

    # The two pages that finished before the interrupt survived it...
    assert _cached(db_path, 0) is not None
    assert _cached(db_path, 1) is not None
    # ...and nothing beyond them, so the count is the whole claim: a write that
    # only runs after every page has finished leaves this at 0.
    assert sum(_cached(db_path, i) is not None for i in range(PAGES)) == 2


def test_the_next_run_only_transcribes_what_is_missing(db_path: Path) -> None:
    """What the surviving cache buys: the second run does not redo page 1."""
    first = FakeVisionClient(interrupt_after=2)
    with pytest.raises(KeyboardInterrupt):
        ingest_raw._apply_vlm_pdf_extraction(
            _parsed(PAGES), Path("book.pdf"), first, {}, db_path
        )

    second = FakeVisionClient()
    ingest_raw._apply_vlm_pdf_extraction(
        _parsed(PAGES), Path("book.pdf"), second, {}, db_path
    )
    # Only the three never cached are re-attempted — this is what makes a
    # 673-page book ingestible across several runs.
    assert second.calls == PAGES - 2
    assert all(_cached(db_path, i) is not None for i in range(PAGES))


def test_a_run_that_completes_caches_every_page(db_path: Path) -> None:
    """Baseline: the uninterrupted path still caches everything it transcribed."""
    client = FakeVisionClient()
    ingest_raw._apply_vlm_pdf_extraction(
        _parsed(PAGES), Path("book.pdf"), client, {}, db_path
    )
    assert all(_cached(db_path, i) is not None for i in range(PAGES))
