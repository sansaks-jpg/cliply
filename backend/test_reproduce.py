import logging
import os
import shutil
import sys
from pathlib import Path

# Clear old log file
log_file = "repro_run.log"
if os.path.exists(log_file):
    os.remove(log_file)

# Set up logging to both stdout and a file with INFO level
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ],
)

logger = logging.getLogger("test_repro")

# Add the parent directory to python path so we can import app
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dotenv

dotenv.load_dotenv()

from app.config import STORAGE_DIR
from app.engine.downloader import download_video
from app.engine.transcriber import transcribe_video


def run_repro():
    video_url = "https://youtu.be/xEah8NzNrGQ"
    task_id = "test_repro_task"

    task_dir = STORAGE_DIR / task_id
    if task_dir.exists():
        logger.info(f"Cleaning existing task dir {task_dir}")
        shutil.rmtree(task_dir)

    logger.info(f"Stage 1: Downloading video from {video_url}...")
    try:
        video_path = download_video(video_url, task_id)
        logger.info(f"Video downloaded successfully to: {video_path}")
        logger.info(f"File size: {os.path.getsize(video_path)} bytes")
    except Exception as e:
        logger.error(f"Download failed: {e}", exc_info=True)
        return

    logger.info("Stage 2: Transcribing video...")
    try:
        transcript = transcribe_video(video_path, task_id, video_url=video_url)
        logger.info("Transcription succeeded!")
        logger.info(f"Transcript segments count: {len(transcript.get('segments', []))}")
        # Print a few segments
        for seg in transcript.get("segments", [])[:5]:
            logger.info(f"Segment: {seg}")
    except Exception as e:
        logger.error(f"Transcription failed: {e}", exc_info=True)


if __name__ == "__main__":
    run_repro()
