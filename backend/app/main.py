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
