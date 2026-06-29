"""Transcribe video — YouTube → Gemini 2.5 Flash (speaker detection) → Groq Whisper.

Submodules:
  - transcriber_youtube: YouTube transcript API provider
  - transcriber_gemini: Google Gemini 2.5 Flash provider
  - transcriber_groq: Groq Whisper provider

Pipeline:
1. youtube-transcript-api (fast, free, no speaker detection)
2. Google AI Studio Gemini 2.5 Flash (speaker detection, diarization)
3. Groq Whisper-large-v3 (fast, no speaker detection)
"""

import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional

import requests

from ..config import STORAGE_DIR
from .utils import extract_video_id, sanitize_env

logger = logging.getLogger(__name__)

# Prevent console windows flashing on Windows
CREATION_FLAGS = 0
if os.name == "nt":
    CREATION_FLAGS = 0x08000000  # subprocess.CREATE_NO_WINDOW

# API keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"
GROQ_MODEL = "whisper-large-v3"


def _transcript_cache_path(task_dir: str) -> Path:
    return Path(task_dir) / "transcript.srt"


def _format_srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    ms = total_ms % 1000
    s = (total_ms // 1000) % 60
    m = (total_ms // 60000) % 60
    h = total_ms // 3600000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _parse_srt_timestamp(value: str) -> float:
    m = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})", value.strip())
    if not m:
        raise ValueError(f"Invalid SRT timestamp: {value!r}")
    h, mi, s, ms = map(int, m.groups())
    return h * 3600 + mi * 60 + s + ms / 1000.0


