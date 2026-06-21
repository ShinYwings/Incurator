"""Vision extraction helpers (v0.22.0; SYSTEM_BEHAVIOR §26.2a).

Shared, transport-agnostic plumbing for turning a rendered page/region image into
clean LaTeX-bearing Markdown via a user-elected vision model. Two transports exist:

- Ollama: in-memory base64 over httpx (no disk; handled in ``llm.OllamaClient``).
- Agentic CLI (claude / agy / codex): the CLI reads a file path with its built-in
  vision tool, so the image MUST be written to a temp PNG. This module owns that
  temp-PNG lifecycle (location under the project ``.cache``, guaranteed cleanup) and
  the per-provider output normalization, so no client duplicates it.

Cloud vision here uses the CLI's *subscription* auth — never a provider API key.
"""

from __future__ import annotations

import re
import shutil
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

from . import config as cfg

__all__ = [
    "vision_render_dir",
    "sweep_stale_vision_dirs",
    "vision_temp_png",
    "normalize_vision_latex",
    "describe_image_via_cli",
    "render_pdf_pages",
    "PDF_LATEX_TRANSCRIBE_PROMPT",
]

# Bounded concurrency for page transcription (subprocess/httpx calls are blocking).
VISION_CONCURRENCY = 4

# Strict, output-only prompt. Region/page-scoped (NOT "parse the whole page").
PDF_LATEX_TRANSCRIBE_PROMPT = (
    "Transcribe ALL text and mathematics in this image to clean Markdown. "
    "Render every formula as LaTeX: inline math as $...$, display math as $$...$$. "
    "Preserve reading order. Output ONLY the transcription — no commentary, no "
    "explanations, no code fences, no summaries."
)


def vision_render_dir() -> Path:
    """Project-local temp dir for rendered page PNGs: ``<repo>/.cache/vision_render``.

    Lives beside ``.cache/config`` and ``.cache/models`` (``.cache/`` is gitignored),
    so no byproducts leak into the repo tree or ``~``.
    """
    return cfg.get_global_config_dir().parent / "vision_render"


def sweep_stale_vision_dirs() -> None:
    """Remove any leftover per-run subdirs from a previously killed run."""
    base = vision_render_dir()
    if not base.exists():
        return
    for child in base.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)


@contextmanager
def vision_temp_png(image_data: bytes, *, run_id: str | None = None) -> Generator[Path, None, None]:
    """Write ``image_data`` to a temp PNG under ``.cache/vision_render/<run-id>/``.

    The file (and its per-run subdir, if we created it) is removed in ``finally`` —
    guaranteed on success, exception, AND timeout. No temp PNG survives the call.
    """
    run = run_id or uuid.uuid4().hex[:12]
    run_dir = vision_render_dir() / run
    run_dir.mkdir(parents=True, exist_ok=True)
    png = run_dir / f"page-{uuid.uuid4().hex[:8]}.png"
    try:
        png.write_bytes(image_data)
        yield png
    finally:
        try:
            png.unlink()
        except OSError:
            pass
        # Best-effort: drop the run subdir if it is now empty.
        try:
            run_dir.rmdir()
        except OSError:
            pass


# Lines that agentic CLIs emit around the real transcription (banners/usage/etc.).
_CLI_NOISE_RE = re.compile(
    r"^\s*(?:codex|claude|agy|tokens?\s+used|usage|model:|thinking|"
    r"\[preferred model[^\]]*\]|\d[\d,]*)\s*$",
    re.IGNORECASE,
)


def normalize_vision_latex(text: str) -> str:
    """Strip CLI banners / fences / `$$` wrappers / commentary → clean transcription.

    Agentic CLIs vary: agy wraps lines in ``$$``, codex prepends a banner and a
    "tokens used" line and may echo unrelated context. Normalize to the actual
    LaTeX-bearing body. Conservative: only drops clearly-noise lines and fences.
    """
    if not text:
        return ""
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        # Drop opening/closing code fences entirely.
        if stripped.startswith("```"):
            continue
        # Drop standalone CLI banner / usage / numeric-only lines.
        if _CLI_NOISE_RE.match(stripped):
            continue
        out.append(line)
    result = "\n".join(out).strip()
    # Unwrap a single fully-$$-wrapped block if the whole thing is one wrapper.
    return result


def render_pdf_pages(
    file_path, *, dpi: int = 170, max_px: int = 1600
) -> list[bytes]:
    """Render each PDF page to bounded PNG bytes via PyMuPDF (in-memory, no disk).

    Renders at ``dpi``; if a page's longest edge would exceed ``max_px`` px, the zoom
    is lowered so the longest edge is capped (R14) — dense/large pages never exceed
    the vision model's image-payload/token limits. PyMuPDF (`fitz`) is already a dep.
    """
    import fitz

    out: list[bytes] = []
    doc = fitz.open(str(file_path))
    try:
        for i in range(doc.page_count):
            page = doc.load_page(i)
            zoom = dpi / 72.0
            rect = page.rect
            longest_pt = max(rect.width, rect.height) or 1.0
            if longest_pt * zoom > max_px:
                zoom = max_px / longest_pt
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            out.append(pix.tobytes("png"))
    finally:
        doc.close()
    return out


def describe_image_via_cli(
    image_data: bytes,
    prompt: str,
    run_with_image_path: Callable[[str, str], str],
    *,
    run_id: str | None = None,
) -> str:
    """Transcribe ``image_data`` by handing a temp PNG path to an agentic CLI.

    ``run_with_image_path(full_prompt, image_path)`` invokes the provider CLI (with
    its own subscription auth and file-Read tool) and returns raw stdout. We compose
    the path-referencing prompt, normalize the output, and guarantee temp cleanup.
    """
    with vision_temp_png(image_data, run_id=run_id) as png:
        full_prompt = (
            f"Read the image file at {png}. {prompt}"
        )
        raw = run_with_image_path(full_prompt, str(png))
    return normalize_vision_latex(raw)
