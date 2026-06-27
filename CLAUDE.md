# CLAUDE.md — Cliply Project Guide

## Overview

Cliply adalah aplikasi desktop (Tauri) + web yang mengubah video YouTube panjang menjadi shorts vertikal 9:16 secara otomatis. Pipeline: download video → transkripsi (Gemini/Groq/YouTube Transcript) → analisis highlight (LLM) → render dengan smart-crop face tracking → subtitle karaoke ASS.

## Architecture

Three-layer monorepo:

```
clip-ai/
├── backend/          # Python FastAPI server (port 8003)
├── frontend/         # Next.js 15 (App Router, static export) + Tauri v2
│   ├── src/          # React source
│   └── src-tauri/    # Rust Tauri shell (spawns & manages backend process)
└── .github/workflows/build.yml  # CI: PyInstaller → Tauri MSI
```

**Runtime flow (desktop):** Tauri Rust (`lib.rs`) spawns `cliply_server.exe` or `python -m uvicorn app.main:app`, polls `/health` + `/debug/build` for PID-verified readiness, then Next.js frontend talks to `http://127.0.0.1:8003`.

## Pipeline Stages (7 Tahap)

Saat user submit YouTube URL ke `/tasks`, backend menjalankan pipeline async 7 stage:

| Stage | Progress | File | Deskripsi |
|-------|----------|------|-----------|
| 1. DOWNLOAD | 0–15% | `downloader.py` | Download video via yt-dlp |
| 2. TRANSCRIBE | 15–35% | `transcriber.py` | Gemini 2.5 Flash (speaker diarization) + Groq Whisper. Dual cache: `.srt` (standar) + `.json` (speaker metadata) |
| 3. RANK HIGHLIGHTS | 35–50% | `highlights.py`, `llm.py` | Prepend label `[Speaker X]:` → kirim ke LLM untuk deteksi momen viral. Analisis `VIRALITY_CRITERIA`, buang overlap >50% |
| 4. SMART CROP PLAN | 50–65% | `smart_crop.py` | Analisis frame 2 FPS via OpenCV DNN Face Detector (SSD ResNet-10). Mouth Motion Energy, scene cut detection (BGR histogram), shot type classifier (`closeup`/`medium`/`wide_cut`) |
| 5. RENDER VERTICAL | 65–90% | `render.py`, `subtitles.py` | Crop 9:16 dengan EMA smoothing. Letterbox effect untuk `wide_cut`. Burn subtitle karaoke ASS |
| 6. SUBTITLE STYLE | (dalam stage 5) | `subtitles.py` | Caption di 75% bawah frame, max 2 baris, font TikTok Sans / Inter Black |
| 7. FINALIZE | 90–100% | `pipeline.py` | Tulis `highlights.json` manifest (metadata + download URLs per klip mp4) |

## Tech Stack

| Layer | Stack |
|-------|-------|
| Backend | Python 3.10, FastAPI, uvicorn, Redis (optional, in-memory fallback), faster-whisper, yt-dlp, ffmpeg, OpenCV (face detection) |
| Frontend | Next.js 15 (App Router, `output: "export"`), React 19, Tailwind CSS v4, Radix UI, shadcn/ui, pnpm |
| Desktop | Tauri v2 (Rust), tauri-plugin-updater, rfd (file dialog) |
| Testing | Vitest + @testing-library/react + MSW (frontend); no formal backend tests |
| CI/CD | GitHub Actions → PyInstaller bundle → Tauri build → MSI artifact |

## Directory Structure

### Backend (`backend/`)

