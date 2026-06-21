# plan.md — AI Clip Generator (cliply workspace)

> Status: **active development / updated layout**
> Last updated: 2026-06-20

## 1. Goals & Constraints

**Goal:** A web application where users paste a YouTube URL → automatic video download → AI extracts viral moments → crops to **9:16 vertical** using face tracking + shot type classification (preventing subject clipping) → burns styled karaoke subtitles → user previews and downloads clips.

**Unified Repository Structure:**
- **Backend = `backend/`** (FastAPI backend + video processing engine originally from `AI-Youtube-Shorts-Generator` with subtitle & smart-crop features ported from `supoclip` natively).
- **Frontend = `frontend/`** (Next.js 15 App Router from `supoclip` stripped clean: no auth, no billing, no Stripe, no Prisma, no Better Auth, and no Docker).

**Out of Scope (MVP):**
- Authentication / user accounts / billing tier limits.
- Pexels B-roll overlays, caption template marketplaces, custom font upload UI.
- Multi-user tenancy (tasks are persistent on filesystem/Redis).
- Manual clip editing (trim/split/merge).

### Technical Decisions
| # | Decision | Chosen Option |
|---|---|---|
| 1 | Aspect ratio | **9:16 vertical** (TikTok/Reels/Shorts) |
| 2 | Auth/billing | **Minimalist — no accounts/billing**, single-purpose UI |
| 3 | LLM provider | **Pluggable via env** (`LLM_PROVIDER=openai\|gemini\|anthropic`) |

---

## 2. Final Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Browser                                                          │
│  ┌──────────────────────────────────────────────────┐            │
│  │ Next.js app (frontend/, stripped down)            │            │
│  │  • Halaman "/" : paste URL + Generate button     │            │
│  │  • Halaman "/tasks/[id]" : live progress (SSE)   │            │
│  │  • Video player 9:16 + download button           │            │
│  └──────────────────────────────────────────────────┘            │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP (fetch) + EventSource (SSE)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ FastAPI backend  (port :8000)                                   │
│  app/main.py                                                    │
│  app/routes/tasks.py   POST /tasks, GET /tasks/{id}, SSE        │
│  app/routes/media.py   serve mp4, thumbnail                     │
│  app/state.py          task store (Redis-backed)                │
│  app/queue.py          BackgroundTasks scheduler                │
│                                                                 │
│  Engine:                                                        │
│   app/engine/                                                   │
│    pipeline.py    ← pipeline coordinator                        │
│    downloader.py  ← video downloader (yt-dlp + cache)           │
│    transcriber.py ← Gemini 2.5 Flash + speaker diarization      │
│    highlights.py  ← virality analysis (speaker label injected)  │
│    llm.py         ← LLM call dispatch                           │
│    smart_crop.py  ← OpenCV SSD DNN + mouth motion + scene cut   │
│    subtitles.py   ← karaoke subtitle ASS formatting             │
│    render.py      ← final vertical 9:16 ffmpeg renderer         │
└──────────────────────────┬──────────────────────────────────────┘
                           │
            ┌──────────────┴───────────────┐
            ▼                              ▼
    Redis (queue+state, :6379)     Filesystem (backend/storage/{task_id}/)
                                    - source.mp4
                                    - transcript.srt & transcript.json
                                    - highlights.json
                                    - clips/short_01.mp4, …
```

---

## 3. Processing Steps (Pipeline)

1. **DOWNLOAD [0-15%]** — `yt-dlp` → `backend/storage/{id}/source.mp4`. Skips downloading if the video has already been cached.
2. **TRANSCRIBE [15-35%]** — Gemini 2.5 Flash with speaker diarization → `backend/storage/{id}/transcript.srt` & `transcript.json` (retains speaker names).
3. **RANK HIGHLIGHTS [35-50%]** — Local model `mimo-v2.5-pro` (`http://localhost:20128/v1` with OpenAI compatible schema) analyzes the transcript. The text has `[Speaker X]:` prepended to preserve dialog context.
4. **SMART CROP PLAN [50-65%]** — OpenCV DNN SSD Caffe + Mouth Motion Energy analyzer tracks active speaker movements at **2 FPS**.
5. **RENDER VERTICAL [65-90%]** — Vertical 9:16 crop using ffmpeg with EMA smoothing (for closeup & medium shots) or Letterbox background blur (for wide/group shots) and burns karaoke ASS subtitles.
6. **SUBTITLE STYLE [within step 5]** — Burns styled "viral-bold" subtitles (TikTok Sans / Inter Black, colored yellow/red for active spoken words) centered in the bottom 75% region of the frame.
7. **FINALIZE [90-100%]** — Generates final manifest JSON and exposes download paths for the generated clips.

---

## 4. Backend Folder Structure (`backend/`)

```
backend/
├── main.py                    ← Legacy CLI entry point (kept for local debugging)
├── requirements.txt           ← Core backend dependencies
├── requirements-local.txt     ← Dependencies for local execution (faster-whisper, opencv)
├── app/                       ← FastAPI Wrapper
│   ├── main.py                ← FastAPI app entry point
│   ├── config.py              ← Environment configuration
│   ├── state.py               ← Redis state manager
│   ├── queue.py               ← Background task scheduler
│   └── engine/                # Core AI Engine
│       ├── pipeline.py        # Pipeline workflow coordinator
│       ├── downloader.py      # Video download & cache manager
│       ├── transcriber.py     # Gemini & Whisper transcribers (outputs .srt & .json)
│       ├── highlights.py      # Virality analysis with speaker diarization support
│       ├── llm.py             # LLM call routing
│       ├── smart_crop.py      # OpenCV DNN face tracking + mouth analysis
│       ├── subtitles.py       # Karaoke caption generator
│       └── render.py          # Final video renderer & ffmpeg builder
```

---

## 5. Frontend Folder Structure (`frontend/`)

Next.js 15 App Router is stripped of heavy client integrations (Better Auth, Prisma, Stripe, Resend, Docker, etc.).
* **Landing Page (`src/app/page.tsx`)**: Input form to paste YouTube links and lists recently generated tasks using `localStorage`.
* **Task View Page (`src/app/tasks/[id]/page.tsx`)**: Listens to Server-Sent Events (SSE) for live stage progress, displaying the vertical player and download cards as clips complete.

---

## 6. Phased Implementation Status

- [x] **Phase 0 — Bootstrap**: Consolidated the layout into unified `backend/` and `frontend/` folders. Stripped auth/billing/Docker setups from the frontend.
- [x] **Phase 1 — Headless Pipeline & Caching**: Ported core engines, fixed start/end timestamp parser conflicts, and enabled dual-caching (JSON & SRT) for speaker diarization.
- [x] **Phase 2 — Speaker-Aware Highlights**: Prefixed `[Speaker X]:` to segment lines in transcriber outputs and integrated the local `mimo-v2.5-pro` highlights model.
- [x] **Phase 3 — Smart Crop & Render**: Configured SSD ResNet-10 face tracking, mouth motion scoring, and EMA smoothing.
- [ ] **Phase 4 — Frontend MVP**: Next.js user interface with form validation and redirect logic.
- [ ] **Phase 5 — Async & SSE**: Real-time progress updates sent through Redis channels.
