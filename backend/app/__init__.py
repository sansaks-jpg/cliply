"""FastAPI wrapper around the backend engine.

This package turns the headless clip-generation pipeline into a web service:
  * POST /tasks        — kick off a generation job
  * GET  /tasks/{id}   — poll status / fetch the clip manifest
  * GET  /tasks/{id}/progress — SSE stream of progress events
  * GET  /clips/...    — serve rendered mp4s

Engine modules (`app/engine/`) are adapted forks of `shorts_generator/`, kept
as separate files so the original CLI library stays intact and importable.
"""
