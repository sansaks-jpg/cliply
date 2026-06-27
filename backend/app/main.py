"""FastAPI application entry point.

Run locally:
    uvicorn app.main:app --reload --port 8003
"""

import logging
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
    version="0.1.3",
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
        "groq_key_length": len(GROQ_API_KEY),
        "gemini_key_length": len(GEMINI_API_KEY),
        "groq_import_error": groq_import_error,
        "gemini_import_error": gemini_import_error,
        "youtube_import_error": youtube_import_error,
    }


@app.get("/debug/build")
async def debug_build() -> dict:
    """Diagnostic endpoint to identify the running backend build."""
    import os

    return {
        "version": config._get("APP_VERSION", "0.1.3"),
        "pid": os.getpid(),
    }


@app.get("/models")
async def list_models(base_url: str, api_key: str | None = Header(None)) -> dict:
    """Proxy to fetch available models from an OpenAI-compatible endpoint, solving CORS."""
    import asyncio
    import ipaddress
    import socket
    from urllib.parse import urlparse, urlunparse

    import requests
    from fastapi.concurrency import run_in_threadpool

    if not base_url:
        return {"data": []}

    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    if not host:
        return {"data": [], "error": "Invalid URL"}
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        loop = asyncio.get_running_loop()
        addr_info = await loop.getaddrinfo(
            host, port, family=socket.AF_INET, type=socket.SOCK_STREAM
        )
        resolved_ip = addr_info[0][4][0]
    except Exception as e:
        return {"data": [], "error": f"DNS resolution failed: {e}"}

    try:
        ip_obj = ipaddress.ip_address(resolved_ip)
    except ValueError:
        return {"data": [], "error": "Invalid IP address resolved"}

    # SSRF protection: deny internal/loopback/metadata IPs unless it's explicitly trusted localhost
    if host not in {"localhost", "127.0.0.1", "0.0.0.0"}:
        if (
            ip_obj.is_loopback
            or ip_obj.is_private
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or not ip_obj.is_global
            or str(ip_obj) == "169.254.169.254"
        ):
            return {"data": [], "error": "Untrusted destination IP"}

    # To prevent TOCTOU DNS rebinding, we must connect using the resolved IP.
    # However, rewriting the URL to use the IP directly causes TLS certificate
    # validation to fail (since the cert is for the hostname). Disabling `verify`
    # is a severe security risk as it exposes API keys to MITM attacks.
    # Instead, we mount a custom HTTPAdapter on requests to force the IP connection
    # while preserving the original URL (and thus hostname) for correct TLS SNI validation.
    formatted_url = base_url.rstrip("/")
    if not formatted_url.endswith("/models"):
        formatted_url = f"{formatted_url}/models"

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    class _HostHeaderAdapter(requests.adapters.HTTPAdapter):
        def __init__(self, resolved_ip, *args, **kwargs):
            self.resolved_ip = resolved_ip
            super().__init__(*args, **kwargs)

        def get_connection(self, url, proxies=None):
            conn = super().get_connection(url, proxies)
            conn.host = self.resolved_ip
            return conn

    try:

        def _fetch():
            with requests.Session() as s:
                prefix = f"{parsed.scheme}://{host}"
                s.mount(prefix, _HostHeaderAdapter(resolved_ip))
                return s.get(formatted_url, headers=headers, timeout=8)

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
