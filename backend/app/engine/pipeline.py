"""End-to-end pipeline orchestrator.

Blocking calls run via asyncio.to_thread to avoid stalling the event loop.
"""
import asyncio
import json
import logging
from typing import Callable, Dict, List, Optional

from ..config import FONTS_DIR, SUBTITLE_STYLE_DEFAULT, STORAGE_DIR, FFMPEG_ENCODER
from ..state import store
from .downloader import download_video
from .highlights import get_highlights
from .llm import get_llm_fn
from .render import render_clips
from .subtitles import generate_ass
from .transcriber import transcribe_video

_logger = logging.getLogger(__name__)


async def run_pipeline(
    task_id: str,
    url: str,
    num_clips: int,
    aspect_ratio: str,
    language: Optional[str],
    subtitle_style: Optional[str] = None,
    face_detector: str = "yunet",
    encoder: str = "auto",
) -> None:
    try:
        await store.set_progress(task_id, 0, "DOWNLOAD", "Memulai unduhan…")
        source_path = await asyncio.to_thread(download_video, url, task_id)
        await store.set_progress(task_id, 15, "DOWNLOAD", "Unduhan selesai")

        await store.set_progress(task_id, 15, "TRANSCRIBE", "Transkripsi video…")
        transcript = await asyncio.to_thread(transcribe_video, source_path, task_id, language, url)
        if not transcript.get("segments"):
            raise RuntimeError("No detectable speech.")
        await store.set_progress(task_id, 35, "TRANSCRIBE", "Transkripsi selesai")

        # ── ANALYZE stage: 3 sub-steps dengan progress callback ke SSE ───────
        await store.set_progress(task_id, 36, "ANALYZE", "Mendeteksi tipe & kepadatan konten…")
        llm_fn = get_llm_fn()

        # Thread-safe emitter — dipanggil dari dalam thread pool asyncio.to_thread
        loop = asyncio.get_event_loop()

        def _emit(pct: float, stage: str, message: str) -> None:
            """Emit progress dari dalam thread ke event loop utama."""
            try:
                future = asyncio.run_coroutine_threadsafe(
                    store.set_progress(task_id, pct, stage, message),
                    loop,
                )
                future.result(timeout=5)
            except Exception as exc:
                _logger.debug("[EMIT] Failed to emit progress: %s", exc)

        highlights_result = await asyncio.to_thread(
            get_highlights, transcript, num_clips, llm_fn, _emit
        )
        all_highlights: List[Dict] = highlights_result.get("highlights", [])
        if not all_highlights:
            raise RuntimeError("No viral highlights found.")
            
        failed_chunks = highlights_result.get("failed_chunks", [])
        coverage_pct = highlights_result.get("coverage_pct", 100)
        if failed_chunks:
            _logger.warning(
                "[PIPELINE] Partial failure during highlights analysis. "
                "Coverage: %d%%. Chunks failed starting at: %s",
                coverage_pct, failed_chunks
            )
            await store.set_progress(task_id, 45, "ANALYZE", f"Analisis {coverage_pct}% video selesai (ada rate-limit)")
            
        top = sorted(all_highlights, key=lambda h: int(h.get("score", 0)), reverse=True)[:num_clips]
        await store.set_progress(task_id, 50, "ANALYZE", f"Ditemukan {len(top)} highlight viral")

        # ── SUBTITLES stage ──────────────────────────────────────────────────
        style_key = subtitle_style or SUBTITLE_STYLE_DEFAULT
        task_dir = str(STORAGE_DIR / task_id)
        ass_path = f"{task_dir}/subtitles.ass"
        fonts_dir = str(FONTS_DIR) if FONTS_DIR.exists() else None

        record = await store.get(task_id)
        s_font = getattr(record, "subtitle_font", None) if record else None
        s_color_primary = getattr(record, "subtitle_color_primary", None) if record else None
        s_color_highlight = getattr(record, "subtitle_color_highlight", None) if record else None

        await store.set_progress(task_id, 55, "SUBTITLES", f"Membuat subtitle karaoke ({style_key})…")
        ass_path = await asyncio.to_thread(
            generate_ass,
            transcript.get("segments", []),
            style_key,
            ass_path,
            1080,
            1920,
            fonts_dir,
            s_font,
            s_color_primary,
            s_color_highlight,
        )
        await store.set_progress(task_id, 60, "SUBTITLES", "Subtitle siap")

        # ── SMART_CROP + RENDER stage ────────────────────────────────────────
        await store.set_progress(task_id, 62, "SMART_CROP", f"Analisis face-crop untuk {len(top)} klip…")

        s_encoder = getattr(record, "encoder", None) or encoder

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
            encoder=s_encoder,
        )

        clip_count = sum(1 for c in clips if c.get("clip_url"))
        
        # Write highlights.json manifest
        manifest = {"url": url, "clips": clips}
        manifest_path = STORAGE_DIR / task_id / "highlights.json"
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
        except Exception as e:
            _logger.warning("Failed to write highlights.json manifest: %s", e)

        await store.update(task_id, status="completed", progress=100.0, stage="DONE", message=f"{clip_count} klip siap")
        for c in clips:
            await store.add_clip(task_id, c)
        await store.publish(task_id, "done", {"clips": clip_count})

    except Exception as e:
        await store.update(task_id, status="error", error=str(e))
        await store.publish(task_id, "error", {"error": str(e)})
