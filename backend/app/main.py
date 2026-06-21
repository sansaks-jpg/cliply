"""FastAPI application entry point.

Run locally:
    uvicorn app.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .routes import media, tasks
from .state import store


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure storage dir exists on boot.
    Path(config.STORAGE_DIR).mkdir(parents=True, exist_ok=True)
    app.state.store = store
    # Auto-recover tasks yang ada di storage tapi hilang dari state (e.g. setelah server restart)
    try:
        recovered = await store.recover_from_storage()
        if recovered:
            import logging
            logging.getLogger(__name__).info("Boot recovery: %d task(s) recovered from storage", recovered)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Boot recovery failed: %s", exc)
    yield


app = FastAPI(
    title="Clip-AI Backend",
    description="YouTube → viral 9:16 shorts. FastAPI wrapper over the "
    "backend engine.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(media.router)


@app.get("/health")
async def health() -> dict:
    """Liveness + dependency probe."""
    storage_ok = Path(config.STORAGE_DIR).exists()
    return {
        "status": "ok",
        "storage": str(config.STORAGE_DIR),
        "storage_ok": storage_ok,
        "llm_provider": config.LLM_PROVIDER,
    }


@app.get("/encoders")
async def list_encoders() -> dict:
    """Detect available ffmpeg encoders on this machine."""
    return {
        "available": config.get_available_encoders(),
        "current": config.FFMPEG_ENCODER,
    }
