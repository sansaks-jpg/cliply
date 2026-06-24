import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("test_direct")

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dotenv

dotenv.load_dotenv()

from app.engine.transcriber import _try_groq_whisper

audio_path = "storage/test_repro_task/audio.mp3"
task_id = "test_repro_task"

logger.info("Calling _try_groq_whisper directly...")
res = _try_groq_whisper(audio_path, task_id)
logger.info("Result obtained!")
print("Result segments count:", len(res.get("segments", [])) if res else "None")
