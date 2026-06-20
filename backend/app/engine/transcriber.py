"""Transcribe video — YouTube → Gemini 2.5 Flash (speaker detection) → Groq Whisper.

Pipeline:
1. youtube-transcript-api (fast, free, no speaker detection)
2. Google AI Studio Gemini 2.5 Flash (speaker detection, diarization)
3. Groq Whisper-large-v3 (fast, no speaker detection)
"""
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, Optional

import requests

from ..config import STORAGE_DIR

# API keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", GROQ_API_KEY)  # fallback ke groq key
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
        import json
        json_cache_path.write_text(json.dumps(transcript, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[transcribe] failed to write JSON cache: {e}", flush=True)
        
    return cache_path


def _load_srt(cache_path: Path) -> Dict:
    content = cache_path.read_text(encoding="utf-8-sig").strip()
    if not content:
        return {"duration": 0.0, "segments": []}
    segments = []
    for block in re.split(r"\n\s*\n", content):
        lines = [l.strip("\ufeff") for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        if "-->" not in lines[0] and len(lines) > 1 and "-->" in lines[1]:
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        start_raw, end_raw = [p.strip() for p in lines[0].split("-->", 1)]
        text = "\n".join(lines[1:]).strip()
        segments.append({"start": _parse_srt_timestamp(start_raw), "end": _parse_srt_timestamp(end_raw), "text": text})
    duration = segments[-1]["end"] if segments else 0.0
    return {"duration": duration, "segments": segments}


# ── Hallucination Cleaner ────────────────────────────────────────

# Kata-kata pendek/filler yang berpotensi jadi hallucination loop
_FILLER_WORDS = {
    "oke", "ok", "he eh", "hehe", "iya", "eh", "uh", "um", "mm", "hmm",
    "ya", "yah", "yep", "yes", "no", "nah", "okay", "alright",
}


def _is_filler_segment(seg: Dict) -> bool:
    """Return True jika segment berisi kata filler/pendek yang bisa jadi hallucination."""
    txt = seg.get("text", "").strip().lower().rstrip(".!?,")
    return txt in _FILLER_WORDS or len(txt) <= 4


def _clean_hallucinations(segments: list, video_duration: float = 0.0, task_id: Optional[str] = None) -> list:
    """Bersihkan hallucination loops dari output Gemini.

    Strategi:
    1. Buang segmen di luar durasi video.
    2. Perbaiki timestamp tidak valid (end <= start).
    3. Deteksi blok berulang (>= 10 filler berturut-turut) dan potong.
    4. Gabungkan blok setelah gap besar akibat pemotongan ke segmen berikutnya yang valid.
    """
    if not segments:
        return segments

    cleaned: list = []
    n = len(segments)

    HALLUCINATION_RUN = 10  # minimum run consecutive fillers untuk dianggap hallucination

    i = 0
    while i < n:
        seg = segments[i]
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", 0.0))

        # 1. Buang segmen yang melebihi durasi video (dengan toleransi 2 detik)
        if video_duration > 0 and start > video_duration + 2.0:
            break

        # 2. Perbaiki end < start (timestamp anomaly)
        if end < start:
            # Coba ambil end dari segmen berikutnya yang valid
            for j in range(i + 1, min(i + 5, n)):
                next_end = float(segments[j].get("end", 0.0))
                if next_end > start:
                    end = next_end
                    break
            else:
                # Perkiraan: +2 detik
                end = start + 2.0
            seg = dict(seg)
            seg["end"] = end

        # 3. Deteksi blok hallucination: hitung berapa filler berturut-turut mulai dari i
        if _is_filler_segment(seg):
            run_len = 0
            for j in range(i, min(i + HALLUCINATION_RUN + 1, n)):
                if _is_filler_segment(segments[j]):
                    run_len += 1
                else:
                    break
            if run_len >= HALLUCINATION_RUN:
                # Ini adalah hallucination block — skip sampai ketemu non-filler berikutnya
                skipped = 0
                while i < n and _is_filler_segment(segments[i]):
                    i += 1
                    skipped += 1
                msg = f"[hallucination_cleaner] potong {skipped} segmen filler berulang (mulai t={start:.1f}s)"
                print(msg, flush=True)
                _update_transcribe_progress(task_id, 32.0, msg)
                continue

        cleaned.append(dict(seg) | {"start": start, "end": end})
        i += 1

    # 4. Sort ulang berdasarkan start time (jaga-jaga kalau ada yang out of order)
    cleaned.sort(key=lambda s: s["start"])

    if len(cleaned) < len(segments):
        msg = f"[hallucination_cleaner] {len(segments)} → {len(cleaned)} segmen (buang {len(segments) - len(cleaned)})"
        print(msg, flush=True)
        _update_transcribe_progress(task_id, 33.0, msg)

    return cleaned


def _extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from URL."""
    from urllib.parse import parse_qs, urlparse
    parsed = urlparse(url)
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


# ── Stage 1: YouTube Transcript API ──────────────────────────────

def _try_youtube_transcript(video_url: str) -> Optional[Dict]:
    """Try to get transcript using youtube-transcript-api."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        video_id = _extract_video_id(video_url)
        if not video_id:
            return None
        
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Try manual transcripts first (Indonesian, then English)
        for lang in ["id", "en"]:
            try:
                transcript = transcript_list.find_manually_created_transcript([lang])
                entries = transcript.fetch()
                return _parse_youtube_transcript(entries)
            except Exception:
                continue
        
        # Try auto-generated transcripts
        for lang in ["id", "en"]:
            try:
                transcript = transcript_list.find_generated_transcript([lang])
                entries = transcript.fetch()
                return _parse_youtube_transcript(entries)
            except Exception:
                continue
        
        return None
    except Exception:
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


# ── Stage 2: Google AI Studio Gemini 2.5 Flash ───────────────────

def _download_audio(video_path: str, task_dir: str) -> str:
    """Extract audio from video file using ffmpeg."""
    audio_path = os.path.join(task_dir, "audio.mp3")
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", video_path,
        "-vn", "-acodec", "libmp3lame", "-q:a", "4",
        audio_path,
    ]
    import subprocess
    subprocess.run(cmd, check=True)
    return audio_path


def _parse_lax_json(json_str: str, task_id: Optional[str] = None) -> dict:
    """Parse JSON string, attempting to repair it if it is truncated or has extra text."""
    json_str = json_str.strip()
    
    # 1. Clean markdown code blocks if present
    if json_str.startswith("```"):
        lines = json_str.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        json_str = "\n".join(lines).strip()
        
    # 2. Try parsing directly
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        msg = f"[transcribe] JSON decode failed directly: {e}. Attempting to repair truncated JSON..."
        print(msg, flush=True)
        _update_transcribe_progress(task_id, 24.0, msg)

    # 3. Try to repair truncated JSON by finding last valid segment
    # We search for '}' from the end, truncate there, and append ']}'
    idx = len(json_str)
    while True:
        idx = json_str.rfind('}', 0, idx)
        if idx == -1:
            break
        
        candidate = json_str[:idx+1]
        # We need to close the array and the object
        # Let's try to append ']}' first (most common for truncated {"segments": [...]})
        try:
            return json.loads(candidate + "]}")
        except json.JSONDecodeError:
            pass
            
        # Try appending just '}' if the array is already closed but not the object
        try:
            return json.loads(candidate + "}")
        except json.JSONDecodeError:
            pass
            
        # Try appending just ']' if the object is not needed or already closed (unlikely but let's be safe)
        try:
            return json.loads(candidate + "]")
        except json.JSONDecodeError:
            pass

        # Try parsing the candidate as-is
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
            
    raise ValueError("Failed to repair truncated JSON response")


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
            print(f"[transcribe progress] Task {task_id}: {pct:.1f}% - {msg}", flush=True)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Failed to update transcribe progress: %s", e)


def _try_gemini_transcription(audio_path: str, task_id: Optional[str] = None) -> Optional[Dict]:
    """Transcribe audio using Gemini 2.5 Flash with speaker detection."""
    if not GEMINI_API_KEY:
        print("[transcribe] no GEMINI_API_KEY set", flush=True)
        return None
    
    try:
        from google import genai
        
        msg = f"[transcribe] calling Gemini {GEMINI_MODEL} with {os.path.getsize(audio_path) / 1024 / 1024:.1f}MB audio"
        print(msg, flush=True)
        _update_transcribe_progress(task_id, 20.0, msg)
        
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Upload audio file
        audio_file = client.files.upload(file=audio_path)
        
        # Prompt for transcription with speaker detection
        prompt = """Transcribe this audio with speaker diarization. 

For each segment, provide:
- start: start time in seconds (float)
- end: end time in seconds (float)  
- speaker: speaker label (e.g., "Speaker 1", "Speaker 2", etc.)
- text: what they said

Rules:
- Detect different speakers based on voice characteristics
- Use consistent speaker labels throughout
- Include timestamps for each segment
- DO NOT transcribe word-by-word. Each segment must contain a complete sentence or a natural phrase (typically 5 to 15 words, or 2 to 7 seconds of continuous speech).
- Group words by the same speaker into readable sentences/clauses instead of splitting them into single words or extremely short fragments.
- Keep natural sentence breaks and proper punctuation.

Respond with JSON only:
{"segments": [{"start": float, "end": float, "speaker": "string", "text": "string"}]}"""
        
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[audio_file, prompt],
            config={
                "temperature": 0.1,
                "response_mime_type": "application/json",
            },
        )
        
        # Parse response
        result = response.text
        if not result:
            return None
        
        parsed = _parse_lax_json(result, task_id)
        segments = parsed.get("segments", [])
        
        if not segments:
            return None
        
        # Convert to our format
        formatted_segments = []
        for seg in segments:
            # support both start/end and start_time/end_time in case the model outputs start_time/end_time
            start_val = seg.get("start") if seg.get("start") is not None else seg.get("start_time", 0.0)
            end_val = seg.get("end") if seg.get("end") is not None else seg.get("end_time", 0.0)
            formatted_segments.append({
                "start": float(start_val),
                "end": float(end_val),
                "text": seg.get("text", "").strip(),
                "speaker": seg.get("speaker", ""),
            })
        
        # Ambil estimasi durasi audio sebelum cleaning
        raw_duration = formatted_segments[-1]["end"] if formatted_segments else 0.0
        # Dapatkan durasi file audio yang sesungguhnya untuk filter hallucination diluar video
        try:
            import subprocess
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "json", audio_path],
                capture_output=True, text=True, timeout=15,
            )
            audio_duration = float(json.loads(probe.stdout).get("format", {}).get("duration", 0.0))
        except Exception:
            audio_duration = 0.0
        
        # Detect timestamp compression hallucination (Gemini sometimes compresses timestamps)
        # If transcript spans < 10% of actual audio duration, rescale proportionally
        if audio_duration > 30 and raw_duration > 0 and raw_duration < audio_duration * 0.1:
            scale_factor = audio_duration / raw_duration
            print(f"[transcribe] WARNING: timestamps compressed ({raw_duration:.1f}s vs {audio_duration:.1f}s actual). "
                  f"Rescaling by {scale_factor:.1f}x", flush=True)
            for seg in formatted_segments:
                seg["start"] *= scale_factor
                seg["end"] *= scale_factor
            raw_duration = formatted_segments[-1]["end"] if formatted_segments else 0.0
        
        # Bersihkan hallucination sebelum return
        formatted_segments = _clean_hallucinations(formatted_segments, video_duration=audio_duration, task_id=task_id)
        
        duration = min(formatted_segments[-1]["end"], audio_duration or raw_duration) if formatted_segments else 0.0
        msg = f"[transcribe] Gemini returned {len(formatted_segments)} segments with speaker detection"
        print(msg, flush=True)
        _update_transcribe_progress(task_id, 34.0, msg)
        
        return {"duration": duration, "segments": formatted_segments}
    
    except Exception as e:
        import traceback
        print(f"[transcribe] Gemini failed: {e}", flush=True)
        traceback.print_exc()
        return None


