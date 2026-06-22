import pytest
from fastapi.testclient import TestClient
from pathlib import Path

# Need to set env variables or mock config before importing app
import os
os.environ["STORAGE_DIR"] = "./test_storage"
os.environ["LLM_PROVIDER"] = "openai"
os.environ["OPENAI_API_KEY"] = "fake"

from app.main import app
from app import config

client = TestClient(app)

def test_media_path_traversal_task_id(tmp_path, monkeypatch):
    # Mock storage dir to a temporary path
    monkeypatch.setattr(config, "STORAGE_DIR", str(tmp_path))

    # Create some dummy file outside the storage dir
    outside_dir = tmp_path.parent / "outside"
    outside_dir.mkdir(exist_ok=True)
    secret_file = outside_dir / "secret.txt"
    secret_file.write_text("secret content")

    # Ensure it's there
    assert secret_file.exists()

    # Try to access it via task_id traversal
    response = client.get("/clips/..%2F..%2Foutside/secret.txt")

    # With the fix, this should return a 404 (Not Found)
    # Note: If it doesn't even hit our route because of path normalization, it returns "Not Found" (capital F).
    # If it hits our route and is rejected, it returns "Not found." (lowercase f).
    # Either way, as long as it's a 404, the traversal is prevented.
    assert response.status_code == 404

def test_media_path_traversal_filename(tmp_path, monkeypatch):
    # Mock storage dir to a temporary path
    monkeypatch.setattr(config, "STORAGE_DIR", str(tmp_path))

    # Create a dummy task
    task_id = "test_task"
    clips_dir = tmp_path / task_id / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    # Create some dummy file outside the clips dir but inside storage
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("secret content")

    # Try to access it via filename traversal
    response = client.get(f"/clips/{task_id}/..%2F..%2Fsecret.txt")

    # This should be caught by target.relative_to(root)
    assert response.status_code == 404

def test_valid_media_access(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STORAGE_DIR", str(tmp_path))

    task_id = "test_task"
    clips_dir = tmp_path / task_id / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    test_file = clips_dir / "test.mp4"
    test_file.write_bytes(b"test content")

    response = client.get(f"/clips/{task_id}/test.mp4")
    assert response.status_code == 200
    assert response.content == b"test content"
