"""Local file validator.

Returns a local mp4 path so the rest of the local pipeline can read it
directly off disk.
"""
import os
from pathlib import Path
from urllib.parse import unquote, urlparse
from typing import Optional


def _resolve_local_path(source: str) -> Optional[str]:
    """Return a local filesystem path if the input already points at one."""
    parsed = urlparse(source)
    if parsed.scheme == "file":
        raw_path = unquote(parsed.path)
        if parsed.netloc and parsed.netloc not in ("", "localhost"):
            raw_path = f"//{parsed.netloc}{raw_path}"
        candidate = Path(raw_path).expanduser()
        if candidate.exists() and candidate.is_file():
            return str(candidate.resolve())
        raise RuntimeError(f"Local file URL does not exist: {source}")

    if parsed.scheme in ("http", "https"):
        raise RuntimeError(f"Remote URLs are not supported, please provide a local file path: {source}")

    candidate = Path(source).expanduser()
    if candidate.exists() and candidate.is_file():
        return str(candidate.resolve())

    raise RuntimeError(f"Local file path does not exist: {source}")


def download_youtube_local(video_url: str) -> str:
    """Validate a local file path and return it unchanged."""
    local_path = _resolve_local_path(video_url)
    if local_path:
        print(f"[download/local] using local file: {local_path}", flush=True)
        return local_path
    
    raise RuntimeError("Failed to resolve local file path.")