```
backend/
├── app/
│   ├── main.py           # FastAPI app, lifespan, CORS, middleware, /health, /encoders, /debug/*, /models
│   ├── config.py          # All env vars (dotenv), encoder detection, RenderConstants dataclass
│   ├── state.py           # TaskRecord dataclass, Redis/in-memory store singleton, SSE pub/sub
│   ├── queue.py           # Task queue (enqueue_task)
│   ├── routes/
│   │   ├── tasks.py       # POST/GET/DELETE /tasks, SSE /tasks/{id}/stream
│   │   └── media.py       # Static file serving for clips
│   ├── engine/
│   │   ├── pipeline.py    # run_pipeline() — orchestrates full flow
│   │   ├── downloader.py  # yt-dlp video download
│   │   ├── transcriber.py # Gemini → Groq Whisper → youtube-transcript-api fallback chain
│   │   ├── highlights.py  # LLM-based viral highlight detection
│   │   ├── llm.py         # Pluggable LLM client (OpenAI/Anthropic/Gemini)
│   │   ├── smart_crop.py  # Face/pose detector & shot type classifier (closeup/medium/wide)
│   │   ├── subtitles.py   # ASS subtitle generation with karaoke animations
│   │   ├── render.py      # ffmpeg rendering with smart-crop face tracking
│   │   └── utils.py       # Helpers (video ID extraction, env sanitization)
│   └── services/
│       └── encoder_detection.py  # HW encoder detection (NVIDIA/Intel/AMD)
├── shorts_generator/       # Legacy CLI engine library (SamurAIGPT)
├── main.py               # CLI entry point (argparse, for direct use)
├── cliply_server.py       # PyInstaller entry point (--storage-dir, --port)
├── cliply.spec            # PyInstaller spec file
├── requirements.txt       # Core deps
├── requirements-local.txt # + faster-whisper, opencv (local mode)
├── requirements-bundle.txt # PyInstaller bundle deps (cloud-only transcription)
├── .env.example           # All env vars documented
├── fonts/                 # Subtitle font files
└── storage/               # Runtime task data (gitignored)
```

### Frontend (`frontend/`)

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx       # Root layout (ThemeProvider, fonts, Toaster)
│   │   ├── page.tsx         # Home page — URL input, config, recent tasks
│   │   ├── tasks/page.tsx   # Task detail — progress SSE, clip gallery
│   │   ├── settings/page.tsx # Tauri settings (API keys, LLM provider)
│   │   └── globals.css      # Tailwind + custom CSS variables
│   ├── components/
│   │   ├── ui/              # shadcn/ui primitives (button, card, input, select, etc.)
│   │   ├── theme-provider.tsx
│   │   ├── theme-toggle.tsx
│   │   ├── setup-wizard.tsx # First-run Tauri wizard
│   │   ├── vertical-player.tsx
│   │   └── gpu-optimizer.tsx
│   ├── lib/
│   │   ├── api.ts           # Backend HTTP client (createTask, getTask, deleteTask, SSE)
│   │   ├── tauri.ts         # Tauri IPC wrappers (settings, storage dir, restart backend)
│   │   └── utils.ts         # cn() helper (clsx + tailwind-merge)
│   └── test/
│       └── setup.ts         # Vitest + MSW server setup
├── src-tauri/
│   ├── src/
│   │   ├── lib.rs           # Tauri commands, backend process management, settings I/O
│   │   └── main.rs          # Tauri entry point
│   ├── Cargo.toml           # Rust deps (tauri 2.11, ureq, rfd, chrono)
│   ├── tauri.conf.json      # Tauri config (CSP, updater, bundle resources)
│   └── icons/
├── package.json             # pnpm, scripts: dev/build/tauri:dev/tauri:build/lint/test
├── next.config.ts           # output: "export", trailingSlash, unoptimized images
├── tsconfig.json            # paths: @/* → ./src/*
├── vitest.config.ts         # jsdom, globals, setupFiles
├── postcss.config.mjs
└── eslint.config.mjs
```

## Running Locally

### Backend (development)
```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements-local.txt
cp .env.example .env  # edit with your API keys
uvicorn app.main:app --reload --port 8003
```

### Frontend (development)
```bash
cd frontend
pnpm install
pnpm dev              # Next.js dev server on :3107
```

### Tauri Desktop (development)
```bash
cd frontend
pnpm tauri:dev        # Starts Next.js + Tauri window + spawns backend
```

### Build Desktop (release)
```bash
# Backend → PyInstaller exe
cd backend && pyinstaller cliply.spec --noconfirm

