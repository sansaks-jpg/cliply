"""End-to-end pipeline orchestrator.

Blocking calls run via asyncio.to_thread to avoid stalling the event loop.
"""
import asyncio
from typing import Dict, List, Optional

from ..config import FONTS_DIR, SUBTITLE_STYLE_DEFAULT, STORAGE_DIR
from ..state import store
from .downloader import download_video
from .highlights import get_highlights
from .llm import get_llm_fn
from .render import render_clips
from .subtitles import generate_ass
from .transcriber import transcribe_video


async def run_pipeline(
    task_id: str,
    url: str,
    num_clips: int,
    aspect_ratio: str,
    language: Optional[str],
    subtitle_style: Optional[str] = None,
    face_detector: str = "yunet",
) -> None:
    try:
        await store.set_progress(task_id, 0, "DOWNLOAD", "Starting download…")
        source_path = await asyncio.to_thread(download_video, url, task_id)
        await store.set_progress(task_id, 15, "DOWNLOAD", "Downloaded")

        await store.set_progress(task_id, 15, "TRANSCRIBE", "Transcribing…")
        transcript = await asyncio.to_thread(transcribe_video, source_path, task_id, language, url)
        if not transcript.get("segments"):
            raise RuntimeError("No detectable speech.")
        await store.set_progress(task_id, 35, "TRANSCRIBE", "Transcription done")

        await store.set_progress(task_id, 35, "ANALYZE", "Finding viral moments…")
        llm_fn = get_llm_fn()
        highlights_result = await asyncio.to_thread(get_highlights, transcript, num_clips, llm_fn)
        all_highlights: List[Dict] = highlights_result.get("highlights", [])
        if not all_highlights:
            raise RuntimeError("No viral highlights found.")
        top = sorted(all_highlights, key=lambda h: int(h.get("score", 0)), reverse=True)[:num_clips]
        await store.set_progress(task_id, 50, "ANALYZE", f"Found {len(top)} highlights")

        # Stage 5: Generate subtitle ASS file
        style_key = subtitle_style or SUBTITLE_STYLE_DEFAULT
        task_dir = str(STORAGE_DIR / task_id)
        ass_path = f"{task_dir}/subtitles.ass"
        fonts_dir = str(FONTS_DIR) if FONTS_DIR.exists() else None

        # Get custom overrides if set
        record = await store.get(task_id)
        s_font = getattr(record, "subtitle_font", None) if record else None
        s_color_primary = getattr(record, "subtitle_color_primary", None) if record else None
        s_color_highlight = getattr(record, "subtitle_color_highlight", None) if record else None

        await store.set_progress(task_id, 55, "SUBTITLES", f"Generating subtitles ({style_key})…")
        ass_path = await asyncio.to_thread(
            generate_ass,
            transcript.get("segments", []),
            style_key,
            ass_path,
            1080,   # play_res_x — will be updated by render based on actual crop dims
            1920,   # play_res_y
            fonts_dir,
            s_font,
            s_color_primary,
            s_color_highlight,
        )
        await store.set_progress(task_id, 60, "SUBTITLES", "Subtitles ready")

        # Stage 6: Render vertical clips with subtitle burn-in
        clips = await asyncio.to_thread(
            render_clips,
            source_path,
            top,
            task_id,
            aspect_ratio,
            ass_path,
            fonts_dir,
            subtitle_style=style_key,
            face_detector=face_detector,
            subtitle_font=s_font,
            subtitle_color_primary=s_color_primary,
            subtitle_color_highlight=s_color_highlight,
        )

        clip_count = sum(1 for c in clips if c.get("clip_url"))
        await store.update(task_id, status="completed", progress=100.0, stage="DONE", message=f"{clip_count} clips ready")
        for c in clips:
            await store.add_clip(task_id, c)
        await store.publish(task_id, "done", {"clips": clip_count})

    except Exception as e:
        await store.update(task_id, status="error", error=str(e))
        await store.publish(task_id, "error", {"error": str(e)})
