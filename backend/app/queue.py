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
        log.error("Failed to enqueue task %s: task record not found in state store", task_id)
        return

    url = record.url
    num_clips = record.num_clips
    aspect_ratio = record.aspect_ratio
    language = record.language
    subtitle_style = record.subtitle_style
    face_detector = getattr(record, "face_detector", "yunet")
    encoder = getattr(record, "encoder", "auto")
    template = getattr(record, "template", "podcast")

    asyncio.create_task(_run_pipeline_wrapper(task_id, url, num_clips, aspect_ratio, language, subtitle_style, face_detector, encoder, template))


# Limit maximum concurrent running pipelines to prevent resource exhaustion (CPU/GPU/API rate limits)
_pipeline_semaphore = asyncio.Semaphore(2)


async def _run_pipeline_wrapper(
    task_id: str,
    url: str,
    num_clips: int,
    aspect_ratio: str,
    language: Optional[str],
    subtitle_style: Optional[str],
    face_detector: str,
    encoder: str,
    template: str,
) -> None:
    from .engine.pipeline import run_pipeline, PipelineError
    if store.is_cancelled(task_id):
        log.warning("Task %s cancelled before starting — skipping pipeline", task_id)
        return

    # Wait for slot to become available with a timeout limit (e.g. 1 hour total) to prevent starvation
    try:
        async with asyncio.timeout(3600):
            async with _pipeline_semaphore:
                # Check cancellation again in case it got cancelled while waiting in queue
                if store.is_cancelled(task_id):
                    log.warning("Task %s cancelled while waiting in queue — skipping pipeline", task_id)
                    return

                try:
                    await run_pipeline(task_id, url, num_clips, aspect_ratio, language, subtitle_style, face_detector, encoder, template)
                except PipelineError as e:
                    log.exception("pipeline crashed for task %s", task_id)
                    await store.update(task_id, status="error", error=str(e))
                    await store.publish(task_id, "error", {"error": str(e)})
                except Exception as e:
                    log.exception("unexpected error for task %s", task_id)
                    await store.update(task_id, status="error", error=str(e))
                    await store.publish(task_id, "error", {"error": str(e)})
    except TimeoutError:
        log.error("Task %s timed out waiting in pipeline queue (starvation check failed)", task_id)
        await store.update(task_id, status="error", error="Antrean tugas terlalu lama (timeout 1 jam). Silakan coba lagi.")
        await store.publish(task_id, "error", {"error": "Timeout antrean terlampaui."})
