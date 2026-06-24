import faulthandler
import os
import sys
import threading
import time
from pathlib import Path

# Enable faulthandler to dump stack trace on SIGINT (Ctrl+C) or after timeout
faulthandler.enable()

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dotenv

dotenv.load_dotenv()

from app.engine.transcriber import _try_groq_whisper

audio_path = "storage/test_repro_task/audio.mp3"
task_id = "test_repro_task"


# Start a watchdog thread that will dump stack traces after 15 seconds
def watchdog():
    time.sleep(15)
    print("=== WATCHDOG TIMEOUT: Dumping active thread frames ===", file=sys.stderr)
    import traceback

    for thread_id, frame in sys._current_frames().items():
        print(f"\n--- Thread ID: {thread_id} ---", file=sys.stderr)
        traceback.print_stack(frame, file=sys.stderr)
    print("=== END OF DUMP ===", file=sys.stderr)
    os._exit(1)  # force exit


wd = threading.Thread(target=watchdog, daemon=True)
wd.start()

print("Calling _try_groq_whisper directly (faulthandler enabled)...")
_try_groq_whisper(audio_path, task_id)
print("Finished!")
