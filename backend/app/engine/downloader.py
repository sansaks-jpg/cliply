"""Download YouTube video via yt-dlp with caching.
"""
import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from ..config import DOWNLOAD_FORMAT, STORAGE_DIR


def _format_for(fmt: str) -> str:
    try:
        height = int(fmt)
    except ValueError:
        height = 720
    return (
        f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
        f"best[height<={height}][ext=mp4]/best"
    )


def _extract_video_id(source: str) -> Optional[str]:
    parsed = urlparse(source)
    host = (parsed.netloc or "").lower().removeprefix("www.")
    if host in ("youtu.be",):
        return parsed.path.lstrip("/").split("/", 1)[0] or None
    if "youtube.com" in host:
        if parsed.path.startswith("/watch"):
            return parse_qs(parsed.query).get("v", [None])[0]
        m = re.search(r"/(?:shorts|embed|live)/([^/?#&]+)", parsed.path)
        if m:
            return m.group(1)
    return None


def _existing_download(out_dir: str, video_id: str) -> Optional[str]:
    for ext in (".mp4", ".mkv", ".webm"):
        p = os.path.join(out_dir, f"source_{video_id}{ext}")
        if os.path.exists(p):
            return p
    return None


def download_video(video_url: str, task_id: str) -> str:
    import yt_dlp

    out_dir = str(STORAGE_DIR / task_id)
    os.makedirs(out_dir, exist_ok=True)

    video_id = _extract_video_id(video_url)
    if video_id:
        cached = _existing_download(str(STORAGE_DIR), video_id)
        if cached:
            return cached

    fmt = _format_for(DOWNLOAD_FORMAT)
    ydl_opts = {
        "format": fmt,
        "outtmpl": os.path.join(str(STORAGE_DIR), "source_%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        path = ydl.prepare_filename(info)
        if not os.path.exists(path):
            stem, _ = os.path.splitext(path)
            for ext in (".mp4", ".mkv", ".webm"):
                if os.path.exists(stem + ext):
                    path = stem + ext
                    break

    return path
