"""Transcribe video — YouTube → Gemini 2.5 Flash (speaker detection) → Groq Whisper.

Pipeline:
1. youtube-transcript-api (fast, free, no speaker detection)
2. Google AI Studio Gemini 2.5 Flash (speaker detection, diarization)
3. Groq Whisper-large-v3 (fast, no speaker detection)
"""
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


def _try_gemini_transcription(audio_path: str) -> Optional[Dict]:
    """Transcribe audio using Gemini 2.5 Flash with speaker detection."""
    if not GEMINI_API_KEY:
        print("[transcribe] no GEMINI_API_KEY set", flush=True)
        return None
    
    try:
        from google import genai
        
        print(f"[transcribe] calling Gemini {GEMINI_MODEL} with {os.path.getsize(audio_path) / 1024 / 1024:.1f}MB audio", flush=True)
        
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
- Keep natural sentence breaks

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
        
        import json
        parsed = json.loads(result)
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
        
        duration = formatted_segments[-1]["end"] if formatted_segments else 0.0
        print(f"[transcribe] Gemini returned {len(formatted_segments)} segments with speaker detection", flush=True)
        
        return {"duration": duration, "segments": formatted_segments}
    
    except Exception as e:
        import traceback
        print(f"[transcribe] Gemini failed: {e}", flush=True)
        traceback.print_exc()
        return None


# ── Stage 3: Groq Whisper ────────────────────────────────────────

def _try_groq_whisper(audio_path: str) -> Optional[Dict]:
    """Transcribe audio using Groq API with whisper-large-v3."""
    if not GROQ_API_KEY:
        print("[transcribe] no GROQ_API_KEY set", flush=True)
        return None
    
    try:
        from groq import Groq
        
        print(f"[transcribe] calling Groq {GROQ_MODEL} with {os.path.getsize(audio_path) / 1024 / 1024:.1f}MB audio", flush=True)
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
    
    if json_cache_path.exists():
        if json_cache_path.stat().st_mtime >= source_mtime:
            print(f"[transcribe] using cached JSON transcript", flush=True)
            import json
            try:
                return json.loads(json_cache_path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[transcribe] failed to read cached JSON: {e}", flush=True)

    if cache_path.exists():
        if cache_path.stat().st_mtime >= source_mtime:
            print(f"[transcribe] using cached SRT transcript", flush=True)
            return _load_srt(cache_path)
    
    # 1. Try YouTube transcript API
    if video_url:
        print(f"[transcribe] trying YouTube transcript API", flush=True)
        yt_result = _try_youtube_transcript(video_url)
        if yt_result and yt_result.get("segments"):
            print(f"[transcribe] got {len(yt_result['segments'])} segments from YouTube", flush=True)
            _write_srt(media_path, yt_result, task_dir)
            return yt_result
        print(f"[transcribe] no YouTube transcript available", flush=True)
    
    # 2. Try Gemini 2.5 Flash (with speaker detection)
    audio_path = None
    try:
        audio_path = _download_audio(media_path, task_dir)
        gemini_result = _try_gemini_transcription(audio_path)
        if gemini_result and gemini_result.get("segments"):
            print(f"[transcribe] got {len(gemini_result['segments'])} segments from Gemini", flush=True)
            _write_srt(media_path, gemini_result, task_dir)
            return gemini_result
    except Exception as e:
        print(f"[transcribe] Gemini failed: {e}", flush=True)
    
    # 3. Try Groq Whisper (no speaker detection)
    if audio_path:
        try:
            groq_result = _try_groq_whisper(audio_path)
            if groq_result and groq_result.get("segments"):
                print(f"[transcribe] got {len(groq_result['segments'])} segments from Groq", flush=True)
                _write_srt(media_path, groq_result, task_dir)
                return groq_result
        except Exception as e:
            print(f"[transcribe] Groq failed: {e}", flush=True)
    
    # 4. No transcription available
    raise RuntimeError("No transcription available — YouTube, Gemini, and Groq all failed.")
