"""Runtime configuration for the FastAPI clip service.

All settings come from environment variables (loaded from `.env` at import).
Defaults match the values in `backend/.env.example`.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

log = logging.getLogger(__name__)

# Load .env from the repo root (backend/.env)
# override=False prevents .env from overwriting env vars already set by
# the runtime (Docker, CI, systemd, Tauri), which are considered authoritative.
_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env", override=False)


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _get_int(key: str, default: int) -> int:
    try:
        return int(_get(key, str(default)))
    except ValueError:
        return default


def _get_positive_int(key: str, default: int) -> int:
    value = _get_int(key, default)
    return value if value > 0 else default


# --- LLM (pluggable) ---------------------------------------------------------
LLM_PROVIDER = _get("LLM_PROVIDER", "openai").lower()
OPENAI_API_KEY = _get("OPENAI_API_KEY")
OPENAI_BASE_URL = _get("OPENAI_BASE_URL", "http://127.0.0.1:20128/v1")
OPENAI_MODEL = _get("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = _get("ANTHROPIC_MODEL", "claude-haiku-4")
GEMINI_API_KEY = _get("GEMINI_API_KEY")
GEMINI_MODEL = _get("GEMINI_MODEL", "gemini-2.5-flash")

# --- Pipeline defaults -------------------------------------------------------
NUM_CLIPS_DEFAULT = max(1, _get_int("NUM_CLIPS_DEFAULT", 5))
ASPECT_RATIO_DEFAULT = _get("ASPECT_RATIO_DEFAULT", "9:16")
SUBTITLE_STYLE_DEFAULT = _get("SUBTITLE_STYLE_DEFAULT", "viral-bold")
DOWNLOAD_FORMAT = _get("DOWNLOAD_FORMAT", "1080")
WHISPER_MODEL = _get("WHISPER_MODEL", "base")
WHISPER_DEVICE = _get("WHISPER_DEVICE", "auto")
LONG_VIDEO_THRESHOLD = _get_positive_int("LONG_VIDEO_THRESHOLD", 1800)
CHUNK_SIZE_SECONDS = _get_positive_int("CHUNK_SIZE_SECONDS", 1200)
CHUNK_OVERLAP_SECONDS = _get_int("CHUNK_OVERLAP_SECONDS", 60)
HIGHLIGHT_MAX_WORKERS = _get_positive_int("HIGHLIGHT_MAX_WORKERS", 8)

# --- FFmpeg encoder ----------------------------------------------------------
from .services.encoder_detection import detect_encoders as _detect_encoders

FFMPEG_ENCODER = _get("FFMPEG_ENCODER", "auto").lower()

ENCODER_MAP: dict[str, str] = {
    "nvidia": "h264_nvenc -preset p4 -rc vbr -cq 20",
    "intel": "h264_qsv -global_quality 20",
    "amd": "h264_amf -quality quality -usage transcoding",
    "cpu": "libx264 -preset fast -crf 20",
}


def get_available_encoders() -> list[str]:
    """Return list of encoder keys available on this machine."""
    avail = _detect_encoders()
    keys = ["auto"]
    for k in ("nvidia", "intel", "amd"):
        if avail.get(k):
            keys.append(k)
    keys.append("cpu")
    return keys


def resolve_encoder(encoder: str) -> str:
    """Return ffmpeg `-c:v ...` args string for the given encoder key.

    'auto' → picks first available HW encoder, falls back to libx264.
    """
    if encoder == "auto":
        avail = _detect_encoders()
        for hw in ("nvidia", "intel", "amd"):
            if avail.get(hw):
                return ENCODER_MAP[hw]
        return ENCODER_MAP["cpu"]
    return ENCODER_MAP.get(encoder, ENCODER_MAP["cpu"])


# --- Infra -------------------------------------------------------------------
REDIS_URL = _get("REDIS_URL", "redis://localhost:6379")
# Storage dir: prefer env var (set by Tauri), then Tauri settings.json, then default.
_STORAGE_ENV = _get("STORAGE_DIR")
if not _STORAGE_ENV:
    # Fallback: read from Tauri settings.json (Roaming app config)
    import json as _json
    for _tauri_dir in [
        Path(os.environ.get("APPDATA", "")) / "com.cliply.app",
        Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "com.cliply.app",
    ]:
        _tauri_settings = _tauri_dir / "settings.json"
        if _tauri_settings.exists():
            try:
                _ts = _json.loads(_tauri_settings.read_text(encoding="utf-8"))
                _ts_dir = _ts.get("storage_dir", "")
                if _ts_dir:
                    _STORAGE_ENV = _ts_dir
                    log.info("STORAGE_DIR from Tauri settings: %s", _ts_dir)
                    break
            except (OSError, ValueError):
                pass

STORAGE_DIR = Path(_STORAGE_ENV or "./storage")
if not STORAGE_DIR.is_absolute():
    STORAGE_DIR = (_REPO_ROOT / STORAGE_DIR).resolve()

log.info("STORAGE_DIR resolved to: %s (env=%s)", STORAGE_DIR, _STORAGE_ENV or "(default)")

FONTS_DIR = Path(_get("FONTS_DIR", "./fonts"))
if not FONTS_DIR.is_absolute():
    FONTS_DIR = (_REPO_ROOT / FONTS_DIR).resolve()

CORS_ORIGINS = [
    "http://localhost:3107",
    "http://127.0.0.1:3107",
    "http://tauri.localhost",
    "tauri://localhost",
]
env_origins = _get("CORS_ORIGINS").split(",")
for origin in env_origins:
    o = origin.strip()
    if o and o not in CORS_ORIGINS:
        CORS_ORIGINS.append(o)
BACKEND_PORT = _get_positive_int("BACKEND_PORT", 8003)


@dataclass(frozen=True)
class RenderConstants:
    """Tuning parameters for the smart-crop renderer.

    All values can be overridden via environment variables prefixed with RENDER_.
    """

    SAMPLE_FPS: int = _get_positive_int("RENDER_SAMPLE_FPS", 2)
    EMA_FACTOR: float = float(_get("RENDER_EMA_FACTOR", "0.15"))
    CONFIDENCE_THRESHOLD: float = float(_get("RENDER_CONFIDENCE_THRESHOLD", "0.30"))
    CLOSEUP_THRESHOLD: float = float(_get("RENDER_CLOSEUP_THRESHOLD", "0.30"))
    MEDIUM_THRESHOLD: float = float(_get("RENDER_MEDIUM_THRESHOLD", "0.15"))
    LETTERBOX_BLUR: int = _get_positive_int("RENDER_LETTERBOX_BLUR", 61)
    CUT_THRESHOLD: float = float(_get("RENDER_CUT_THRESHOLD", "0.97"))
    MOTION_WEIGHT: float = float(_get("RENDER_MOTION_WEIGHT", "0.6"))
    SIZE_WEIGHT: float = float(_get("RENDER_SIZE_WEIGHT", "0.4"))
    GROUP_REACTION_MIN_FACES: int = _get_positive_int(
        "RENDER_GROUP_REACTION_MIN_FACES", 3
    )
    GROUP_REACTION_MOTION_THRESH: float = float(
        _get("RENDER_GROUP_REACTION_MOTION_THRESH", "0.3")
    )
    MIN_HOLD_SAMPLES: int = _get_positive_int("RENDER_MIN_HOLD_SAMPLES", 3)
    SWITCH_MARGIN: float = float(_get("RENDER_SWITCH_MARGIN", "0.15"))
    MIN_SHOT_HOLD_SAMPLES: int = _get_positive_int("RENDER_MIN_SHOT_HOLD_SAMPLES", 3)
    MAX_MISSED_SAMPLES: int = _get_positive_int("RENDER_MAX_MISSED_SAMPLES", 4)


# Singleton
RENDER_CFG = RenderConstants()


def require_llm_key() -> str:
    """Return the API key for the active LLM provider, or raise with guidance."""
    if LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to .env or switch LLM_PROVIDER."
            )
        return OPENAI_API_KEY
    if LLM_PROVIDER == "anthropic":
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to .env or switch LLM_PROVIDER."
            )
        return ANTHROPIC_API_KEY
    if LLM_PROVIDER == "gemini":
        if not GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to .env or switch LLM_PROVIDER."
            )
        return GEMINI_API_KEY
    raise RuntimeError(
        f"Unknown LLM_PROVIDER={LLM_PROVIDER!r}. Use 'openai', 'anthropic', or 'gemini'."
    )
