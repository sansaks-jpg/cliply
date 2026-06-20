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
from typing import Any, AsyncIterator, Dict, List, Optional

from .config import REDIS_URL

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
    subtitle_style: Optional[str] = None
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
            "subtitle_style": self.subtitle_style or "",
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

    async def _ensure_backend(self):
        if self._redis is None:
            try:
                from redis.asyncio import Redis
                r = Redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
                await r.ping()
                self._redis = r
                self._use_redis = True
                log.info("TaskStore: Redis connected")
            except Exception as e:
                log.warning("TaskStore: Redis unavailable (%s), using in-memory", e)
                self._use_redis = False
        return self._use_redis

    async def create(self, url: str, num_clips: int, aspect_ratio: str, language: Optional[str], subtitle_style: Optional[str] = None) -> str:
        task_id = uuid.uuid4().hex[:12]
        record = TaskRecord(task_id=task_id, url=url, num_clips=num_clips, aspect_ratio=aspect_ratio, language=language, subtitle_style=subtitle_style)
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
        for k in ("language", "error", "subtitle_style"):
            if k in data and not data.get(k):
                data[k] = None
        if "subtitle_style" not in data:
            data["subtitle_style"] = None
        if "clips" not in data:
            data["clips"] = []
        return TaskRecord(**data)

    async def list(self) -> List[TaskRecord]:
        if await self._ensure_backend():
            keys = await self._redis.keys(_TASK.format("*"))
            records = []
            for key in keys:
                data = await self._redis.hgetall(key)
                if data:
                    tid = data.get("task_id", "")
                    clips = await self._redis.lrange(_CLIPS.format(tid), 0, -1)
                    if clips:
                        data["clips"] = [json.loads(c) for c in clips]
                    records.append(self._record_from_dict(data))
            return sorted(records, key=lambda r: r.created_at, reverse=True)
        async with self._mem_lock:
            return sorted(self._mem_tasks.values(), key=lambda r: r.created_at, reverse=True)

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

    async def set_progress(self, task_id: str, pct: float, stage: str, message: str = "") -> None:
        await self.update(task_id, progress=float(pct), stage=stage, message=message, status="processing")
        await self.publish(task_id, "progress", {"pct": float(pct), "stage": stage, "message": message})

    async def add_clip(self, task_id: str, clip: Dict[str, Any]) -> None:
        if await self._ensure_backend():
            await self._redis.rpush(_CLIPS.format(task_id), json.dumps(clip))
        else:
            async with self._mem_lock:
                r = self._mem_tasks.get(task_id)
                if r:
                    r.clips.append(clip)
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
                    pass

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

    async def delete(self, task_id: str) -> bool:
        from .config import STORAGE_DIR
        import shutil
        import os
        
        task_dir = STORAGE_DIR / task_id
        if task_dir.exists() and task_dir.is_dir():
            try:
                await asyncio.to_thread(shutil.rmtree, task_dir)
                log.info("Deleted storage directory for task %s", task_id)
            except Exception as e:
                log.error("Failed to delete storage directory %s: %s", task_dir, e)

        if await self._ensure_backend():
            existed = await self._redis.exists(_TASK.format(task_id))
            if existed:
                await self._redis.delete(_TASK.format(task_id), _CLIPS.format(task_id))
            return bool(existed)
        async with self._mem_lock:
            existed = task_id in self._mem_tasks
            self._mem_tasks.pop(task_id, None)
            self._mem_subs.pop(task_id, None)
        return existed


store = TaskStore()
