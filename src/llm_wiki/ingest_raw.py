"""Raw ingest: parse source files, register in the state DB, generate L1 Summaries.

This module handles the `wiki sync` phase:
  1. Discover files in raw_dirs (02_Wiki, 03_Notes, 04_Resources, 06_Archives)
  2. Register each file in the `sources` table with a content hash
  3. Generate an L1 Summary page in `.curator/Collections/01_Summaries/`
     using a single LLM pass (Pass 0)

No L2/L3/L4 processing happens here — that is `wiki ingest` (ingest_llm.py).
"""

from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable

from . import config as cfg
from . import db
from . import parsers


class AddResult(str, Enum):
    ADDED = "added"
    DEDUPED = "deduped"
    SKIPPED_EMPTY = "skipped_empty"
    SKIPPED_UNSUPPORTED = "skipped_unsupported"
    ERROR = "error"


@dataclass
class AddOutcome:
    """Result of attempting to add a single file."""

    result: AddResult
    source_path: Path              # Where the file ended up (or original on error)
    relpath: str                   # Relative to project root
    title: str | None = None
    file_type: str | None = None
    bytes: int = 0
    word_count: int = 0
    content_hash: str | None = None
    source_id: int | None = None   # Row ID in sources table
    summary_id: str | None = None  # SUM-UUID for L1 summary page
    message: str = ""              # Human-friendly explanation

    @property
    def ok(self) -> bool:
        return self.result == AddResult.ADDED

    @property
    def is_warning(self) -> bool:
        return self.result in {
            AddResult.DEDUPED,
            AddResult.SKIPPED_EMPTY,
            AddResult.SKIPPED_UNSUPPORTED,
        }


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _generate_id(prefix: str) -> str:
    """Generate a prefixed UUID4, e.g. 'SUM-a1b2c3d4'."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _is_inside_raw(path: Path, raw_dirs: list[Path]) -> bool:
    """True if `path` is already inside one of the project's raw directories."""
    path = path.resolve()
    for d in raw_dirs:
        try:
            path.relative_to(d.resolve())
            return True
        except ValueError:
            pass
    return False


# ---------------------------------------------------------------------------
# L1 Summary generation (Pass 0)
# ---------------------------------------------------------------------------


MAX_SUMMARY_CHARS = 35_000  # ~8.5K tokens
MAX_IMAGES_PER_DOC = 5     # cap vision calls per document


def _resolve_image_link(raw_link: str, source_file: Path, vault_root: Path) -> Path | None:
    """Resolve a raw image link string to an absolute path.

    Tries vault-root-relative first (Obsidian style: "05_Assets/foo.png"),
    then source-file-relative (standard Markdown: "../images/foo.png").
    """
    candidate = vault_root / raw_link
    if candidate.exists():
        return candidate
    candidate = source_file.parent / raw_link
    if candidate.exists():
        return candidate
    return None


def _describe_images_with_vision(
    client,
    images: list[bytes],
    context: str,
) -> list[str]:
    """Describe a list of images using the client's vision capability.

    Returns a list of description strings (one per image). Skips silently on
    failure so the overall ingest is not aborted by a bad image.
    """
    from . import prompts

    descriptions: list[str] = []
    msgs = prompts.build_image_description_messages(context=context)
    vision_prompt = msgs[-1].content  # the user turn text

    for img_data in images:
        try:
            desc = client.describe_image(img_data, prompt=vision_prompt)
            if desc:
                descriptions.append(desc)
        except Exception as e:
            print(f"    [Warn] Vision inference failed: {e}")
    return descriptions


