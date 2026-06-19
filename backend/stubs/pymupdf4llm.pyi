from pathlib import Path
from typing import Any

def to_markdown(
    doc: str | Path,
    *,
    page_chunks: bool = ...,
    write_images: bool = ...,
    image_path: str | None = ...,
    image_format: str = ...,
    **kwargs: Any,
) -> Any: ...
