"""FastAPI application entry point.

Run locally:
    uvicorn app.main:app --reload --port 8003
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from redis.exceptions import RedisError

from . import config
from .routes import media, tasks
from .state import store


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Suppress harmless WinError 10054 noise from asyncio event loop
    import asyncio

    loop = asyncio.get_running_loop()
    _orig_handler = loop.get_exception_handler()

    def _filter_asyncio_error(loop, context):
        exc = context.get("exception")
        if isinstance(exc, ConnectionResetError):
            return
        (_orig_handler or loop.default_exception_handler)(loop, context)

    loop.set_exception_handler(_filter_asyncio_error)

    # Ensure storage dir exists on boot.
    Path(config.STORAGE_DIR).mkdir(parents=True, exist_ok=True)
    app.state.store = store
    # Auto-recover tasks yang ada di storage tapi hilang dari state (e.g. setelah server restart)
    try:
        recovered = await store.recover_from_storage()
        if recovered:
            logging.getLogger(__name__).info(
                "Boot recovery: %d task(s) recovered from storage", recovered
            )
    except (OSError, RedisError) as exc:
        logging.getLogger(__name__).warning("Boot recovery failed: %s", exc)
    logging.getLogger(__name__).info(
        "CORS allowed origins: %s", config.CORS_ORIGINS
    )
    yield
    # --- shutdown ---
    try:
        await store.close()
    except Exception:
        logging.getLogger(__name__).warning("Error closing store", exc_info=True)


class _SuppressConnectionResetError(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if (
            record.exc_info
            and record.exc_info[1]
            and isinstance(record.exc_info[1], ConnectionResetError)
        ):
            return False
        return True


logging.getLogger("uvicorn.error").addFilter(_SuppressConnectionResetError())

app = FastAPI(
    title="Clip-AI Backend",
    description="YouTube → viral 9:16 shorts. FastAPI wrapper over the backend engine.",
    version="0.1.8",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def restrict_to_localhost(request: Request, call_next):
    # Restricted to localhost client IP only for security (anti port-forwarding / SSRF)
    if not request.client or request.client.host == "testclient":
        # Internal test client requests (no client IP or testclient host) are allowed
        return await call_next(request)

    client_host = request.client.host
    import ipaddress
    try:
        client_ip = ipaddress.ip_address(client_host)
        if not (client_ip.is_loopback or client_host in ("localhost", "127.0.0.1", "::1")):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={"error": "Forbidden: Access restricted to localhost"})
    except ValueError:
        if client_host not in ("localhost", "127.0.0.1", "::1"):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={"error": "Forbidden: Access restricted to localhost"})
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


app.include_router(tasks.router)
app.include_router(media.router)


@app.get("/health")
async def health() -> dict:
    """Liveness + dependency probe."""
    storage_ok = Path(config.STORAGE_DIR).exists()
    redis_ok = False
    try:
        redis_ok = await store.ping_redis()
    except Exception:
        pass
    return {
        "status": "ok",
        "ready": True,
        "storage": str(config.STORAGE_DIR),
        "storage_ok": storage_ok,
        "redis": redis_ok,
        "llm_provider": config.LLM_PROVIDER,
    }


@app.get("/encoders")
async def list_encoders() -> dict:
    """Detect available ffmpeg encoders on this machine."""
    return {
        "available": config.get_available_encoders(),
        "current": config.FFMPEG_ENCODER,
    }


@app.get("/video-info")
async def video_info(url: str) -> dict:
    """Fetch YouTube video metadata (title, author, thumbnail) via oEmbed."""
    import re
    import requests
    from fastapi.concurrency import run_in_threadpool

    # SSRF Protection: Validate that the url matches a legitimate YouTube format
    youtube_pattern = re.compile(
        r'^(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)[a-zA-Z0-9_-]{11}(&.*)?$'
    )
    if not youtube_pattern.match(url):
        return {"title": "", "author": "", "thumbnail": "", "error": "Invalid YouTube URL"}

    def _fetch_oembed():
        try:
            r = requests.get("https://www.youtube.com/oembed", params={"url": url, "format": "json"}, timeout=5)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    result = await run_in_threadpool(_fetch_oembed)
    if result:
        return {
            "title": result.get("title", ""),
            "author": result.get("author_name", ""),
            "thumbnail": result.get("thumbnail_url", ""),
        }

    # Fallback: yt-dlp info extract (no download)
    try:
        import subprocess, json as _json
        cmd = ["yt-dlp", "--dump-json", "--no-download", url]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        if r.returncode == 0:
            data = _json.loads(r.stdout)
            return {
                "title": data.get("title", ""),
                "author": data.get("uploader", ""),
                "thumbnail": data.get("thumbnail", ""),
            }
    except Exception:
        pass

    return {"title": "", "author": "", "thumbnail": ""}


@app.get("/debug/providers")
async def debug_providers() -> dict:
    """Diagnostic endpoint to verify transcription provider readiness."""
    from .engine.transcriber import GEMINI_API_KEY, GROQ_API_KEY

    groq_sdk = False
    gemini_sdk = False
    youtube_sdk = False
    groq_import_error = None
    gemini_import_error = None
    youtube_import_error = None

    try:
        import groq  # noqa: F401

        groq_sdk = True
    except Exception as e:
        groq_import_error = str(e)

    try:
        from google import genai  # noqa: F401

        gemini_sdk = True
    except Exception as e:
        gemini_import_error = str(e)

    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # noqa: F401

        youtube_sdk = True
    except Exception as e:
        youtube_import_error = str(e)

    return {
        "groq_sdk": groq_sdk,
        "gemini_sdk": gemini_sdk,
        "youtube_sdk": youtube_sdk,
        "groq_key_present": bool(GROQ_API_KEY),
        "gemini_key_present": bool(GEMINI_API_KEY),
        "groq_import_error": groq_import_error,
        "gemini_import_error": gemini_import_error,
        "youtube_import_error": youtube_import_error,
    }


@app.get("/debug/build")
async def debug_build() -> dict:
    """Diagnostic endpoint to identify the running backend build."""
    import os

    return {
        "version": config._get("APP_VERSION", "0.1.7"),
        "pid": os.getpid(),
    }


@app.get("/debug/storage")
async def debug_storage() -> dict:
    """Diagnostic endpoint showing resolved storage directory.

    Helps verify that the STORAGE_DIR env var set by Tauri is correctly
    picked up by the Python backend (dev mode uses env var only, no
    --storage-dir arg).
    """
    import os
    from pathlib import Path

    raw = os.getenv("STORAGE_DIR", "")
    resolved = Path(config.STORAGE_DIR)
    return {
        "env_var": raw or "(not set, using default)",
        "resolved": str(resolved),
        "is_absolute": resolved.is_absolute(),
        "exists": resolved.exists(),
        "task_count": sum(1 for p in resolved.iterdir() if p.is_dir()) if resolved.exists() else 0,
    }


@app.get("/debug/cors")
async def debug_cors() -> dict:
    """Diagnostic endpoint showing allowed CORS origins."""
    return {"allowed_origins": config.CORS_ORIGINS}


@app.get("/models")
async def list_models(base_url: str, api_key: str | None = Header(None)) -> dict:
    """Proxy to fetch available models from an OpenAI-compatible endpoint, solving CORS."""
    import asyncio
    import ipaddress
    import socket
    from urllib.parse import urlparse

    import requests
    from fastapi.concurrency import run_in_threadpool

    if not base_url:
        return {"data": []}

    parsed = urlparse(base_url)
    # Scheme validation (PR #57: prevent file:/// and other non-HTTP schemes)
    if parsed.scheme not in ("http", "https"):
        return {"data": [], "error": "Untrusted scheme"}

    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    if not host:
        return {"data": [], "error": "Invalid host"}

    # SSRF protection: Resolve host asynchronously and validate against loopback/0.0.0.0
    loop = asyncio.get_running_loop()
    try:
        addr_info = await loop.getaddrinfo(host, port)
        valid_ip = None
        for result in addr_info:
            ip = result[4][0]
            ip_obj = ipaddress.ip_address(ip)
            if ip_obj.is_loopback or str(ip_obj) == "0.0.0.0":
                valid_ip = ip
                break

        if not valid_ip:
            return {"data": [], "error": "Untrusted host"}
    except socket.gaierror:
        return {"data": [], "error": "Cannot resolve host"}
    except ValueError:
        return {"data": [], "error": "Invalid IP address"}

    # Rewrite URL to use IP address to prevent DNS Rebinding / TOCTOU
    ip_host = f"[{valid_ip}]" if ":" in valid_ip else valid_ip
    netloc = f"{ip_host}:{port}" if parsed.port else ip_host
    safe_base_url = parsed._replace(netloc=netloc).geturl()

    formatted_url = safe_base_url.rstrip("/")
    if not formatted_url.endswith("/models"):
        formatted_url = f"{formatted_url}/models"

    headers = {"Content-Type": "application/json"}
    headers["Host"] = host
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:

        def _fetch():
            # disable redirects to prevent redirect to a non-local IP
            return requests.get(formatted_url, headers=headers, timeout=8, allow_redirects=False)

        response = await run_in_threadpool(_fetch)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and "data" in data:
                return data
            elif isinstance(data, list):
                return {"data": [{"id": m} for m in data]}
        return {"data": []}
    except Exception as e:
        logging.getLogger(__name__).warning("Proxy models request failed: %s", e)
        return {"data": [], "error": str(e)}
