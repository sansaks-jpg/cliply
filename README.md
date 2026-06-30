# Cliply

Automatic YouTube → viral 9:16 short clips generator. Paste a YouTube URL, and the AI pipeline downloads, transcribes, analyzes virality, tracks faces, crops to vertical, and burns karaoke subtitles — all in one go.

**Version:** 0.2.1

## Features

- **One-click** — paste YouTube link, get vertical clips
- **AI virality analysis** — finds the best moments via local LLM (mimo-v2.5-pro)
- **Smart face tracking** — OpenCV DNN SSD + MediaPipe + YuNet, mouth motion energy scoring
- **Speaker detection** — mouth motion energy + face size scoring with hysteresis
- **Detection sensitivity slider** — adjustable 0-100 sensitivity for speaker detection accuracy
- **Shot classification** — closeup / medium / wide-cut, with dynamic zoom & letterbox
- **Multi-style karaoke subtitles** — 10+ styles (viral-bold, tiktok, neon-glow, word-pop, etc.)
- **Live progress (SSE)** — real-time stage updates in the browser
- **High-Quality Previews & Split-Screen Comparison** — Premium side-by-side and vertical comparisons for both Podcast and Gaming templates, complete with frame-synchronized looping and anti-download overlay shields.
- **Rich Status Indicators** — Live log updates capturing the video download size in MB and the active AI engine/model, combined with dynamic explanation cards for each processing stage.
- **Improved Subtitle Color Controls** — Synchronized color picker updates applying changes to all preview cards instantly without requiring individual activation.
- **Persistent settings** — all preferences saved in localStorage (clips, face detector, subtitle style, etc.)
- **Dual caching** — transcripts cached as `.json` (speaker metadata) + `.srt`
- **Pluggable LLM** — OpenAI / Gemini / Anthropic / local via env
- **LLM resilience** — retry 3x with exponential backoff for transient errors
- **Graceful degradation** — pipeline continues with fallback if LLM fails

## Architecture

```
Browser (Next.js 15)
   │ HTTP + SSE
   ▼
FastAPI backend
   ├── downloader.py     yt-dlp → source.mp4
   ├── transcriber.py    Gemini/Whisper → transcript
   ├── highlights.py     LLM → viral segment candidates
   ├── smart_crop.py     Face detection + shot type
   ├── subtitles.py      ASS karaoke styling engine
   └── render.py         ffmpeg 9:16 crop + subtitle burn
   │
   ├── Redis (queue + state)
   └── Filesystem (storage/{task_id}/)
```

## Tech Stack

| Layer | Stack |
|-------|-------|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Frontend | Next.js 15, React 19, Tailwind v4, shadcn/ui |
| Video | yt-dlp, ffmpeg, OpenCV, PySceneDetect |
| AI | Gemini 2.5 Flash, Groq Whisper, mimo-v2.5-pro |
| State | Redis |
| Fonts | TikTok Sans, Montserrat, Plus Jakarta Sans, Helvetica |

## Prerequisites

- Python 3.10+
- Node.js 20+
- pnpm (`npm i -g pnpm`)
- Redis server on `:6379`
- ffmpeg in PATH
- YouTube video accessible by yt-dlp

## Usage

### Web UI

1. Open `http://localhost:3107`
2. Paste a YouTube URL (video, Shorts, or live stream)
3. Click **Advanced Options** to adjust:
   - **Number of clips** (1–10)
   - **Subtitle style** (10 styles available)
   - **Face detector** (YuNet / SSD / MediaPipe / YOLOv8-Face)
   - **Language** (auto-detect or force specific)
4. Click **Generate** → watch live progress via SSE
5. Preview & download each clip once done

### API

```bash
curl -X POST http://localhost:8003/tasks \
  -H "Content-Type: application/json" \
  -d '{"url": "https://youtube.com/watch?v=...", "num_clips": 5, "subtitle_style": "viral-bold"}'
```

Stream progress:
```bash
curl -N http://localhost:8003/tasks/{task_id}/events
```

## Models

### Face Detection (2 options, default: YOLOv8-Face)

| Model | File | Notes |
|-------|------|-------|
| **YOLOv8-Face** | `yolov8n-face.onnx` | ONNX, good accuracy with NMS. Default. |
| **YuNet** | `face_detection_yunet_2023mar.onnx` | Fastest & most accurate for side profiles. ONNX, lightweight. |

All model files are bundled in `backend/models/`.

### Transcription (cascading fallback)