def _extract_json_object(text: str) -> str:
    """Find the first top-level {...} block in text."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n", 1)
        if len(lines) == 2:
            text = lines[1]
        if text.rstrip().endswith("```"):
            text = text.rsplit("```", 1)[0]
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def _chunk_text(text: str, chunk_size: int = 30000, overlap: int = 2500) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += chunk_size - overlap
    return chunks


def _build_vision_client(config: dict, main_client):
    """Return a vision-capable OllamaClient for image inference.

    Resolution order:
    1. config.llm.vision_model set → dedicated OllamaClient for that model
    2. main_client supports vision → reuse main_client
    3. None (image inference disabled)
    """
    from .llm import OllamaClient, DEFAULT_OLLAMA_HOST

    llm_cfg = config.get("llm", {})
    vision_model = llm_cfg.get("vision_model", "").strip()
    if vision_model:
        return OllamaClient(
            host=llm_cfg.get("host", DEFAULT_OLLAMA_HOST),
            model=vision_model,
        )
    if getattr(main_client, "supports_vision", False):
        return main_client
    return None


def generate_l1_summary(
    paths: cfg.WikiPaths,
    source_id: int,
    relpath: str,
    content_hash: str,
    client,  # LLM client (OllamaClient or GeminiClient)
    *,
    config: dict | None = None,
    existing_summary_id: str | None = None,
    thinking: bool = False,
) -> str | None:
    """Generate an L1 Summary page for a source file.

    Returns the SUM-UUID if successful, None on failure.
    The page is written to `.curator/Collections/01_Summaries/<SUM-UUID>.md`.
    """
    from . import prompts

    file_path = paths.root / relpath
    if not file_path.exists():
        print(f"  [Error] File does not exist at: {file_path}")
        return None

    try:
        parsed = parsers.parse(file_path)
    except Exception as e:
        print(f"  [Error] Parsing file failed for {relpath}: {e}")
        return None

    vision_client = _build_vision_client(config or {}, client)
    has_vision = vision_client is not None

    # --- Vision: describe standalone image files ---
    if parsed.file_type == "image":
        if has_vision:
            try:
                img_data = file_path.read_bytes()
                descs = _describe_images_with_vision(vision_client, [img_data], context=parsed.title)
                source_text = f"[Image: {file_path.name}]\n\n" + (descs[0] if descs else "")
            except Exception as e:
                print(f"  [Warn] Could not describe image {relpath}: {e}")
                source_text = f"[Image: {file_path.name}] — vision inference unavailable"
        else:
            print(
                f"  [Info] Skipping image inference for {relpath}: "
                f"model '{getattr(client, 'model', '?')}' does not support vision. "
                f"Configure a vision model via llm.vision_model in config.yml "
                f"(e.g. gemma4:31b-it, gemma3:12b, llava:latest, qwen2.5-vl:7b)."
            )
            source_text = f"[Image: {file_path.name}] — no vision model configured"
    else:
        source_text = parsed.text

        # --- Vision: describe images linked from markdown documents ---
        if parsed.linked_images and has_vision:
            img_bytes: list[bytes] = []
            img_names: list[str] = []
            for raw_link in parsed.linked_images[:MAX_IMAGES_PER_DOC]:
                img_path = _resolve_image_link(raw_link, file_path, paths.root)
                if img_path:
                    try:
                        img_bytes.append(img_path.read_bytes())
                        img_names.append(img_path.name)
                    except OSError:
                        pass
            if img_bytes:
                print(f"  [Info] Describing {len(img_bytes)} linked image(s) via vision…")
                descs = _describe_images_with_vision(vision_client, img_bytes, context=parsed.title)
                if descs:
                    img_section = "\n\n".join(
                        f"**[Image: {name}]**\n{desc}"
                        for name, desc in zip(img_names, descs)
                    )
                    source_text = source_text + "\n\n## Embedded Images\n\n" + img_section

        # --- Vision: describe images embedded in PDFs ---
        pdf_images = parsed.metadata.get("pdf_images", [])
        if pdf_images and has_vision:
            pdf_img_bytes = [img["data"] for img in pdf_images[:MAX_IMAGES_PER_DOC]]
            if pdf_img_bytes:
                print(f"  [Info] Describing {len(pdf_img_bytes)} PDF image(s) via vision…")
                descs = _describe_images_with_vision(
                    vision_client, pdf_img_bytes, context=parsed.title
                )
                if descs:
                    pdf_section = "\n\n".join(
                        f"**[PDF Image, Page {pdf_images[i]['page']}]**\n{desc}"
                        for i, desc in enumerate(descs)
                    )
                    source_text = source_text + "\n\n## PDF Figures\n\n" + pdf_section

    chunk_size = getattr(client, "optimal_chunk_chars", 30000)
    
    if len(source_text) <= chunk_size + 5000:
        chunks = [source_text]
    else:
        overlap = min(2500, int(chunk_size * 0.1))
        chunks = _chunk_text(source_text, chunk_size=chunk_size, overlap=overlap)

    all_summaries = []
    all_key_claims = []
    all_atom_candidates = []
    all_tags = []
    domain = None
    title = parsed.title

    if len(chunks) > 1:
        print(f"  [Info] Text is long ({len(source_text)} chars). Processing in {len(chunks)} chunk(s).")

    from .llm import LLMError

    for idx, chunk in enumerate(chunks, 1):
        if len(chunks) > 1:
            print(f"    -> Summarizing chunk {idx}/{len(chunks)}...")
        messages = prompts.build_summary_messages(parsed.title, chunk)

        try:
            raw_response = client.chat(
                messages,
                thinking=thinking,
                json_mode=True,
                temperature=0.2,
            )
        except LLMError as e:
            print(f"  [Error] LLM chat failed for chunk {idx}: {e}")
            return None

        # Parse JSON
        json_str = _extract_json_object(raw_response)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # Retry without thinking
            try:
                retry_messages = prompts.build_summary_retry_messages(
                    parsed.title, chunk, raw_response
                )
                raw_response = client.chat(retry_messages, thinking=False, json_mode=True, temperature=0.1)
                json_str = _extract_json_object(raw_response)
                data = json.loads(json_str)
            except (json.JSONDecodeError, LLMError) as e:
                print(f"  [Error] Failed to parse summary JSON after retry for chunk {idx}: {e}")
                return None

        summary_val = data.get("summary")
        if summary_val:
            if isinstance(summary_val, str):
                all_summaries.append(summary_val)
            else:
                all_summaries.append(json.dumps(summary_val, indent=2, ensure_ascii=False))
        all_key_claims.extend(data.get("key_claims", []))
        all_atom_candidates.extend(data.get("atom_candidates", []))
        all_tags.extend(data.get("tags", []))
        if not domain and data.get("domain"):
            domain = data["domain"]
        if data.get("title") and len(data["title"]) > 5:
            title = data["title"]

    # Deduplicate claims and candidates
    seen_claims = set()
    unique_key_claims = []
    for claim in all_key_claims:
        clean = claim.strip()
        if clean and clean not in seen_claims:
            seen_claims.add(clean)
            unique_key_claims.append(clean)

    seen_atoms = set()
    unique_atom_candidates = []
    for c in all_atom_candidates:
        name = c.get("name", "").strip()
        if name and name not in seen_atoms:
            seen_atoms.add(name)
            unique_atom_candidates.append(c)

    unique_tags = list(set(tag.strip() for tag in all_tags if tag.strip()))

    combined_summary = "\n\n".join(all_summaries) if all_summaries else ""

    summary_id = existing_summary_id or _generate_id("SUM")
    today = _now_iso()

    candidates_text = "\n".join(
        f"- [{c.get('type', 'fact')}] {c.get('name', '')}: {c.get('one_liner', '')}"
        for c in unique_atom_candidates
    )
    key_claims_text = "\n".join(f"- {c}" for c in unique_key_claims)

    page_content = (
        f"---\n"
        f"id: {summary_id}\n"
        f"type: summary\n"
        f"source_path: \"[[{relpath}]]\"\n"
        f"source_hash: {content_hash}\n"
        f"domain: \"{domain or 'general'}\"\n"
        f"last_updated: {today}\n"
        f"tags: {json.dumps(unique_tags)}\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"## Summary\n\n"
        f"{combined_summary}\n\n"
        f"## Key Claims\n\n"
        f"{key_claims_text}\n\n"
        f"## Atom Candidates\n\n"
        f"{candidates_text}\n\n"
        f"## Source\n\n"
        f"- Path: `{relpath}`\n"
        f"- Hash: `{content_hash[:16]}…`\n"
        f"- Ingested: {today}\n"
    )

    # Write the L1 summary page
    paths.summaries.mkdir(parents=True, exist_ok=True)
    summary_path = paths.summaries / f"{summary_id}.md"
    summary_path.write_text(page_content, encoding="utf-8")

    # Record summary_id in DB
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE sources SET summary_id = ? WHERE id = ?",
            (summary_id, source_id),
        )

    return summary_id


# ---------------------------------------------------------------------------
# Core file registration
# ---------------------------------------------------------------------------


def add_file(
    paths: cfg.WikiPaths,
    source: Path,
) -> AddOutcome:
    """Add a single file to the tracking DB. Does not generate L1 summary.

    L1 summary generation requires an LLM client — call `generate_l1_summary()`
    separately after this returns `AddResult.ADDED`.
    """
    source = source.expanduser().resolve()

    # Guard: file must exist
    if not source.exists() or not source.is_file():
        return AddOutcome(
            result=AddResult.ERROR,
            source_path=source,
            relpath=str(source),
            message=f"File not found: {source}",
        )

    # Guard: file type must be supported
    if not parsers.is_supported(source):
        return AddOutcome(
            result=AddResult.SKIPPED_UNSUPPORTED,
            source_path=source,
            relpath=str(source),
            message=f"Unsupported file type: {source.suffix or '(no extension)'}",
        )

    # Guard: must be inside one of raw_dirs but NOT in collections
    in_raw = _is_inside_raw(source, paths.raw_dirs)
    try:
        source.relative_to(paths.collections.resolve())
        in_raw = False
    except ValueError:
        pass

    if not in_raw:
        return AddOutcome(
            result=AddResult.SKIPPED_UNSUPPORTED,
            source_path=source,
            relpath=str(source),
            message=(
                f"File is outside allowed raw directories or inside "
                f".curator/Collections: {source}"
            ),
        )

    # Parse
    try:
        parsed = parsers.parse(source)
    except parsers.ParserError as e:
        return AddOutcome(
            result=AddResult.ERROR,
            source_path=source,
            relpath=str(source),
            message=f"Parse failed: {e}",
        )

    try:
        relpath = str(source.relative_to(paths.root))
    except ValueError:
        relpath = str(source)

    with db.connect(paths.state_db) as conn:
        existing = conn.execute(
            "SELECT id, relpath, content_hash, summary_id FROM sources WHERE relpath = ?",
            (relpath,),
        ).fetchone()

        if existing is not None:
            if existing["content_hash"] == parsed.content_hash:
                return AddOutcome(
                    result=AddResult.DEDUPED,
                    source_path=source,
                    relpath=relpath,
                    title=parsed.title,
                    file_type=parsed.file_type,
                    bytes=parsed.bytes,
                    word_count=parsed.word_count,
                    content_hash=parsed.content_hash,
                    source_id=existing["id"],
                    summary_id=existing["summary_id"],
                    message=f"Already tracked and unmodified: #{existing['id']}",
                )
            else:
                # Content changed — reset to pending, clear summary
                conn.execute(
                    "UPDATE sources SET content_hash = ?, bytes = ?, status = 'pending', "
                    "last_ingested = NULL, summary_id = NULL WHERE id = ?",
                    (parsed.content_hash, parsed.bytes, existing["id"]),
                )
                return AddOutcome(
                    result=AddResult.ADDED,
                    source_path=source,
                    relpath=relpath,
                    title=parsed.title,
                    file_type=parsed.file_type,
                    bytes=parsed.bytes,
                    word_count=parsed.word_count,
                    content_hash=parsed.content_hash,
                    source_id=existing["id"],
                    message=f"Updated #{existing['id']} (content changed)",
                )

        # Near-empty check (likely scanned PDF)
        if parsed.is_empty:
            status = "error"
            message = (
                f"Extracted only {parsed.word_count} words — likely a scanned "
                f"PDF or empty file. OCR not yet supported."
            )
            result_kind = AddResult.SKIPPED_EMPTY
        else:
            status = "pending"
            message = f"Added as #?: {parsed.title}"
            result_kind = AddResult.ADDED

        cur = conn.execute(
            """
            INSERT INTO sources (relpath, content_hash, file_type, bytes, added_at, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                relpath,
                parsed.content_hash,
                parsed.file_type,
                parsed.bytes,
                _now_iso(),
                status,
            ),
        )
        source_id = cur.lastrowid
        message = message.replace("#?", f"#{source_id}")

    return AddOutcome(
        result=result_kind,
        source_path=source,
        relpath=relpath,
        title=parsed.title,
        file_type=parsed.file_type,
        bytes=parsed.bytes,
        word_count=parsed.word_count,
        content_hash=parsed.content_hash,
        source_id=source_id,
        message=message,
    )