# Frontend + Tauri → MSI
cd frontend && pnpm tauri build
```

## Key Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `openai` | `openai`, `anthropic`, or `gemini` |
| `OPENAI_API_KEY` | — | Required if LLM_PROVIDER=openai |
| `OPENAI_BASE_URL` | `http://localhost:8003/v1` | OpenAI-compatible endpoint |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model name |
| `ANTHROPIC_API_KEY` | — | Required if LLM_PROVIDER=anthropic |
| `GEMINI_API_KEY` | — | Required for Gemini transcription + LLM |
| `GROQ_API_KEY` | — | Required for Groq Whisper transcription |
| `REDIS_URL` | `redis://localhost:6379` | Optional; falls back to in-memory |
| `STORAGE_DIR` | `./storage` | Task output directory |
| `FONTS_DIR` | `./fonts` | Subtitle font files |
| `FFMPEG_ENCODER` | `auto` | `auto`, `nvidia`, `intel`, `amd`, `cpu` |
| `BACKEND_PORT` | `8003` | FastAPI port |

## Key Patterns & Conventions

### Backend
- **Config:** All settings via `config.py` using `dotenv` with `override=False` (env vars take precedence over `.env`).
- **State store:** `state.py` singleton `store` — Redis-backed with automatic in-memory fallback. TaskRecord is a dataclass.
- **Pipeline:** `engine/pipeline.py` `run_pipeline()` is the async orchestrator. Blocking I/O wrapped in `asyncio.to_thread()`. Progress emitted via `store.set_progress()` → SSE.
- **Transcription fallback chain:** youtube-transcript-api → Gemini 2.5 Flash → Groq Whisper-large-v3.
- **LLM pluggable:** `engine/llm.py` returns a callable based on `LLM_PROVIDER`.
- **Encoder auto-detection:** `services/encoder_detection.py` probes ffmpeg for NVENC/QSV/AMF.
- **Security:** SSRF protection on `/models` proxy (localhost-only). Security headers middleware. CORS locked to Tauri origins.

### Frontend
- **Static export:** `next.config.ts` has `output: "export"` — no SSR, pure SPA. Served by Tauri's WebView.
- **Path alias:** `@/*` maps to `./src/*`.
- **API client:** `lib/api.ts` talks to `NEXT_PUBLIC_API_URL` (default `http://127.0.0.1:8003`). `waitForBackend()` polls `/health` on boot.
- **Tauri IPC:** `lib/tauri.ts` wraps `@tauri-apps/api/core` invoke calls. All guarded by `isTauri()` check.
- **UI components:** shadcn/ui under `components/ui/`. Use existing primitives, don't add new UI libs.
- **State:** React useState/useEffect, no external state management library. localStorage for recent tasks.
- **Styling:** Tailwind CSS v4 + CSS custom properties (`--accent-violet`, `--accent-indigo`). Dark mode default via next-themes.
- **SSE:** Task progress streamed via `EventSource` from `/tasks/{id}/stream`.

### Tauri (Rust)
- **Backend lifecycle:** `lib.rs` manages the child process — spawn, PID-verified health check, crash monitoring thread, log rotation, kill on app exit.
- **Settings:** JSON file at `app_config_dir/settings.json`. Fields: `storage_dir`, `first_run`, API keys, `llm_provider`.
- **Commands:** `get_settings`, `set_storage_dir`, `save_app_settings`, `pick_storage_dir`, `open_storage_dir`, `restart_backend`, `relaunch_app`.
- **Bundle:** PyInstaller exe bundled as Tauri resource (`../../backend/dist/cliply_server.exe → backend/cliply_server.exe`).

## Testing

### Frontend
```bash
cd frontend
pnpm test            # Vitest single run
pnpm test:watch      # Vitest watch mode
```
- Framework: Vitest + jsdom + @testing-library/react + MSW
- Setup: `src/test/setup.ts` creates MSW server, auto-cleanup after each test
- Test files: `src/**/*.test.ts` or `src/**/*.test.tsx`

