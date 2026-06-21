"""Task routes: create, inspect, stream progress, delete.

Fase 0: `POST /tasks` records the job and returns an id; the actual pipeline
runs via `app.queue.enqueue_task` (Fase 1 makes it real, Fase 3 moves it
fully async with SSE).
"""
import re
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, HttpUrl

from .. import config
from ..state import store

router = APIRouter(prefix="/tasks", tags=["tasks"])

# Permissive YouTube URL check — covers youtu.be, /watch?v=, /shorts/, /embed/, /live/.
_YOUTUBE_RE = re.compile(
    r"^(https?://)?(www\.)?(youtube\.com/(watch\?v=|shorts/|embed/|live/)|youtu\.be/).+",
    re.IGNORECASE,
)

SubtitleStyle = Literal[
    "viral-bold", "minimalist", "neon-glow", "classic-popup",
    "word-pop", "clean-minimal", "highlight-box", "neon-gradient",
    "tiktok",
]


class CreateTaskRequest(BaseModel):
    url: str = Field(..., description="YouTube URL (youtu.be or youtube.com).")
    num_clips: Optional[int] = Field(default=None, ge=1, le=20)
    aspect_ratio: Optional[str] = Field(default=None, pattern=r"^\d+:\d+$")
    language: Optional[str] = Field(
        default=None, description="ISO-639-1 to force Whisper language; omit for auto."
    )
    subtitle_style: SubtitleStyle = Field(
        default="viral-bold",
        description="Subtitle animation style.",
    )
    face_detector: Optional[Literal["yunet", "mediapipe", "yolov8-face", "ssd"]] = Field(
        default="yunet",
        description="Face detector model to use.",
    )
    subtitle_font: Optional[str] = Field(default=None, description="Custom font override.")
    subtitle_color_primary: Optional[str] = Field(default=None, description="Custom primary text color override (#RRGGBB).")
    subtitle_color_highlight: Optional[str] = Field(default=None, description="Custom highlight color override (#RRGGBB).")
    encoder: Optional[str] = Field(default=None, description="Encoder: auto | nvidia | intel | amd | cpu")


class TaskCreatedResponse(BaseModel):
    task_id: str


@router.post("", response_model=TaskCreatedResponse, status_code=201)
async def create_task(req: CreateTaskRequest, request: Request) -> TaskCreatedResponse:
    """Create a generation task and enqueue it.

    Returns immediately with a `task_id`. Poll `GET /tasks/{id}` or connect
    to `GET /tasks/{id}/progress` (SSE) to watch progress.
    """
    if not _YOUTUBE_RE.match(req.url):
        raise HTTPException(
            status_code=422,
            detail="URL must be a YouTube link (youtu.be/... or youtube.com/watch?v=...).",
        )

    num_clips = req.num_clips or config.NUM_CLIPS_DEFAULT
    aspect_ratio = req.aspect_ratio or config.ASPECT_RATIO_DEFAULT

    encoder = req.encoder or config.FFMPEG_ENCODER

    task_id = await store.create(
        url=req.url,
        num_clips=num_clips,
        aspect_ratio=aspect_ratio,
        language=req.language,
        subtitle_style=req.subtitle_style,
        face_detector=req.face_detector,
        subtitle_font=req.subtitle_font,
        subtitle_color_primary=req.subtitle_color_primary,
        subtitle_color_highlight=req.subtitle_color_highlight,
        encoder=encoder,
    )

    # Enqueue the background pipeline (no-op stub in Fase 0; real in Fase 1).
    from ..queue import enqueue_task

    await enqueue_task(task_id)

    return TaskCreatedResponse(task_id=task_id)


@router.get("")
async def list_tasks() -> dict:
    records = await store.list()
    return {"tasks": [r.to_dict() for r in sorted(records, key=lambda r: r.created_at, reverse=True)]}


@router.get("/recover", status_code=200)
async def recover_tasks() -> dict:
    """Scan storage dan recover task yang hilang dari state (misalnya setelah server restart).
    
    Berguna jika frontend menunjukkan task yang sudah ada tapi backend
    mengembalikan 404 Not Found.
    """
    try:
        recovered = await store.recover_from_storage()
        records = await store.list()
        return {
            "recovered": recovered,
            "total_tasks": len(records),
            "message": f"{recovered} task(s) berhasil di-recover dari storage.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recovery gagal: {e}")


@router.get("/{task_id}")
async def get_task(task_id: str) -> dict:
    record = await store.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return record.to_dict()


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str) -> None:
    deleted = await store.delete(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found.")


@router.get("/{task_id}/progress")
async def task_progress(task_id: str, request: Request):
    """Server-Sent Events stream for one task.

    Emits `progress`, `clip_ready`, then a terminal `done` (or `error`).
    Falls back gracefully if the task doesn't exist — emits an `error` event
    so the client EventSource can surface it instead of hanging.
    """
    record = await store.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    async def event_generator():
        # Replay current state first, so a late subscriber sees the bar fill.
        if record.status in ("completed", "error", "cancelled"):
            yield _sse("progress", {
                "pct": record.progress,
                "stage": record.stage,
                "message": record.message,
            })
            for clip in record.clips:
                yield _sse("clip_ready", clip)
            yield _sse("done" if record.status == "completed" else "error",
                       {"error": record.error} if record.error else {})
            return

        # Already-terminal or not, hand off to live subscription.
        if record.status == "queued" and record.progress == 0.0:
            yield _sse("progress", {"pct": 0.0, "stage": "queued", "message": "Queued."})

        async for event, data in store.subscribe(task_id):
            yield _sse(event, data)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering if fronted
        },
    )


def _sse(event: str, data) -> str:
    import json
    payload = json.dumps(data) if not isinstance(data, str) else data
    return f"event: {event}\ndata: {payload}\n\n"
