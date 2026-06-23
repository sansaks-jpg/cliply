"""Shared utility functions for the video processing engine."""

import re
from typing import Optional
from urllib.parse import parse_qs, urlparse


def extract_video_id(source: str) -> Optional[str]:
    """Extract YouTube video ID from a URL or string.

    Supports:
    - youtu.be/<id>
    - youtube.com/watch?v=<id>
    - youtube.com/shorts/<id>
    - youtube.com/embed/<id>
    - youtube.com/live/<id>
    """
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