def iter_addable_files(root: Path, recursive: bool) -> Iterable[Path]:
    """Yield every supported file at or under `root`."""
    root = root.expanduser().resolve()
    if not root.exists():
        return
    if root.is_file():
        if parsers.is_supported(root):
            yield root
        return
    if root.is_dir():
        iterator = root.rglob("*") if recursive else root.iterdir()
        for child in iterator:
            if child.is_file() and not child.name.startswith(".") and parsers.is_supported(child):
                yield child


# ---------------------------------------------------------------------------
# DB query helpers
# ---------------------------------------------------------------------------


def list_sources(
    paths: cfg.WikiPaths, status_filter: str | None = None
) -> list[dict]:
    """Return all tracked sources as a list of dicts, ordered by id."""
    query = "SELECT * FROM sources"
    params: tuple = ()
    if status_filter:
        query += " WHERE status = ?"
        params = (status_filter,)
    query += " ORDER BY id ASC"

    with db.connect(paths.state_db) as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def get_source(paths: cfg.WikiPaths, source_id: int) -> dict | None:
    """Fetch a single source row by id."""
    with db.connect(paths.state_db) as conn:
        row = conn.execute(
            "SELECT * FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
        return dict(row) if row else None


def mark_source_pending(
    paths: cfg.WikiPaths, source_id: int
) -> tuple[bool, str]:
    """Reset a source's status to 'pending' so it can be re-ingested."""
    row = get_source(paths, source_id)
    if row is None:
        return False, f"No source with id {source_id}"

    file_path = paths.root / row["relpath"]
    if not file_path.exists():
        return False, f"Source file no longer on disk: {row['relpath']}"

    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE sources SET status = 'pending', last_ingested = NULL, "
            "summary_id = NULL WHERE id = ?",
            (source_id,),
        )
        conn.commit()

    return True, f"Marked #{source_id} ({row['relpath']}) as pending"


def remove_source(
    paths: cfg.WikiPaths, source_id: int, delete_file: bool = True
) -> tuple[bool, str]:
    """Remove a source from tracking."""
    row = get_source(paths, source_id)
    if row is None:
        return False, f"No source with id {source_id}"

    file_path = paths.root / row["relpath"]

    with db.connect(paths.state_db) as conn:
        conn.execute("DELETE FROM source_pages WHERE source_id = ?", (source_id,))
        conn.execute("DELETE FROM ingest_runs WHERE source_id = ?", (source_id,))
        conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))

    deleted_file = False
    if delete_file and file_path.exists() and _is_inside_raw(file_path, paths.raw_dirs):
        try:
            file_path.unlink()
            deleted_file = True
        except OSError as e:
            return True, f"Removed #{source_id} from DB but failed to delete file: {e}"

    msg = f"Removed #{source_id} ({row['relpath']})"
    if deleted_file:
        msg += " — file deleted from raw dirs"
    elif delete_file:
        msg += " — file was outside raw dirs, left in place"
    return True, msg
