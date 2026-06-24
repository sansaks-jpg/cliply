import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("test_full")

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dotenv

dotenv.load_dotenv()

from app.engine.transcriber import (
    _download_audio,
    _try_gemini_transcription,
    _try_groq_whisper,
    _try_youtube_transcript,
)

video_url = "https://youtu.be/xEah8NzNrGQ"
task_id = "test_repro_task"
media_path = "storage/source_xEah8NzNrGQ.mp4"
audio_path = "storage/test_repro_task/audio.mp3"

logger.info("=== Testing Stage 1: YouTube Transcript API ===")
try:
    yt_res = _try_youtube_transcript(video_url)
    logger.info(f"YouTube Transcript Result: {bool(yt_res)}")
    if yt_res:
        logger.info(f"YouTube segments count: {len(yt_res.get('segments', []))}")
except Exception as e:
    logger.error(f"YouTube Transcript failed: {e}", exc_info=True)

logger.info("=== Extracting Audio for Groq / Gemini tests ===")
if not os.path.exists(audio_path):
    try:
        _download_audio(media_path, "storage/test_repro_task")
        logger.info("Audio extracted successfully.")
    except Exception as e:
        logger.error(f"Audio extraction failed: {e}", exc_info=True)
else:
    logger.info("Audio file already exists.")

logger.info("=== Testing Stage 2: Groq Whisper ===")
try:
    # Explicitly pass a custom timeout to client inside _try_groq_whisper
    # let's call it and see
    groq_res = _try_groq_whisper(audio_path, task_id)
    logger.info(f"Groq Result: {bool(groq_res)}")
    if groq_res:
        logger.info(f"Groq segments count: {len(groq_res.get('segments', []))}")
except Exception as e:
    logger.error(f"Groq failed: {e}", exc_info=True)

logger.info("=== Testing Stage 3: Gemini 2.5 Flash ===")
try:
    gemini_res = _try_gemini_transcription(audio_path, task_id)
    logger.info(f"Gemini Result: {bool(gemini_res)}")
    if gemini_res:
        logger.info(f"Gemini segments count: {len(gemini_res.get('segments', []))}")
except Exception as e:
    logger.error(f"Gemini failed: {e}", exc_info=True)
