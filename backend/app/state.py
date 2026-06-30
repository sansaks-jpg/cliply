"""Task state store — Redis-backed with in-memory fallback.

Module-level singleton `store` lazily chooses backend on first use.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from .config import REDIS_URL, STORAGE_DIR

log = logging.getLogger(__name__)

_TASK = "task:{}"
_CLIPS = "clip:{}"
_PROGRESS = "task:progress:{}"


@dataclass
class TaskRecord:
    task_id: str
    url: str
    num_clips: int
    aspect_ratio: str
    language: Optional[str]
    template: str = "podcast"
    subtitle_style: Optional[str] = None
    face_detector: Optional[str] = "yunet"
    subtitle_font: Optional[str] = None
    subtitle_color_primary: Optional[str] = None
    subtitle_color_highlight: Optional[str] = None
    encoder: Optional[str] = "auto"
    sensitivity: int = 50
    status: str = "queued"
    progress: float = 0.0
    stage: str = ""
    message: str = ""
    error: Optional[str] = None
    clips: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "url": self.url,
            "num_clips": self.num_clips,
            "aspect_ratio": self.aspect_ratio,
            "language": self.language or "",
            "template": self.template,
            "subtitle_style": self.subtitle_style or "",
            "face_detector": self.face_detector or "yunet",
            "subtitle_font": self.subtitle_font or "",
            "subtitle_color_primary": self.subtitle_color_primary or "",
            "subtitle_color_highlight": self.subtitle_color_highlight or "",
            "encoder": self.encoder or "auto",
            "sensitivity": self.sensitivity,
            "status": self.status,
            "progress": self.progress,
            "stage": self.stage,
            "message": self.message,
            "error": self.error or "",
            "clips": self.clips,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_redis_hash(self) -> Dict[str, Any]:
        """Serialize without clips (stored separately) and coerce types for Redis."""
        d = self.to_dict()
        d.pop("clips", None)
        return {k: v if isinstance(v, (int, float)) else str(v) for k, v in d.items()}


class TaskStore:
    def __init__(self):
        self._redis = None
        self._use_redis = False
        self._mem_tasks: Dict[str, TaskRecord] = {}
        self._mem_subs: Dict[str, List[asyncio.Queue]] = {}
        self._mem_lock = asyncio.Lock()
        self._cancelled: set[str] = set()
        self.loop = None

    async def _ensure_backend(self):
        if not self.loop:
            try:
                self.loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

        if self._redis is None:
            try:
                from redis.asyncio import Redis

                r = Redis.from_url(
                    REDIS_URL, decode_responses=True, socket_connect_timeout=2
                )
                await r.ping()
                self._redis = r
                self._use_redis = True
                log.info("TaskStore: Redis connected")
            except Exception as e:
                log.warning("TaskStore: Redis unavailable (%s), using in-memory", e)
                self._use_redis = False
        return self._use_redis

    async def ping_redis(self) -> bool:
        """Check Redis connectivity. Returns False if Redis is not in use or unreachable."""
        if self._redis is not None:
            try:
                await self._redis.ping()
                return True
            except Exception:
                return False
        return False

    async def close(self) -> None:
        """Close the Redis connection if open."""
        if self._redis is not None:
            try:
                await self._redis.close()
            except Exception:
                pass
            self._redis = None
            self._use_redis = False

    async def create(
        self,
        url: str,
        num_clips: int,
        aspect_ratio: str,
        language: Optional[str],
        template: str = "podcast",
        subtitle_style: Optional[str] = None,
        face_detector: Optional[str] = "yunet",
        subtitle_font: Optional[str] = None,
        subtitle_color_primary: Optional[str] = None,
        subtitle_color_highlight: Optional[str] = None,
        encoder: Optional[str] = "auto",
        sensitivity: int = 50,
    ) -> str:
        task_id = uuid.uuid4().hex[:12]
        record = TaskRecord(
            task_id=task_id,
            url=url,
            num_clips=num_clips,
            aspect_ratio=aspect_ratio,
            language=language,
            template=template,
            subtitle_style=subtitle_style,
            face_detector=face_detector,
            subtitle_font=subtitle_font,
            subtitle_color_primary=subtitle_color_primary,
            subtitle_color_highlight=subtitle_color_highlight,
            encoder=encoder,
            sensitivity=sensitivity,
        )
        if await self._ensure_backend():
            await self._redis.hmset(_TASK.format(task_id), record.to_redis_hash())
        else:
            async with self._mem_lock:
                self._mem_tasks[task_id] = record
                self._mem_subs[task_id] = []
        return task_id

    async def get(self, task_id: str) -> Optional[TaskRecord]:
        if await self._ensure_backend():
            data = await self._redis.hgetall(_TASK.format(task_id))
            if not data:
                return None
            clips = await self._redis.lrange(_CLIPS.format(task_id), 0, -1)
            if clips:
                data["clips"] = [json.loads(c) for c in clips]
            return self._record_from_dict(data)
        async with self._mem_lock:
            return self._mem_tasks.get(task_id)

    def _record_from_dict(self, data: dict) -> TaskRecord:
        for k in ("progress", "created_at", "updated_at"):
            if k in data:
                data[k] = float(data[k])
        if "num_clips" in data:
            data["num_clips"] = int(data["num_clips"])
        if "sensitivity" in data:
            data["sensitivity"] = int(data["sensitivity"])
        nullables = (
            "language",
            "error",
            "subtitle_style",
            "face_detector",
            "subtitle_font",
            "subtitle_color_primary",
            "subtitle_color_highlight",
            "encoder",
        )
        for k in nullables:
            if k in data and not data.get(k):
                data[k] = None
        for k, v in {
            "subtitle_style": None,
            "face_detector": "yunet",
            "subtitle_font": None,
            "subtitle_color_primary": None,
            "subtitle_color_highlight": None,
            "encoder": "auto",
            "sensitivity": 50,
            "clips": [],
        }.items():
            if k not in data:
                data[k] = v
        return TaskRecord(**data)

    async def list(self) -> List[TaskRecord]:
        if await self._ensure_backend():
            # Use SCAN instead of KEYS (non-blocking)
            keys = []
            async for key in self._redis.scan_iter(match=_TASK.format("*")):
                keys.append(key)
            records_data = []
            orphaned_ids = []
            # Batch HGETALL via pipeline (avoid N+1)
            if keys:
                pipe = self._redis.pipeline()
                for key in keys:
                    pipe.hgetall(key)
                hgetall_results = await pipe.execute()
                for data in hgetall_results:
                    if not data:
                        continue
                    tid = data.get("task_id", "")
                    task_dir = STORAGE_DIR / tid
                    if not task_dir.exists():
                        status = data.get("status", "")
                        # Grace period: task baru yang masih queued/processing mungkin belum sempat
                        # membuat storage dir (pipeline baru dimulai). Jangan hapus dulu selama
                        # masih dalam 5 menit pertama sejak dibuat.
                        created_at = float(data.get("created_at", 0) or 0)
                        age_seconds = time.time() - created_at
                        if status in ("queued", "processing") and age_seconds < 300:
                            # Task masih baru — masukkan ke records dan tunggu pipeline buat foldernya
                            records_data.append(data)
                            continue
                        if status in ("queued", "processing"):
                            # Orphaned processing task — data is stale, mark as error
                            log.warning(
                                "Zombie task %s: status=%s but storage missing — marking as error",
                                tid,
                                data.get("status"),
                            )
                        orphaned_ids.append(tid)
                        continue
                    records_data.append(data)
                # Batch LRANGE via pipeline
                if records_data:
                    clips_pipe = self._redis.pipeline()
                    for data in records_data:
                        clips_pipe.lrange(_CLIPS.format(data.get("task_id", "")), 0, -1)
                    clips_results = await clips_pipe.execute()
                    for data, clips_raw in zip(records_data, clips_results):
                        if clips_raw:
                            data["clips"] = [json.loads(c) for c in clips_raw]
            records = [self._record_from_dict(d) for d in records_data]
            # Clean orphaned records from Redis
            if orphaned_ids:
                keys_to_delete = []
                for tid in orphaned_ids:
                    keys_to_delete.extend([_TASK.format(tid), _CLIPS.format(tid)])
                if keys_to_delete:
                    await self._redis.delete(*keys_to_delete)
                for tid in orphaned_ids:
                    log.info("Auto-cleaned orphaned task %s (storage deleted)", tid)
            return sorted(records, key=lambda r: r.created_at, reverse=True)
        async with self._mem_lock:
            orphaned_ids = []
            for tid, r in self._mem_tasks.items():
                task_dir = STORAGE_DIR / tid
                if not task_dir.exists():
                    # Grace period: task baru yang masih queued/processing mungkin belum sempat
                    # membuat storage dir. Jangan hapus selama masih dalam 5 menit pertama.
                    age_seconds = time.time() - r.created_at
                    if r.status in ("queued", "processing") and age_seconds < 300:
                        continue
                    orphaned_ids.append(tid)
            for tid in orphaned_ids:
                self._mem_tasks.pop(tid, None)
                self._mem_subs.pop(tid, None)
                log.info("Auto-cleaned orphaned task %s (storage deleted)", tid)
            return sorted(
                self._mem_tasks.values(), key=lambda r: r.created_at, reverse=True
            )

    async def update(self, task_id: str, **fields) -> Optional[TaskRecord]:
        fields["updated_at"] = time.time()
        if await self._ensure_backend():
            exists = await self._redis.exists(_TASK.format(task_id))
            if not exists:
                return None
            await self._redis.hmset(_TASK.format(task_id), fields)
            return await self.get(task_id)
        async with self._mem_lock:
            r = self._mem_tasks.get(task_id)
            if r is None:
                return None
            for k, v in fields.items():
                if hasattr(r, k):
                    setattr(r, k, v)
            return r

    async def set_progress(
        self, task_id: str, pct: float, stage: str, message: str = ""
    ) -> None:
        await self.update(
            task_id,
            progress=float(pct),
            stage=stage,
            message=message,
            status="processing",
        )
        await self.publish(
            task_id, "progress", {"pct": float(pct), "stage": stage, "message": message}
        )

    async def add_clip(self, task_id: str, clip: Dict[str, Any]) -> None:
        if await self._ensure_backend():
            await self._redis.rpush(_CLIPS.format(task_id), json.dumps(clip))
        else:
            async with self._mem_lock:
                r = self._mem_tasks.get(task_id)
                if r:
                    r.clips.append(clip)
        await self.publish(task_id, "clip_ready", clip)

    async def add_clips(self, task_id: str, clips: List[Dict[str, Any]]) -> None:
        if not clips:
            return

        if await self._ensure_backend():
            clip_strs = [json.dumps(clip) for clip in clips]
            await self._redis.rpush(_CLIPS.format(task_id), *clip_strs)

            # Batch publish events using pipeline to reduce network roundtrips
            async with self._redis.pipeline(transaction=False) as pipe:
                for clip in clips:
                    payload = json.dumps({"event": "clip_ready", "data": clip})
                    pipe.publish(_PROGRESS.format(task_id), payload)
                await pipe.execute()
        else:
            async with self._mem_lock:
                r = self._mem_tasks.get(task_id)
                if r:
                    r.clips.extend(clips)

            # For in-memory, we can't pipeline, but we just call publish sequentially
            for clip in clips:
                await self.publish(task_id, "clip_ready", clip)

    async def publish(self, task_id: str, event: str, data: Any) -> None:
        if await self._ensure_backend():
            payload = json.dumps({"event": event, "data": data})
            await self._redis.publish(_PROGRESS.format(task_id), payload)
        else:
            async with self._mem_lock:
                queues = list(self._mem_subs.get(task_id, []))
            for q in queues:
                try:
                    q.put_nowait((event, data))
                except asyncio.QueueFull:
                    try:
                        # Queue is full: discard oldest event to make room for the latest progress event
                        q.get_nowait()
                        q.put_nowait((event, data))
                    except Exception:
                        pass

    async def recover_from_storage(self) -> int:
        """Scan STORAGE_DIR dan load semua task yang belum ada di state.

        Dipanggil saat lifespan boot supaya task tidak hilang ketika server
        restart. Task yang punya highlights.json dianggap 'completed'; task
        yang hanya punya transcript.json dianggap 'error' (pipeline gagal
        atau belum selesai saat server mati).

        Returns:
            Jumlah task yang berhasil di-recover.
        """
        recovered = 0
        storage = Path(STORAGE_DIR)
        if not storage.exists():
            return 0

        for task_dir in storage.iterdir():
            if not task_dir.is_dir():
                continue
            task_id = task_dir.name
            # Skip kalau task sudah ada di state
            existing = await self.get(task_id)
            if existing is not None:
                continue

            # Baca metadata dari highlights.json jika ada
            highlights_path = task_dir / "highlights.json"
            transcript_path = task_dir / "transcript.json"

            if highlights_path.exists():
                try:

                    def read_json(path=highlights_path):
                        with open(path, encoding="utf-8") as file:
                            return file.read()

                    manifest_str = await asyncio.to_thread(read_json)
                    manifest = json.loads(manifest_str)
                    url = manifest.get("url", "")
                    clips = manifest.get("clips", [])

                    # Verifikasi keberadaan file fisik .mp4 untuk masing-masing klip
                    valid_clips = []
                    for clip in clips:
                        clip_url = clip.get("clip_url")
                        if not clip_url:
                            continue
                        # Ambil nama file dari clip_url, misal "/clips/abc123xyz/short_01.mp4" -> "short_01.mp4"
                        filename = clip_url.split("/")[-1]
                        clip_file_path = task_dir / filename
                        if clip_file_path.exists():
                            valid_clips.append(clip)

                    if not valid_clips:
                        log.warning(
                            "Zombie completed task %s: highlights.json exists but all physical .mp4 files are missing from disk. Skipping recovery.",
                            task_id,
                        )
                        continue

                    # Re-create TaskRecord sebagai completed dengan klip yang valid
                    record = TaskRecord(
                        task_id=task_id,
                        url=url,
                        num_clips=len(valid_clips),
                        aspect_ratio="9:16",
                        language=None,
                        subtitle_style="viral-bold",
                        status="completed",
                        progress=100.0,
                        stage="done",
                        message="Recovered from storage",
                        clips=valid_clips,
                        created_at=highlights_path.stat().st_mtime,
                        updated_at=highlights_path.stat().st_mtime,
                    )
                    if await self._ensure_backend():
                        await self._redis.hmset(
                            _TASK.format(task_id), record.to_redis_hash()
                        )
                        if valid_clips:
                            await self._redis.rpush(
                                _CLIPS.format(task_id),
                                *[json.dumps(clip) for clip in valid_clips],
                            )
                    else:
                        async with self._mem_lock:
                            self._mem_tasks[task_id] = record
                            self._mem_subs[task_id] = []
                    recovered += 1
                    log.info(
                        "Recovered completed task %s with %d valid clips from storage",
                        task_id,
                        len(valid_clips),
                    )
                    continue
                except Exception as e:
                    log.warning(
                        "Failed to recover task %s from highlights.json: %s", task_id, e
                    )

            if transcript_path.exists():
                # Pipeline gagal atau mati di tengah jalan — tandai sebagai error
                # supaya user bisa lihat task-nya di frontend
                try:
                    stat = transcript_path.stat()
                    record = TaskRecord(
                        task_id=task_id,
                        url="",
                        num_clips=5,
                        aspect_ratio="9:16",
                        language=None,
                        subtitle_style="viral-bold",
                        status="error",
                        progress=0.0,
                        stage="error",
                        message="Server restarted — pipeline belum selesai.",
                        error="Server restarted sebelum pipeline selesai. Submit ulang URL untuk memproses ulang.",
                        created_at=stat.st_mtime,
                        updated_at=stat.st_mtime,
                    )
                    if await self._ensure_backend():
                        await self._redis.hmset(
                            _TASK.format(task_id), record.to_redis_hash()
                        )
                    else:
                        async with self._mem_lock:
                            self._mem_tasks[task_id] = record
                            self._mem_subs[task_id] = []
                    recovered += 1
                    log.info(
                        "Recovered orphaned task %s from storage (marked as error)",
                        task_id,
                    )
                except Exception as e:
                    log.warning(
                        "Failed to recover task %s from transcript.json: %s", task_id, e
                    )

        return recovered

    async def subscribe(self, task_id: str) -> AsyncIterator[Tuple[str, Any]]:
        if await self._ensure_backend():
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(_PROGRESS.format(task_id))
            try:
                async for msg in pubsub.listen():
                    if msg["type"] != "message":
                        continue
                    try:
                        parsed = json.loads(msg["data"])
                        yield parsed.get("event", "progress"), parsed.get("data", {})
                        if parsed.get("event") in ("done", "error"):
                            break
                    except (json.JSONDecodeError, KeyError):
                        continue
            finally:
                await pubsub.unsubscribe(_PROGRESS.format(task_id))
                await pubsub.close()
        else:
            q = asyncio.Queue(maxsize=256)
            async with self._mem_lock:
                self._mem_subs.setdefault(task_id, []).append(q)
            try:
                while True:
                    event, data = await q.get()
                    yield event, data
                    if event in ("done", "error"):
                        break
            finally:
                async with self._mem_lock:
                    subs = self._mem_subs.get(task_id)
                    if subs and q in subs:
                        subs.remove(q)

    def is_cancelled(self, task_id: str) -> bool:
        return task_id in self._cancelled

    async def cancel(self, task_id: str) -> None:
        """Mark a task as cancelled and notify SSE subscribers."""
        self._cancelled.add(task_id)
        await self.update(
            task_id,
            status="cancelled",
            progress=100.0,
            stage="cancelled",
            message="Task cancelled by user",
        )
        await self.publish(
            task_id,
            "progress",
            {"pct": 100.0, "stage": "cancelled", "message": "Task cancelled by user"},
        )
        # Terminal event so SSE subscribers break out of their listen loop
        await self.publish(task_id, "done", {"clips": 0})

    async def delete(self, task_id: str) -> bool:
        """Delete a task from state and storage.

        Deletes from Redis/memory state first, then attempts storage cleanup.
        If storage cleanup fails (e.g. locked file on Windows), the task is
        still removed from the system — only leftover files remain on disk.
        """
        from .config import STORAGE_DIR
        import shutil

        # 1. Delete from state first — guarantees clean removal even if storage fails
        if await self._ensure_backend():
            existed = await self._redis.exists(_TASK.format(task_id))
            if existed:
                await self._redis.delete(_TASK.format(task_id), _CLIPS.format(task_id))
        else:
            async with self._mem_lock:
                existed = task_id in self._mem_tasks
                self._mem_tasks.pop(task_id, None)
                self._mem_subs.pop(task_id, None)

        if not existed:
            return False

        # 2. Mark as cancelled so running pipelines can detect
        self._cancelled.add(task_id)

        # 3. Attempt storage cleanup (best-effort)
        task_dir = STORAGE_DIR / task_id
        if task_dir.exists() and task_dir.is_dir():
            try:
                await asyncio.to_thread(shutil.rmtree, task_dir)
                log.info("Deleted storage directory for task %s", task_id)
            except OSError as e:
                log.warning(
                    "Failed to delete storage directory %s: %s — task already removed from state",
                    task_dir,
                    e,
                )

        # 4. Release cancellation marker so the set doesn't grow unbounded
        self._cancelled.discard(task_id)

        return True


store = TaskStore()