def _write_srt(media_path: str, transcript: Dict, task_dir: str) -> Path:
    cache_path = _transcript_cache_path(task_dir)
    lines = []
    for idx, seg in enumerate(transcript.get("segments", []), 1):
        start = _format_srt_timestamp(float(seg["start"]))
        end = _format_srt_timestamp(float(seg["end"]))
        text = str(seg.get("text", "")).strip().replace("\r", "").replace("\n", " ")
        lines.extend([str(idx), f"{start} --> {end}", text, ""])
    cache_path.write_text("\n".join(lines), encoding="utf-8")

    # Also cache as JSON to preserve speaker detection info and other fields
    json_cache_path = Path(task_dir) / "transcript.json"
    try:
        json_cache_path.write_text(json.dumps(transcript, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[transcribe] failed to write JSON cache: %s", e)

    return cache_path


def _load_srt(cache_path: Path) -> Dict:
    content = cache_path.read_text(encoding="utf-8-sig").strip()
    if not content:
        return {"duration": 0.0, "segments": []}
    segments = []
    for block in re.split(r"\n\s*\n", content):
        lines = [l.strip("﻿") for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        if "-->" not in lines[0] and len(lines) > 1 and "-->" in lines[1]:
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        start_raw, end_raw = [p.strip() for p in lines[0].split("-->", 1)]
        text = "\n".join(lines[1:]).strip()
        segments.append(
            {
                "start": _parse_srt_timestamp(start_raw),
                "end": _parse_srt_timestamp(end_raw),
                "text": text,
            }
        )
    duration = segments[-1]["end"] if segments else 0.0
    return {"duration": duration, "segments": segments}


# ── Hallucination Cleaner ────────────────────────────────────────

_FILLER_WORDS = {
    "oke", "ok", "he eh", "hehe", "iya", "eh", "uh", "um", "mm", "hmm",
    "ya", "yah", "yep", "yes", "no", "nah", "okay", "alright",
}


def _is_filler_segment(seg: Dict) -> bool:
    """Return True jika segment berisi kata filler/pendek yang bisa jadi hallucination."""
    txt = seg.get("text", "").strip().lower().rstrip(".!?,")
    return txt in _FILLER_WORDS or len(txt) <= 4


def _clean_hallucinations(
    segments: list, video_duration: float = 0.0, task_id: Optional[str] = None
) -> list:
    """Bersihkan hallucination loops dari output Gemini."""
    if not segments:
        return segments

    cleaned: list = []
    n = len(segments)

    HALLUCINATION_RUN = 10

    i = 0
    while i < n:
        seg = segments[i]
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", 0.0))

        # 1. Buang segmen yang melebihi durasi video
        if video_duration > 0 and start > video_duration + 2.0:
            break

        # 2. Perbaiki end < start
        if end < start:
            for j in range(i + 1, min(i + 5, n)):
                next_end = float(segments[j].get("end", 0.0))
                if next_end > start:
                    end = next_end
                    break
            else:
                end = start + 2.0
            seg = dict(seg)
            seg["end"] = end

        # 3. Deteksi blok hallucination
        if _is_filler_segment(seg):
            run_len = 0
            for j in range(i, min(i + HALLUCINATION_RUN + 1, n)):
                if _is_filler_segment(segments[j]):
                    run_len += 1
                else:
                    break
            if run_len >= HALLUCINATION_RUN:
                skipped = 0
                while i < n and _is_filler_segment(segments[i]):
                    i += 1
                    skipped += 1
                msg = f"[hallucination_cleaner] potong {skipped} segmen filler berulang (mulai t={start:.1f}s)"
                logger.info(msg)
                _update_transcribe_progress(task_id, 32.0, msg)
                continue

        cleaned.append(dict(seg) | {"start": start, "end": end})
        i += 1

    cleaned.sort(key=lambda s: s["start"])

    # 4. Batasi agar waktu akhir segmen tidak tumpang tindih dengan segmen berikutnya secara tidak wajar.
    # Tindakan ini mencegah tumpang tindih subtitle tanpa mengubah durasi secara sepihak berbasis asumsi kata statis.
    n_cleaned = len(cleaned)
    adjusted_overlaps = 0
    for idx in range(n_cleaned - 1):
        curr_seg = cleaned[idx]
        next_seg = cleaned[idx + 1]
        if curr_seg["end"] > next_seg["start"]:
            if curr_seg["start"] < next_seg["start"]:
                curr_seg["end"] = next_seg["start"]
                adjusted_overlaps += 1
    if adjusted_overlaps:
        logger.info(f"[hallucination_cleaner] Adjusted {adjusted_overlaps} overlapping segments to maintain temporal boundary.")

    if len(cleaned) < len(segments):
        msg = f"[hallucination_cleaner] {len(segments)} → {len(cleaned)} segmen (buang {len(segments) - len(cleaned)})"
        logger.info(msg)
        _update_transcribe_progress(task_id, 33.0, msg)

    return cleaned


def _download_audio(video_path: str, task_dir: str) -> str:
    """Extract audio from video file using ffmpeg."""
    audio_path = os.path.join(task_dir, "audio.mp3")
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", video_path, "-vn", "-acodec", "libmp3lame", "-q:a", "4",
        audio_path,
    ]
    subprocess.run(cmd, check=True, creationflags=CREATION_FLAGS)
    return audio_path


def _update_transcribe_progress(task_id: Optional[str], pct: float, msg: str):
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


# ── Main Entry Point ─────────────────────────────────────────────


def transcribe_video(
    media_path: str,
    task_id: str,
    language: Optional[str] = None,
    video_url: Optional[str] = None,
) -> Dict:
    """Transcribe video — YouTube → Gemini → Groq fallback."""
    sanitize_env()
    task_dir = str(STORAGE_DIR / task_id)
    os.makedirs(task_dir, exist_ok=True)

    # Check cache first
    json_cache_path = Path(task_dir) / "transcript.json"
    cache_path = _transcript_cache_path(task_dir)
    source_mtime = os.path.getmtime(media_path)

    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", media_path],
            capture_output=True, text=True, timeout=15, creationflags=CREATION_FLAGS,
        )
        video_duration = float(json.loads(probe.stdout).get("format", {}).get("duration", 0.0))
    except Exception as e:
        logger.error("[transcribe] ffprobe duration validation check failed: %s. Cache verification may skip duration validation.", e)
        video_duration = 0.0

    if json_cache_path.exists():
        if json_cache_path.stat().st_mtime >= source_mtime:
            try:
                cached = json.loads(json_cache_path.read_text(encoding="utf-8"))
                cached_dur = cached.get("duration", 0)
                if video_duration > 30 and cached_dur > 0 and cached_dur < video_duration * 0.1:
                    logger.warning(
                        "[transcribe] cached transcript duration (%.1fs) is suspicious vs video (%.1fs). Re-transcribing.",
                        cached_dur, video_duration,
                    )
                else:
                    logger.info("[transcribe] using cached JSON transcript")
                    return cached
            except Exception as e:
                logger.warning("[transcribe] failed to read cached JSON: %s", e)

    if cache_path.exists():
        if cache_path.stat().st_mtime >= source_mtime:
            try:
                cached_srt = _load_srt(cache_path)
                cached_dur = cached_srt.get("duration", 0)
                if video_duration > 30 and cached_dur > 0 and cached_dur < video_duration * 0.1:
                    logger.warning(
                        "[transcribe] cached SRT duration (%.1fs) is suspicious vs video (%.1fs). Re-transcribing.",
                        cached_dur, video_duration,
                    )
                else:
                    logger.info("[transcribe] using cached SRT transcript")
                    return cached_srt
            except Exception as e:
                logger.warning("[transcribe] failed to read cached SRT: %s", e)

    # 1. Try YouTube transcript API
    if video_url:
        msg = "[transcribe] trying YouTube transcript API"
        logger.info(msg)
        _update_transcribe_progress(task_id, 16.0, msg)

        from .transcriber_youtube import _try_youtube_transcript
        yt_result = _try_youtube_transcript(video_url)
        if yt_result and yt_result.get("segments"):
            msg = f"[transcribe] got {len(yt_result['segments'])} segments from YouTube"
            logger.info(msg)
            _update_transcribe_progress(task_id, 19.0, msg)
            _write_srt(media_path, yt_result, task_dir)
            return yt_result

        msg = "[transcribe] no YouTube transcript available"
        logger.info(msg)
        _update_transcribe_progress(task_id, 18.0, msg)

    # Extract audio (needed for both Groq and Gemini)
    audio_path = None
    try:
        audio_path = _download_audio(media_path, task_dir)
    except Exception as e:
        logger.warning("[transcribe] audio extraction failed: %s", e)

    failure_reasons: list[str] = []
    if video_url:
        failure_reasons.append("YouTube: no transcript available for this video")
    if audio_path is None:
        failure_reasons.append("audio extraction failed (ffmpeg missing or video corrupt)")

    # 2. Try Groq Whisper (fast, word timestamps)
    if audio_path:
        try:
            from .transcriber_groq import _try_groq_whisper
            groq_result = _try_groq_whisper(audio_path, task_id, language=language)
            if groq_result and groq_result.get("segments"):
                msg = f"[transcribe] got {len(groq_result['segments'])} segments from Groq (with word timestamps)"
                logger.info(msg)
                _update_transcribe_progress(task_id, 35.0, msg)
                _write_srt(media_path, groq_result, task_dir)
                return groq_result
            reason = "no GROQ_API_KEY set" if not GROQ_API_KEY else "Groq returned no segments"
            failure_reasons.append(f"Groq Whisper: {reason}")
        except Exception as e:
            logger.warning("[transcribe] Groq failed: %s", e)
            failure_reasons.append(f"Groq Whisper: {e}")

    # 3. Try Gemini 2.5 Flash (with speaker detection)
    if audio_path:
        try:
            from .transcriber_gemini import _try_gemini_transcription
            gemini_result = _try_gemini_transcription(audio_path, task_id)
            if gemini_result and gemini_result.get("segments"):
                msg = f"[transcribe] got {len(gemini_result['segments'])} segments from Gemini"
                logger.info(msg)
                _update_transcribe_progress(task_id, 35.0, msg)
                _write_srt(media_path, gemini_result, task_dir)
                return gemini_result
            reason = "no GEMINI_API_KEY set" if not GEMINI_API_KEY else "Gemini returned no segments"
            failure_reasons.append(f"Gemini: {reason}")
        except Exception as e:
            logger.warning("[transcribe] Gemini failed: %s", e)
            failure_reasons.append(f"Gemini: {e}")

    # 4. No transcription available
    detail = "; ".join(failure_reasons) if failure_reasons else "unknown reason"
    raise RuntimeError(f"No transcription available — {detail}.")
