"""Runtime configuration for the FastAPI clip service.

All settings come from environment variables (loaded from `.env` at import).
# Defaults match the values in `backend/.env.example`.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the repo root (backend/.env)
_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env", override=True)


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _get_int(key: str, default: int) -> int:
    try:
        return int(_get(key, str(default)))
    except ValueError:
        return default


# --- LLM (pluggable) ---------------------------------------------------------
LLM_PROVIDER = _get("LLM_PROVIDER", "openai").lower()
OPENAI_API_KEY = _get("OPENAI_API_KEY")
OPENAI_BASE_URL = _get("OPENAI_BASE_URL")
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
LONG_VIDEO_THRESHOLD = _get_int("LONG_VIDEO_THRESHOLD", 1800)
CHUNK_SIZE_SECONDS = _get_int("CHUNK_SIZE_SECONDS", 1200)
CHUNK_OVERLAP_SECONDS = _get_int("CHUNK_OVERLAP_SECONDS", 60)
HIGHLIGHT_MAX_WORKERS = _get_int("HIGHLIGHT_MAX_WORKERS", 8)

# --- FFmpeg encoder ----------------------------------------------------------
FFMPEG_ENCODER = _get("FFMPEG_ENCODER", "auto").lower()

ENCODER_MAP: dict[str, str] = {
    "nvidia": "h264_nvenc -preset p4 -rc vbr -cq 20",
    "intel":  "h264_qsv -global_quality 20",
    "amd":    "h264_amf -quality quality -usage transcoding",
    "cpu":    "libx264 -preset fast -crf 20",
}


_ENCODER_CACHE: dict[str, bool] | None = None


def _detect_encoders() -> dict[str, bool]:
    global _ENCODER_CACHE
    if _ENCODER_CACHE is not None:
        return _ENCODER_CACHE
    import subprocess, re

    # --- WMI: detect GPU vendors from actual hardware ---
    gpu_vendors: set[str] = set()
    try:
        output = subprocess.run(
            ["powershell", "-Command",
             "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=10,
        ).stdout.lower()
        gpu_vendors.update(re.findall(r"(nvidia|intel|amd|advanced micro devices|ati radeon)", output))
    except (OSError, subprocess.TimeoutExpired):
        pass

    has_nvidia_hw = any(k in gpu_vendors for k in ("nvidia",))
    has_intel_hw  = any(k in gpu_vendors for k in ("intel",))
    has_amd_hw    = any(k in gpu_vendors for k in ("amd", "advanced micro devices", "ati radeon"))

    # --- ffmpeg: check if encoder is compiled in ---
    ff_nvenc = ff_qsv = ff_amf = False
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
        ).stdout.lower()
        ff_nvenc = "nvenc" in out
        ff_qsv   = "qsv" in out
        ff_amf   = "amf" in out
    except (OSError, subprocess.TimeoutExpired):
        pass

    result: dict[str, bool] = {
        "nvidia": has_nvidia_hw and ff_nvenc,
        "intel":  has_intel_hw and ff_qsv,
        "amd":    has_amd_hw and ff_amf,
    }
    _ENCODER_CACHE = result
    return result


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
# Storage dir is resolved relative to the repo root and created lazily.
STORAGE_DIR = Path(_get("STORAGE_DIR", "./storage"))
if not STORAGE_DIR.is_absolute():
    STORAGE_DIR = (_REPO_ROOT / STORAGE_DIR).resolve()

FONTS_DIR = Path(_get("FONTS_DIR", "./fonts"))
if not FONTS_DIR.is_absolute():
    FONTS_DIR = (_REPO_ROOT / FONTS_DIR).resolve()

CORS_ORIGINS = [
    origin.strip()
    for origin in _get("CORS_ORIGINS", "http://localhost:3107").split(",")
    if origin.strip()
]
BACKEND_PORT = _get_int("BACKEND_PORT", 8000)


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
