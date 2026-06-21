"""Task queue — enqueues pipeline via asyncio background task.
"""
import asyncio
import logging
from typing import Optional

from .state import store

log = logging.getLogger(__name__)


async def enqueue_task(task_id: str) -> None:
    record = await store.get(task_id)
    if record is None:
        return

    url = record.url
    num_clips = record.num_clips
    aspect_ratio = record.aspect_ratio
    language = record.language
    subtitle_style = record.subtitle_style
    face_detector = getattr(record, "face_detector", "yunet")
    encoder = getattr(record, "encoder", "auto")

    asyncio.create_task(_run_pipeline_wrapper(task_id, url, num_clips, aspect_ratio, language, subtitle_style, face_detector, encoder))


async def _run_pipeline_wrapper(
    task_id: str,
    url: str,
    num_clips: int,
    aspect_ratio: str,
    language: Optional[str],
    subtitle_style: Optional[str],
    face_detector: str,
    encoder: str,
) -> None:
    from .engine.pipeline import run_pipeline
    try:
        await run_pipeline(task_id, url, num_clips, aspect_ratio, language, subtitle_style, face_detector, encoder)
    except Exception as e:
        log.exception("pipeline crashed for task %s", task_id)
        await store.update(task_id, status="error", error=str(e))
        await store.publish(task_id, "error", {"error": str(e)})