### Backend
No formal test suite. Ad-hoc test scripts exist (`test_*.py`) but are not part of CI.

## CI/CD

Single workflow: `.github/workflows/build.yml`
- Trigger: push tags `v*` or manual dispatch
- Steps: checkout → pnpm install → Next.js build → Python setup → PyInstaller → smoke test (spawn exe, verify /health + /encoders) → Rust setup → Tauri build → upload MSI → create GitHub Release
- Platform: `windows-latest` only

## Developer Rules

1. **Maintain Workspace Integrity:** Jangan buat direktori baru di luar `backend/` dan `frontend/`. Semua UI di `frontend/`, semua processing logic & API di `backend/`.
2. **Async Code:** Semua operasi blocking berat (yt-dlp, transkripsi, render) harus dijalankan dalam thread pool (`asyncio.to_thread()` / `run_in_threadpool`) agar tidak memblokir event loop FastAPI.
3. **Double Caching:** Saat modifikasi engine transkripsi/highlights, pastikan fallback pembacaan cache `.json` (speaker metadata) dan `.srt` tetap berfungsi agar tidak memanggil API eksternal yang mahal.
4. **No Secrets:** Jangan commit API key asli ke repo. Selalu pakai `.env.example` sebagai template.
5. **Windows Subprocess Suppression:** Saat menjalankan subprocess (`ffmpeg`, `ffprobe`, `taskkill`) di Windows, selalu pass `creationflags=subprocess.CREATE_NO_WINDOW` (Python) atau `.creation_flags(CREATE_NO_WINDOW)` (Rust/Tauri) untuk mencegah popup cmd.
6. **CORS Bypass untuk Model Query:** Frontend harus query available models melalui backend proxy `/models`, bukan langsung ke endpoint pihak ketiga (browser CORS akan block).
7. **Static Route Adaptation:** Next.js pakai static export. Jangan buat dynamic route `/tasks/[id]` — pakai `/tasks/page.tsx` + `useSearchParams` untuk ambil `?id=...`.
8. **Commit Rules:**
   - Jangan auto-commit/push. Cek dulu apakah ada perubahan besar, atau tunggu instruksi eksplisit dari user.
   - Pakai prefix convention: `feat:`, `fix:`, `refactor:`, `chore:`, `ci:`, `docs:`.

## Handling Bot PRs (Jules)

Saat menerima PR dari bot contributor (e.g., `google-labs-jules[bot]`):

1. **Jangan merge langsung di GitHub** — bot tidak tercatat sebagai contributor di graf repo.
2. **Pull & test lokal** — checkout branch PR, pastikan tidak ada error TypeScript/syntax/runtime.
3. **Manual clean squash-merge:**
   ```powershell
   git checkout main
   # Apply changes manually or squash-merge
   git commit --author="Sandi Ardiansyah <sandisansan1407@gmail.com>" -m "merge: Description of changes (PR #X)"
   ```
4. **Push & close PR:** `git push origin main`, lalu close PR di GitHub UI (jangan merge) + komentar bahwa changes sudah diintegrasikan manual.

## Common Gotchas

1. **Backend port 8003** is hardcoded in Tauri `lib.rs`, `tauri.conf.json` CSP, and `config.py` CORS. Don't change one without the others.
2. **PyInstaller bundle** uses `requirements-bundle.txt` (no faster-whisper/torch/opencv) — transcription is cloud-only in desktop builds.
3. **Tauri env injection:** Only non-empty settings are passed as env vars to backend process. Empty values would override `.env` due to `load_dotenv(override=False)`.
4. **PID verification:** Tauri polls `/debug/build` to confirm the responding backend is the one it spawned (prevents stale process acceptance).
5. **Static export:** Next.js `output: "export"` means no server-side features (API routes, ISR, middleware). All data fetching is client-side.
6. **pnpm:** Package manager is pnpm (v10). Don't use npm or yarn.
7. **Version:** Currently `0.1.3`. Version appears in: `frontend/package.json`, `frontend/src-tauri/Cargo.toml`, `frontend/src-tauri/tauri.conf.json`, `backend/app/main.py`.
