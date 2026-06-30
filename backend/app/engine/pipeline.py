"""End-to-end pipeline orchestrator.

Blocking calls run via asyncio.to_thread to avoid stalling the event loop.
"""
import asyncio
import concurrent.futures
import json
import logging
from typing import Dict, List, Optional

import redis.exceptions

from ..config import FONTS_DIR, SUBTITLE_STYLE_DEFAULT, STORAGE_DIR
from ..state import store
from .downloader import download_video
from .highlights import get_highlights_async
from .llm import get_llm_fn
from .render import render_clips
from .subtitles import generate_ass
from .transcriber import transcribe_video

_logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Custom exception for pipeline errors."""


async def run_pipeline(
    task_id: str,
    url: str,
    num_clips: int,
    aspect_ratio: str,
    language: Optional[str],
    subtitle_style: Optional[str] = None,
    face_detector: str = "yunet",
    encoder: str = "auto",
    template: str = "podcast",
) -> None:
    try:
        await store.set_progress(task_id, 0, "DOWNLOAD", "Memulai unduhan…")
        source_path = await asyncio.to_thread(download_video, url, task_id)
        import os
        try:
            size_bytes = os.path.getsize(source_path)
            size_mb = size_bytes / (1024 * 1024)
            await store.set_progress(task_id, 15, "DOWNLOAD", f"Unduhan selesai ({size_mb:.1f} MB)")
        except Exception:
            await store.set_progress(task_id, 15, "DOWNLOAD", "Unduhan selesai")

        if store.is_cancelled(task_id):
            _logger.warning("Task %s cancelled after DOWNLOAD", task_id)
            return

        await store.set_progress(task_id, 15, "TRANSCRIBE", "Transkripsi video…")
        transcript = await asyncio.to_thread(transcribe_video, source_path, task_id, language, url)
        if not transcript.get("segments"):
            raise RuntimeError("No detectable speech.")
        await store.set_progress(task_id, 35, "TRANSCRIBE", "Transkripsi selesai")

        if store.is_cancelled(task_id):
            _logger.warning("Task %s cancelled after TRANSCRIBE", task_id)
            return

        # ── ANALYZE stage: 3 sub-steps dengan progress callback ke SSE ───────
        from ..config import LLM_PROVIDER, OPENAI_MODEL, GEMINI_MODEL, ANTHROPIC_MODEL
        provider = (LLM_PROVIDER or "openai").strip().lower()
        model = OPENAI_MODEL
        if provider == "gemini":
            model = GEMINI_MODEL
        elif provider == "anthropic":
            model = ANTHROPIC_MODEL

        await store.set_progress(task_id, 36, "ANALYZE", f"Analisis highlight via AI ({provider}: {model})…")
        llm_fn = get_llm_fn()

        # Thread-safe emitter — dipanggil dari dalam thread pool asyncio.to_thread
        loop = asyncio.get_running_loop()

        def _emit(pct: float, stage: str, message: str) -> None:
            """Emit progress dari dalam thread ke event loop utama."""
            try:
                future = asyncio.run_coroutine_threadsafe(
                    store.set_progress(task_id, pct, stage, message),
                    loop,
                )
                future.result(timeout=5)
            except (concurrent.futures.TimeoutError, RuntimeError, concurrent.futures.CancelledError, redis.exceptions.RedisError) as exc:
                _logger.debug("[EMIT] Failed to emit progress: %s", exc)

        is_auto = (num_clips == 0)
        target_limit = 10 if is_auto else num_clips

        highlights_result = await get_highlights_async(transcript, target_limit, llm_fn, _emit, template)
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
            
        if is_auto:
            sorted_highlights = sorted(all_highlights, key=lambda h: int(h.get("score", 0)), reverse=True)
            top = [h for h in sorted_highlights if int(h.get("score", 0)) >= 70]
            if not top and sorted_highlights:
                top = sorted_highlights[:1]
            top = top[:7]
        else:
            top = sorted(all_highlights, key=lambda h: int(h.get("score", 0)), reverse=True)[:num_clips]
            
        await store.set_progress(task_id, 50, "ANALYZE", f"Ditemukan {len(top)} highlight viral via {provider.upper()}")

        if store.is_cancelled(task_id):
            _logger.warning("Task %s cancelled after ANALYZE", task_id)
            return

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

        if store.is_cancelled(task_id):
            _logger.warning("Task %s cancelled after SUBTITLES", task_id)
            return

        # ── SMART_CROP + RENDER stage ────────────────────────────────────────
        await store.set_progress(task_id, 62, "SMART_CROP", f"Analisis face-crop untuk {len(top)} klip…")

        s_encoder = getattr(record, "encoder", None) or encoder
        s_sensitivity = getattr(record, "sensitivity", 50) or 50

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
            sensitivity=s_sensitivity,
            template=template,
        )

        clip_count = sum(1 for c in clips if c.get("clip_url"))
        
        # Write highlights.json manifest
        manifest = {"url": url, "clips": clips}
        manifest_path = STORAGE_DIR / task_id / "highlights.json"
        def _write_manifest() -> None:
            try:
                with open(manifest_path, "w", encoding="utf-8") as f:
                    json.dump(manifest, f, indent=2, ensure_ascii=False)
            except (OSError, TypeError, ValueError) as e:
                _logger.error("Failed to write highlights.json manifest: %s", e)
                raise RuntimeError(f"Gagal menulis file manifest highlights.json: {e}") from e

        await asyncio.to_thread(_write_manifest)

        # Cleanup intermediate files
        for filename in ["subtitles.ass", "transcript.json", "transcript.srt"]:
            p = STORAGE_DIR / task_id / filename
            if p.exists():
                try:
                    p.unlink()
                except Exception as e:
                    _logger.warning("Failed to delete intermediate file %s: %s", p, e)

        await store.update(task_id, status="completed", progress=100.0, stage="DONE", message=f"{clip_count} klip siap")
        if clips:
            await store.add_clips(task_id, clips)
        await store.publish(task_id, "done", {"clips": clip_count})

    except Exception as e:
        raise PipelineError(str(e)) from e
