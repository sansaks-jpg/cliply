"""Google Gemini 2.5 Flash transcription provider.

Provides speaker diarization and timestamp detection using Gemini's
multimodal capabilities.
"""
import json
import logging
import os
import subprocess
from typing import Dict, Optional

logger = logging.getLogger(__name__)

CREATION_FLAGS = 0
if os.name == "nt":
    CREATION_FLAGS = 0x08000000  # subprocess.CREATE_NO_WINDOW

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"


def _parse_lax_json(json_str: str, task_id: Optional[str] = None) -> dict:
    """Parse JSON string, attempting to clean and extract valid JSON without unsafe truncation."""
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
    except json.JSONDecodeError:
        pass

    # 3. Try to extract JSON structure between first '{' and last '}'
    start_idx = json_str.find("{")
    end_idx = json_str.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        candidate = json_str[start_idx : end_idx + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            msg = f"[transcribe] Failed to parse extracted JSON block: {e}"
            logger.warning("%s", msg)
            _update_gemini_progress(task_id, 24.0, msg)

    # Do NOT attempt to repair truncated/incomplete JSON packages by appending closing characters,
    # as this discards dialogue segments quietly and corrupts the downstream pipeline.
    raise ValueError("Gemini response is not a valid complete JSON object")


def _update_gemini_progress(task_id: Optional[str], pct: float, msg: str):
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


def _try_gemini_transcription(
    audio_path: str, task_id: Optional[str] = None
) -> Optional[Dict]:
    """Transcribe audio using Gemini 2.5 Flash with speaker detection."""
    logger.info(
        "[transcribe] GEMINI_API_KEY present: %s (length: %d)",
        bool(GEMINI_API_KEY),
        len(GEMINI_API_KEY),
    )
    if not GEMINI_API_KEY:
        logger.warning("[transcribe] no GEMINI_API_KEY set")
        return None

    try:
        from google import genai
        logger.info("[transcribe] google.genai SDK imported OK")
    except Exception as e:
        logger.error("[transcribe] google.genai SDK import FAILED: %s", e, exc_info=True)
        return None

    # Import hallucination cleaner from parent module
    from .transcriber import _clean_hallucinations

    try:
        audio_size = os.path.getsize(audio_path)
        msg = f"[transcribe] calling Gemini {GEMINI_MODEL} with {audio_size / 1024 / 1024:.1f}MB audio"
        logger.info(msg)
        _update_gemini_progress(task_id, 20.0, msg)

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
            start_val = (
                seg.get("start")
                if seg.get("start") is not None
                else seg.get("start_time", 0.0)
            )
            end_val = (
                seg.get("end")
                if seg.get("end") is not None
                else seg.get("end_time", 0.0)
            )
            formatted_segments.append(
                {
                    "start": float(start_val),
                    "end": float(end_val),
                    "text": seg.get("text", "").strip(),
                    "speaker": seg.get("speaker", ""),
                }
            )

        # Ambil estimasi durasi audio sebelum cleaning
        raw_duration = formatted_segments[-1]["end"] if formatted_segments else 0.0
        try:
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "json", audio_path,
                ],
                capture_output=True, text=True, timeout=15,
                creationflags=CREATION_FLAGS,
            )
            audio_duration = float(
                json.loads(probe.stdout).get("format", {}).get("duration", 0.0)
            )
        except Exception:
            audio_duration = 0.0

        # Detect timestamp compression hallucination
        if (
            audio_duration > 30
            and raw_duration > 0
            and raw_duration < audio_duration * 0.1
        ):
            scale_factor = audio_duration / raw_duration
            logger.warning(
                "[transcribe] timestamps compressed (%.1fs vs %.1fs actual). Rescaling by %.1fx",
                raw_duration, audio_duration, scale_factor,
            )
            for seg in formatted_segments:
                seg["start"] *= scale_factor
                seg["end"] *= scale_factor
            raw_duration = formatted_segments[-1]["end"] if formatted_segments else 0.0

        # Bersihkan hallucination sebelum return
        formatted_segments = _clean_hallucinations(
            formatted_segments, video_duration=audio_duration, task_id=task_id
        )

        duration = (
            min(formatted_segments[-1]["end"], audio_duration or raw_duration)
            if formatted_segments
            else 0.0
        )
        msg = f"[transcribe] Gemini returned {len(formatted_segments)} segments with speaker detection"
        logger.info(msg)
        _update_gemini_progress(task_id, 34.0, msg)

        return {"duration": duration, "segments": formatted_segments}

    except Exception as e:
        import traceback
        logger.error("[transcribe] Gemini transcription API failed: %s", e)
        logger.debug(traceback.format_exc())
        raise RuntimeError(f"Gemini API failed: {e}") from e