# ── Stage 3: Groq Whisper ────────────────────────────────────────

def _try_groq_whisper(audio_path: str, task_id: Optional[str] = None) -> Optional[Dict]:
    """Transcribe audio using Groq API with whisper-large-v3."""
    if not GROQ_API_KEY:
        print("[transcribe] no GROQ_API_KEY set", flush=True)
        return None
    
    try:
        from groq import Groq
        
        msg = f"[transcribe] calling Groq {GROQ_MODEL} with {os.path.getsize(audio_path) / 1024 / 1024:.1f}MB audio"
        print(msg, flush=True)
        _update_transcribe_progress(task_id, 28.0, msg)
        client = Groq(api_key=GROQ_API_KEY)
        
        with open(audio_path, "rb") as f:
            result = client.audio.transcriptions.create(
                file=(os.path.basename(audio_path), f.read()),
                model=GROQ_MODEL,
                response_format="verbose_json",
                language="id",
            )
        
        # Parse Groq response
        segments = []
        if hasattr(result, "segments") and result.segments:
            for seg in result.segments:
                segments.append({
                    "start": float(seg["start"]),
                    "end": float(seg["end"]),
                    "text": seg["text"].strip(),
                })
        elif hasattr(result, "text") and result.text:
            segments.append({"start": 0.0, "end": 0.0, "text": result.text.strip()})
        
        duration = float(result.duration) if hasattr(result, "duration") else (segments[-1]["end"] if segments else 0.0)
        print(f"[transcribe] Groq returned {len(segments)} segments", flush=True)
        return {"duration": duration, "segments": segments}
    
    except Exception as e:
        import traceback
        print(f"[transcribe] Groq failed: {e}", flush=True)
        traceback.print_exc()
        return None


