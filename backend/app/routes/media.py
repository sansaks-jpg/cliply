"""Media routes: serve rendered clip mp4s and thumbnails.

Files live under `{STORAGE_DIR}/{task_id}/clips/<filename>` and
`{STORAGE_DIR}/{task_id}/thumbs/<filename>`. We refuse paths with traversal
segments so a crafted URL can't escape the storage root.
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import config

router = APIRouter(tags=["media"])


def _safe_resolve(task_id: str, subdir: str, filename: str) -> Path:
    """Resolve a media path and reject any traversal attempt."""
    base_storage = Path(config.STORAGE_DIR).resolve()
    root = (base_storage / task_id / subdir).resolve()

    # Ensure the resolved root directory does not escape the base storage directory
    # through a crafted task_id (e.g. "../../../etc").
    try:
        root.relative_to(base_storage)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found.")

    target = (root / filename).resolve()
    # `Path.relative_to` raises ValueError if target is outside root.
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found.")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not found.")
    return target


@router.get("/clips/{task_id}/{filename}")
async def get_clip(task_id: str, filename: str):
    path = _safe_resolve(task_id, "clips", filename)
    return FileResponse(path, media_type="video/mp4")


@router.get("/thumbs/{task_id}/{filename}")
async def get_thumb(task_id: str, filename: str):
    path = _safe_resolve(task_id, "thumbs", filename)
    return FileResponse(path, media_type="image/jpeg")