| Source | Model | Speaker Diarization |
|--------|-------|-------------------|
| YouTube API | `youtube-transcript-api` | No |
| Gemini (default) | `gemini-2.5-flash` | **Yes** — speaker labels |
| Groq Whisper | `whisper-large-v3` | No |

### LLM for Highlight Ranking

| Provider | Default Model | Use Case |
|----------|--------------|----------|
| `openai` | `gpt-4o-mini` / custom (e.g. `mimo/mimo-v2.5-pro`) | Virality scoring |
| `gemini` | `gemini-2.5-flash` | Alternative |
| `anthropic` | `claude-haiku-4` | Alternative |

Switch via `LLM_PROVIDER` in `.env`.

## Getting Started

### 1. Backend

```powershell
cd backend
uv venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-local.txt
```

Copy `.env.example` to `.env` and configure:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=http://127.0.0.1:20128/v1
OPENAI_MODEL=mimo/mimo-v2.5-pro
GEMINI_API_KEY=...
```

Start the server:

```powershell
python -m uvicorn app.main:app --reload --port 8003
```

### 2. Frontend

```powershell
cd frontend
pnpm install
pnpm run dev
```

Opens at `http://localhost:3107`.

## Configuration

All settings in `backend/.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `openai` | `openai`, `gemini`, or `anthropic` |
| `OPENAI_BASE_URL` | — | Custom endpoint (for local models) |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model name |
| `NUM_CLIPS_DEFAULT` | `5` | Default number of clips |
| `SUBTITLE_STYLE_DEFAULT` | `viral-bold` | Default subtitle style |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `STORAGE_DIR` | `./storage` | Task output directory |
| `CORS_ORIGINS` | `http://localhost:3107` | Allowed origins |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/tasks` | Submit a YouTube URL for processing |
| `GET` | `/tasks` | List all tasks |
| `GET` | `/tasks/{id}` | Get task status |
| `GET` | `/tasks/{id}/events` | SSE stream for live progress |
| `DELETE` | `/tasks/{id}` | Delete a task + storage |
| `GET` | `/media/{task_id}/{filename}` | Serve mp4 clips & thumbnails |
| `GET` | `/health` | Liveness check |

## Subtitle Styles

| Style | Animation | Description |
|-------|-----------|-------------|
| `viral-bold` | karaoke | Bold uppercase, yellow highlight, thick outline |
| `tiktok` | karaoke | TikTok-style, Inter Black, green highlight |
| `word-pop` | wordpop | Single word pop with scale |
| `highlight-box` | box | Per-word box highlight |
| `neon-gradient` | karaoke | Gradient neon, glow blur |
| `neon-glow` | sweep | Karaoke sweep with flash glow |
| `classic-popup` | popup | Traditional pop-up style |
| `clean-minimal` | fadein | Minimal fade-in |
| `minimalist` | fadein | Ultra-minimal, small text |

## Project Structure

```
cliply/
├── backend/
│   ├── app/
│   │   ├── main.py           FastAPI entry
│   │   ├── config.py         Env config
│   │   ├── state.py          Redis-backed task store
│   │   ├── queue.py          Background scheduler
│   │   ├── routes/
│   │   │   ├── tasks.py      Task CRUD + SSE
│   │   │   └── media.py      File serving
│   │   └── engine/
│   │       ├── pipeline.py   7-stage coordinator
│   │       ├── downloader.py
│   │       ├── transcriber.py
│   │       ├── highlights.py
│   │       ├── llm.py
│   │       ├── smart_crop.py
│   │       ├── subtitles.py
│   │       └── render.py
│   ├── requirements.txt
│   ├── requirements-local.txt
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── app/              pages (/, /tasks/[id])
│   │   ├── components/       UI components
│   │   └── lib/              API client, SSE hook
│   ├── package.json
│   └── tsconfig.json
├── plan.md
├── AGENTS.md
└── README.md
```

## Pipeline Stages

| Stage | % | Description |
|-------|---|-------------|
| DOWNLOAD | 0–15% | yt-dlp download with mp4 cache |
| TRANSCRIBE | 15–35% | Gemini diarization + Groq Whisper fallback |
| RANK HIGHLIGHTS | 35–50% | LLM virality scoring |
| SMART CROP PLAN | 50–65% | Face/pose detection, shot classification |
| RENDER VERTICAL | 65–90% | 9:16 crop + ASS subtitle burn-in |
| SUBTITLE STYLE | (65–90%) | Karaoke word-highlight styling |
| FINALIZE | 90–100% | Manifest generation |

## License

MIT
