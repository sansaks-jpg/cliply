"""Groq Whisper transcription provider.

Uses Groq API with whisper-large-v3 for fast transcription
with word-level timestamps.
"""
import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "whisper-large-v3"


def _try_groq_whisper(
    audio_path: str, task_id: Optional[str] = None, language: Optional[str] = None
) -> Optional[Dict]:
    """Transcribe audio using Groq API with whisper-large-v3."""
    groq_api_key = os.getenv("GROQ_API_KEY", "")
    logger.info(
        "[transcribe] GROQ_API_KEY present: %s",
        bool(groq_api_key),
    )
    if not groq_api_key:
        logger.warning("[transcribe] no GROQ_API_KEY set")
        return None

    try:
        from groq import Groq
        logger.info("[transcribe] groq SDK imported OK")
    except Exception as e:
        logger.error("[transcribe] groq SDK import FAILED: %s", e, exc_info=True)
        return None

    try:
        audio_size = os.path.getsize(audio_path)
        msg = f"[transcribe] calling Groq {GROQ_MODEL} with {audio_size / 1024 / 1024:.1f}MB audio"
        logger.info(msg)
        _update_groq_progress(task_id, 28.0, msg)
        client = Groq(api_key=groq_api_key)

        with open(audio_path, "rb") as f:
            audio_data = (os.path.basename(audio_path), f.read())
        create_kwargs: dict = {
            "file": audio_data,
            "model": GROQ_MODEL,
            "response_format": "verbose_json",
            "timestamp_granularities": ["word", "segment"],
        }
        if language:
            create_kwargs["language"] = language
        logger.info("[transcribe] Sending request to Groq API (model=%s, file_size=%d bytes)...", GROQ_MODEL, audio_size)
        if "timeout" not in create_kwargs:
            create_kwargs["timeout"] = 60.0
        result = client.audio.transcriptions.create(**create_kwargs)
        logger.info("[transcribe] Groq API response received! duration=%s", getattr(result, "duration", "N/A"))

        # Parse kata-kata jika tersedia
        words = []
        raw_words = getattr(result, "words", None)
        if raw_words:
            for w in raw_words:
                if isinstance(w, dict):
                    words.append(
                        {
                            "word": w.get("word", "").strip(),
                            "start": float(w.get("start", 0.0)),
                            "end": float(w.get("end", 0.0)),
                        }
                    )
                else:
                    words.append(
                        {
                            "word": getattr(w, "word", "").strip(),
                            "start": float(getattr(w, "start", 0.0)),
                            "end": float(getattr(w, "end", 0.0)),
                        }
                    )

        # Parse Groq response segments
        segments = []
        if hasattr(result, "segments") and result.segments:
            for seg in result.segments:
                seg_dict = {
                    "start": float(
                        seg["start"]
                        if isinstance(seg, dict)
                        else getattr(seg, "start", 0.0)
                    ),
                    "end": float(
                        seg["end"]
                        if isinstance(seg, dict)
                        else getattr(seg, "end", 0.0)
                    ),
                    "text": (
                        seg["text"]
                        if isinstance(seg, dict)
                        else getattr(seg, "text", "")
                    ).strip(),
                }
                segments.append(seg_dict)
        elif hasattr(result, "text") and result.text:
            segments.append({"start": 0.0, "end": 0.0, "text": result.text.strip()})

        # Hubungkan kata-kata ke segmen menggunakan waktu tengah (mid-time) kata
        if words and segments:
            import bisect

            seg_starts = [s["start"] for s in segments]

            for w in words:
                mid_time = (w["start"] + w["end"]) / 2.0

                # Optimisasi O(N log M) menggunakan binary search
                idx = bisect.bisect_right(seg_starts, mid_time)

                candidates = []
                if idx > 0:
                    candidates.append(segments[idx - 1])
                if idx < len(segments):
                    candidates.append(segments[idx])

                best_seg = None
                min_distance = float("inf")

                for seg_dict in candidates:
                    if seg_dict["start"] <= mid_time <= seg_dict["end"]:
                        best_seg = seg_dict
                        min_distance = 0
                        break
                    dist = min(
                        abs(mid_time - seg_dict["start"]),
                        abs(mid_time - seg_dict["end"]),
                    )
                    if dist < min_distance:
                        min_distance = dist
                        best_seg = seg_dict

                if best_seg is not None:
                    if "words" not in best_seg:
                        best_seg["words"] = []
                    best_seg["words"].append(w)

        duration = (
            float(result.duration)
            if hasattr(result, "duration")
            else (segments[-1]["end"] if segments else 0.0)
        )
        logger.info(
            "[transcribe] Groq returned %d segments (with word-level timestamps)",
            len(segments),
        )
        return {"duration": duration, "segments": segments}

    except Exception as e:
        import traceback
        logger.error("[transcribe] Groq transcription API failed: %s", e)
        logger.debug(traceback.format_exc())
        raise RuntimeError(f"Groq API failed: {e}") from e


def _update_groq_progress(task_id: Optional[str], pct: float, msg: str):
    if not task_id:
        return
    try:
        import asyncio
        from ..state import store

        loop = getattr(store, "loop", None)
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(
                store.set_progress(task_id, pct, "TRANSCRIBE", msg), loop
            )
        else:
            logger.info("[transcribe progress] Task %s: %.1f%% - %s", task_id, pct, msg)
    except Exception as e:
        logging.getLogger(__name__).error("Failed to update transcribe progress: %s", e)