# ── Main Entry Point ─────────────────────────────────────────────

def transcribe_video(media_path: str, task_id: str, language: Optional[str] = None, video_url: Optional[str] = None) -> Dict:
    """Transcribe video — YouTube → Gemini → Groq fallback.
    
    Args:
        media_path: local video file path
        task_id: task ID for caching
        language: ISO-639-1 language code (optional)
        video_url: YouTube URL for transcript API (optional)
    """
    task_dir = str(STORAGE_DIR / task_id)
    os.makedirs(task_dir, exist_ok=True)
    
    # Check cache first
    json_cache_path = Path(task_dir) / "transcript.json"
    cache_path = _transcript_cache_path(task_dir)
    source_mtime = os.path.getmtime(media_path)
    
    # Get actual video duration for cache validation
    try:
        import subprocess
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", media_path],
            capture_output=True, text=True, timeout=15,
        )
        video_duration = float(json.loads(probe.stdout).get("format", {}).get("duration", 0.0))
    except Exception:
        video_duration = 0.0
    
    if json_cache_path.exists():
        if json_cache_path.stat().st_mtime >= source_mtime:
            try:
                cached = json.loads(json_cache_path.read_text(encoding="utf-8"))
                cached_dur = cached.get("duration", 0)
                # Validate cache: if transcript duration is < 10% of video duration, cache is bad
                if video_duration > 30 and cached_dur > 0 and cached_dur < video_duration * 0.1:
                    print(f"[transcribe] cached transcript duration ({cached_dur:.1f}s) is suspicious "
                          f"vs video ({video_duration:.1f}s). Re-transcribing.", flush=True)
                else:
                    print(f"[transcribe] using cached JSON transcript", flush=True)
                    return cached
            except Exception as e:
                print(f"[transcribe] failed to read cached JSON: {e}", flush=True)

    if cache_path.exists():
        if cache_path.stat().st_mtime >= source_mtime:
            try:
                cached_srt = _load_srt(cache_path)
                cached_dur = cached_srt.get("duration", 0)
                if video_duration > 30 and cached_dur > 0 and cached_dur < video_duration * 0.1:
                    print(f"[transcribe] cached SRT duration ({cached_dur:.1f}s) is suspicious "
                          f"vs video ({video_duration:.1f}s). Re-transcribing.", flush=True)
                else:
                    print(f"[transcribe] using cached SRT transcript", flush=True)
                    return cached_srt
            except Exception as e:
                print(f"[transcribe] failed to read cached SRT: {e}", flush=True)
    
    # 1. Try YouTube transcript API
    if video_url:
        msg = "[transcribe] trying YouTube transcript API"
        print(msg, flush=True)
        _update_transcribe_progress(task_id, 16.0, msg)
        
        yt_result = _try_youtube_transcript(video_url)
        if yt_result and yt_result.get("segments"):
            msg = f"[transcribe] got {len(yt_result['segments'])} segments from YouTube"
            print(msg, flush=True)
            _update_transcribe_progress(task_id, 19.0, msg)
            _write_srt(media_path, yt_result, task_dir)
            return yt_result
            
        msg = "[transcribe] no YouTube transcript available"
        print(msg, flush=True)
        _update_transcribe_progress(task_id, 18.0, msg)
    
    # 2. Try Gemini 2.5 Flash (with speaker detection)
    audio_path = None
    try:
        audio_path = _download_audio(media_path, task_dir)
        gemini_result = _try_gemini_transcription(audio_path, task_id)
        if gemini_result and gemini_result.get("segments"):
            msg = f"[transcribe] got {len(gemini_result['segments'])} segments from Gemini"
            print(msg, flush=True)
            _update_transcribe_progress(task_id, 35.0, msg)
            _write_srt(media_path, gemini_result, task_dir)
            return gemini_result
    except Exception as e:
        print(f"[transcribe] Gemini failed: {e}", flush=True)
    
    # 3. Try Groq Whisper (no speaker detection)
    if audio_path:
        try:
            groq_result = _try_groq_whisper(audio_path, task_id)
            if groq_result and groq_result.get("segments"):
                msg = f"[transcribe] got {len(groq_result['segments'])} segments from Groq"
                print(msg, flush=True)
                _update_transcribe_progress(task_id, 35.0, msg)
                _write_srt(media_path, groq_result, task_dir)
                return groq_result
        except Exception as e:
            print(f"[transcribe] Groq failed: {e}", flush=True)
    
    # 4. No transcription available
    raise RuntimeError("No transcription available — YouTube, Gemini, and Groq all failed.")
