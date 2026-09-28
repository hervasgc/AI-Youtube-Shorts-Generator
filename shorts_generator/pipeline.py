"""End-to-end orchestrator.

Mode:
  * local — faster-whisper + OpenAI or Gemini + ffmpeg/opencv.
            Self-hosted, LLM_PROVIDER selects OpenAI or Gemini.
"""
import os
from typing import Dict, List, Optional

from .config import GCS_OUTPUT_BUCKET
from .local.clipper import crop_highlights_local
from .local.downloader import download_youtube_local
from .local.llm import call_local_llm
from .local.transcriber import transcribe_local
from .highlights import get_highlights


def generate_shorts(
    youtube_url: str,
    num_clips: int = 3,
    aspect_ratio: str = "9:16",
    language: Optional[str] = None,
) -> Dict:
    """Run the full pipeline and return a structured result.

    Args:
        youtube_url: local path to the source video.
        num_clips: how many shorts to render.
        aspect_ratio: e.g. "9:16", "1:1".
        language: ISO-639-1 to force Whisper language detection.

    Returns:
        {
          "mode": "local",
          "source_video_url": str,   # local path
          "transcript": {...},
          "highlights": [...],       # all candidates ranked
          "shorts": [...],           # top `num_clips` with clip_url / local path
        }
    """
    source_path = download_youtube_local(youtube_url)

    transcript = transcribe_local(source_path, language=language)
    if not transcript["segments"]:
        raise RuntimeError(
            "Whisper produced no segments. The video may have no detectable speech."
        )

    highlights_result = get_highlights(transcript, num_clips=num_clips, llm_fn=call_local_llm)
    all_highlights: List[Dict] = highlights_result.get("highlights", [])
    if not all_highlights:
        raise RuntimeError("Highlight generator returned zero clips.")

    top = sorted(all_highlights, key=lambda h: int(h.get("score", 0)), reverse=True)[:num_clips]
    print(f"[pipeline/local] cropping {len(top)} of {len(all_highlights)} candidates", flush=True)

    shorts = crop_highlights_local(source_path, top, aspect_ratio=aspect_ratio)

    if GCS_OUTPUT_BUCKET:
        from .local.storage import upload_and_sign

        for short in shorts:
            clip_path = short.get("clip_url")
            if clip_path and os.path.exists(clip_path):
                short["clip_url"] = upload_and_sign(clip_path, os.path.basename(clip_path))

    return {
        "mode": "local",
        "source_video_url": source_path,
        "transcript": transcript,
        "highlights": all_highlights,
        "shorts": shorts,
    }
