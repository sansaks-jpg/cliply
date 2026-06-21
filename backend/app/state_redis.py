"""Redis-backed task store with pub/sub progress.

Same interface as the in-memory TaskStore in state.py — swap by changing
which module is imported in app.state.store.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from redis.asyncio import Redis

from ..config import REDIS_URL

# Redis key prefixes
_TASK = "task:"           # hash → task_id → JSON record
_PROGRESS = "task:progress:"  # channel for SSE
_CLIPS = "task:clips:"    # list → task_id → clip JSON items


@dataclass
class TaskRecord:
    task_id: str
    url: str
    num_clips: int
    aspect_ratio: str
    language: Optional[str]
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
            "language": self.language,
            "status": self.status,
            "progress": self.progress,
            "stage": self.stage,
            "message": self.message,
            "error": self.error,
            "clips": self.clips,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> TaskRecord:
        return cls(
            task_id=d["task_id"],
            url=d["url"],
            num_clips=d.get("num_clips", 5),
            aspect_ratio=d.get("aspect_ratio", "9:16"),
            language=d.get("language"),
            status=d.get("status", "queued"),
            progress=float(d.get("progress", 0)),
            stage=d.get("stage", ""),
            message=d.get("message", ""),
            error=d.get("error"),
            clips=d.get("clips", []),
            created_at=float(d.get("created_at", time.time())),
            updated_at=float(d.get("updated_at", time.time())),
        )


class RedisTaskStore:
    def __init__(self) -> None:
        self._redis: Redis | None = None

    async def _r(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(REDIS_URL, decode_responses=True)
        return self._redis

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def create(
        self,
        url: str,
        num_clips: int,
        aspect_ratio: str,
        language: Optional[str],
    ) -> str:
        task_id = uuid.uuid4().hex[:12]
        record = TaskRecord(
            task_id=task_id,
            url=url,
            num_clips=num_clips,
            aspect_ratio=aspect_ratio,
            language=language,
        )
        r = await self._r()
        await r.hset(_TASK + task_id, mapping=record.to_dict())
        return task_id

    async def get(self, task_id: str) -> Optional[TaskRecord]:
        r = await self._r()
        data = await r.hgetall(_TASK + task_id)
        if not data:
            return None
        # clips are stored separately; load them
        clips = await r.lrange(_CLIPS + task_id, 0, -1)
        if clips:
            data["clips"] = [json.loads(c) for c in clips]
        return TaskRecord.from_dict(data)

    async def list(self) -> List[TaskRecord]:
        r = await self._r()
        # SCAN instead of KEYS (non-blocking)
        keys = []
        async for key in r.scan_iter(match=_TASK + "*"):
            keys.append(key)
        records_data = []
        if keys:
            pipe = r.pipeline()
            for key in keys:
                pipe.hgetall(key)
            hgetall_results = await pipe.execute()
            for data in hgetall_results:
                if not data:
                    continue
                records_data.append(data)
            # Batch LRANGE
            if records_data:
                clips_pipe = r.pipeline()
                for data in records_data:
                    clips_pipe.lrange(_CLIPS + data.get("task_id", ""), 0, -1)
                clips_results = await clips_pipe.execute()
                for data, clips_raw in zip(records_data, clips_results):
                    if clips_raw:
                        data["clips"] = [json.loads(c) for c in clips_raw]
        records = [TaskRecord.from_dict(d) for d in records_data]
        return sorted(records, key=lambda r: r.created_at, reverse=True)

    async def update(self, task_id: str, **fields: Any) -> Optional[TaskRecord]:
        r = await self._r()
        exists = await r.exists(_TASK + task_id)
        if not exists:
            return None
        fields["updated_at"] = time.time()
        await r.hset(_TASK + task_id, mapping=fields)
        # re-read and return
        return await self.get(task_id)

    async def set_progress(self, task_id: str, pct: float, stage: str, message: str = "") -> None:
        await self.update(
            task_id,
            progress=float(pct),
            stage=stage,
            message=message,
            status="processing",
        )
        await self.publish(task_id, "progress", {"pct": float(pct), "stage": stage, "message": message})

    async def add_clip(self, task_id: str, clip: Dict[str, Any]) -> None:
        r = await self._r()
        await r.rpush(_CLIPS + task_id, json.dumps(clip))
        await self.publish(task_id, "clip_ready", clip)

    async def publish(self, task_id: str, event: str, data: Any) -> None:
        r = await self._r()
        payload = json.dumps({"event": event, "data": data})
        await r.publish(_PROGRESS + task_id, payload)

    async def subscribe(self, task_id: str) -> AsyncIterator[Tuple[str, Any]]:
        r = await self._r()
        pubsub = r.pubsub()
        await pubsub.subscribe(_PROGRESS + task_id)
        try:
            async for msg in pubsub.listen():
                if msg["type"] != "message":
                    continue
                try:
                    parsed = json.loads(msg["data"])
                    event = parsed.get("event", "progress")
                    data = parsed.get("data", {})
                    yield event, data
                    if event in ("done", "error"):
                        break
                except (json.JSONDecodeError, KeyError):
                    continue
        finally:
            await pubsub.unsubscribe(_PROGRESS + task_id)
            await pubsub.close()

    async def delete(self, task_id: str) -> bool:
        r = await self._r()
        existed = await r.exists(_TASK + task_id)
        if existed:
            await r.delete(_TASK + task_id, _CLIPS + task_id)
        return bool(existed)


# Module-level singleton — routes and pipeline import `store` from here.
store = RedisTaskStore()
