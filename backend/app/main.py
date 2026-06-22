"""FastAPI application entry point.

Run locally:
    uvicorn app.main:app --reload --port 8003
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from redis.exceptions import RedisError

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

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
            logging.getLogger(__name__).info("Boot recovery: %d task(s) recovered from storage", recovered)
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
        if record.exc_info and record.exc_info[1] and isinstance(record.exc_info[1], ConnectionResetError):
            return False
        return True

logging.getLogger("uvicorn.error").addFilter(_SuppressConnectionResetError())

app = FastAPI(
    title="Clip-AI Backend",
    description="YouTube → viral 9:16 shorts. FastAPI wrapper over the "
    "backend engine.",
    version="0.1.1",
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


@app.get("/models")
async def list_models(base_url: str, api_key: str = "") -> dict:
    """Proxy to fetch available models from an OpenAI-compatible endpoint, solving CORS."""
    import requests
    from fastapi.concurrency import run_in_threadpool
    if not base_url:
        return {"data": []}
    
    formatted_url = base_url.rstrip("/")
    if not formatted_url.endswith("/models"):
        formatted_url = f"{formatted_url}/models"
        
    headers = {
        "Content-Type": "application/json"
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        
    try:
        def _fetch():
            return requests.get(formatted_url, headers=headers, timeout=8)
            
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

