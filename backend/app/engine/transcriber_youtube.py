"""YouTube transcript API provider.

Uses youtube-transcript-api to fetch transcripts directly from YouTube
(fast, free, no speaker detection).
"""
import logging
from typing import Dict, Optional

from .utils import extract_video_id

logger = logging.getLogger(__name__)


def _try_youtube_transcript(video_url: str) -> Optional[Dict]:
    """Try to get transcript using youtube-transcript-api v1.x."""
    logger.info("[transcribe] YouTube: attempting transcript API for %s", video_url)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        logger.info("[transcribe] YouTube: youtube_transcript_api SDK imported OK")
    except Exception as e:
        logger.error("[transcribe] YouTube: SDK import FAILED: %s", e, exc_info=True)
        return None

    try:
        video_id = extract_video_id(video_url)
        if not video_id:
            logger.debug("[transcribe] YouTube: could not extract video ID from %s", video_url)
            return None

        logger.info("[transcribe] YouTube: video_id=%s, listing transcripts...", video_id)
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)

        # Try manual transcripts first (Indonesian, then English)
        try:
            transcript = transcript_list.find_manually_created_transcript(["id", "en"])
            entries = transcript.fetch()
            logger.info("[transcribe] YouTube: found manual transcript")
            return _parse_youtube_transcript(entries)
        except Exception as e:
            logger.debug("[transcribe] YouTube: no manual transcript (id/en): %s", e)

        # Try auto-generated transcripts
        try:
            transcript = transcript_list.find_generated_transcript(["id", "en"])
            entries = transcript.fetch()
            logger.info("[transcribe] YouTube: found auto-generated transcript")
            return _parse_youtube_transcript(entries)
        except Exception as e:
            logger.debug("[transcribe] YouTube: no auto-generated transcript (id/en): %s", e)

        logger.info("[transcribe] YouTube: no transcript available for this video")
        return None
    except Exception as e:
        logger.warning("[transcribe] YouTube transcript API failed: %s", e, exc_info=True)
        return None


def _parse_youtube_transcript(entries) -> Dict:
    """Parse youtube-transcript-api entries into segments."""
    segments = []
    for entry in entries:
        start = float(entry.start)
        duration = float(entry.duration)
        text = entry.text.strip().replace("\n", " ")
        if text:
            segments.append({"start": start, "end": start + duration, "text": text})
    duration = segments[-1]["end"] if segments else 0.0
    return {"duration": duration, "segments": segments}
