# AGENTS.md — Workspace Guide for `cliply`

This workspace is a **unified monorepo** for the automated short video creator (AI Video Clipper). The project integrates a lightweight Next.js 15 web interface (`frontend/`) with an AI-powered video processing engine (`backend/`).

> **Primary Working Directory:** `C:\Users\WORKPLUS\Documents\WEB\clip-ai\`

---

## 1. Directory Structure

```
cliply/
├── backend/                  # Python 3.10+ FastAPI Backend & AI Clipping Engine
│   ├── app/                  # Web API & Task Queue
│   │   ├── main.py           # FastAPI Entry Point (CORS, lifespan, routers)
│   │   ├── config.py         # Env config (LLM_PROVIDER, BASE_URL, etc.)
│   │   ├── state.py          # Redis-backed Task Store (status, progress, manifest)
│   │   ├── queue.py          # Background tasks scheduler (FastAPI BackgroundTasks)
│   │   └── engine/           # Integrated video processing pipeline
│   │       ├── pipeline.py    # Pipeline coordinator (7 stages)
│   │       ├── downloader.py  # Video downloader via yt-dlp + mp4 cache
│   │       ├── transcriber.py # Gemini transcription (speaker diarization) + Groq Whisper (.srt & .json cache)
│   │       ├── highlights.py  # Virality analysis & segmenter with speaker labels
│   │       ├── llm.py         # LLM provider dispatch (OpenAI/Gemini/Anthropic/mimo-local)
│   │       ├── smart_crop.py  # Face/pose detector & shot type classifier (closeup/medium/wide)
│   │       ├── subtitles.py   # Karaoke subtitles generator with ASS styling
│   │       └── render.py      # Final ffmpeg filter complex renderer (2-pass SSD DNN crop + subtitle)
│   ├── shorts_generator/      # Legacy CLI engine library (SamurAIGPT)
│   ├── storage/              # Temp file storage per task
│   │   └── test_pipeline/    # Testing pipeline cache
│   ├── requirements.txt       # Core Python dependencies
│   ├── requirements-local.txt # Python dependencies for local processing (faster-whisper, opencv, etc.)
│   └── .env                   # Backend environment variables
├── frontend/                 # Next.js 15 Frontend (Borgir Version — No Auth & No Billing, No Docker)
│   ├── src/                  # Next.js Source Code (App Router, React 19, Tailwind v4, shadcn/ui)
│   │   ├── app/              # Halaman "/" (paste URL) & "/tasks/[id]" (progress & player)
│   │   ├── components/       # UI Components (vertical-player, clip-card, task-progress, etc.)
│   │   └── lib/              # Utilities & SSE hook
│   ├── package.json          # Node.js dependencies
│   └── tsconfig.json         # TypeScript configuration
├── plan.md                   # Development plan & technical designs
└── AGENTS.md                 # Developer guide (this file)
```

---

## 2. Video Processing Flow (Backend Pipeline)

When a user submits a YouTube video link to the `/tasks` endpoint, the backend triggers an asynchronous pipeline consisting of 7 distinct stages:

1. **DOWNLOAD (0-15%)** — [downloader.py](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/backend/app/engine/downloader.py)
   * Downloads the video using `yt-dlp`.
   * Caches the file as `source_{video_id}.mp4` in the `storage` directory to avoid re-downloading.

2. **TRANSCRIBE (15-35%)** — [transcriber.py](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/backend/app/engine/transcriber.py)
   * Uses Gemini 2.5 Flash to generate a full transcript with speaker diarization.
   * **Dual Caching**: Saves output in two formats: `.srt` (standard) and `.json` (retaining speaker metadata).
   * Robustly parses keys for both `start`/`end` and `start_time`/`end_time` formats.

3. **RANK HIGHLIGHTS (35-50%)** — [highlights.py](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/backend/app/engine/highlights.py) & [llm.py](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/backend/app/engine/llm.py)
   * Prepend speaker labels `[Speaker X]:` to each line of transcript text so the highlight model understands conversational flow.
   * Sends the formatted transcript to the local highlight model **mimo-v2.5-pro** (running at `http://localhost:20128/v1` via OpenAI-compatible schema) to identify candidate viral moments.
   * Analyzes candidates using `VIRALITY_CRITERIA` and discards overlapping duplicates (>50% overlap).

4. **SMART CROP PLAN (50-65%)** — [smart_crop.py](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/backend/app/engine/smart_crop.py)
   * Analyzes video frames at **2 FPS** to detect face coordinates using OpenCV DNN Face Detector (SSD ResNet-10).
   * Evaluates active speaking levels using *Mouth Motion Energy* (absolute pixel changes on the speaker's mouth region).
   * Detects scene transitions (*Scene Cut Detection*) via BGR color histogram correlation to instantly reset camera panning interpolations.
   * Classifies shot types: `closeup` (face > 30% of frame), `medium` (15-30%), and `wide_cut` (< 15%).

5. **RENDER VERTICAL (65-90%)** — [render.py](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/backend/app/engine/render.py) & [subtitles.py](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/backend/app/engine/subtitles.py)
   * Crops the video to a vertical 9:16 aspect ratio with dynamic coordinates smoothed via Exponential Moving Average (EMA) to prevent camera panning jitter.
   * Automatically applies a **Letterbox** visual effect (centering the original horizontal video and overlaying it on top of a zoomed, Gaussian-blurred background) if the shot is classified as a `wide_cut`.
   * Burns *viral-bold* subtitles (word-level karaoke, highlighting active words in yellow/red) using ffmpeg ASS filters.

6. **SUBTITLE STYLE (within Stage 5)** — [subtitles.py](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/backend/app/engine/subtitles.py)
   * Renders caption text in the lower 75% of the frame, maxing out at 2 lines, using TikTok Sans / Inter Black fonts.

7. **FINALIZE (90-100%)** — [pipeline.py](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/backend/app/engine/pipeline.py)
   * Generates a final `highlights.json` manifest containing metadata (title, duration, virality score, explanation) and download URLs for each mp4 clip.

---

## 3. How to Run Locally

### 3.1 Running the Backend (FastAPI)

1. Ensure a Redis server is active on port `:6379`.
2. Navigate to the `backend` directory, install dependencies, and activate the virtual environment:
   ```powershell
   cd backend
   uv venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt -r requirements-local.txt
   ```
3. Configure the `.env` file inside `backend/` appropriately:
   ```env
   LLM_PROVIDER=openai
   OPENAI_API_KEY=your_key_here
   OPENAI_BASE_URL=http://localhost:20128/v1
   OPENAI_MODEL=mimo/mimo-v2.5-pro
   GEMINI_API_KEY=your_gemini_api_key_here
   ```
4. Start the FastAPI server:
   ```powershell
   python -m uvicorn app.main:app --reload --port 8000
   ```

### 3.2 Running the Frontend (Next.js)

1. Navigate to the `frontend` directory and install dependencies:
   ```powershell
   cd frontend
   pnpm install
   ```
2. Start the development server:
   ```powershell
   pnpm run dev
   ```
   The frontend app will run at `http://localhost:3107`.

---

## 4. Rules of Thumb for Developers

1. **Maintain Workspace Integrity**: Do not create new directories outside of `backend/` and `frontend/`. Place all UI improvements inside `frontend/` and all processing logic, API routes, and AI engines inside `backend/`.
2. **Asynchronous Code**: Execute all heavy blocking operations (yt-dlp downloads, transcription, video rendering) inside a thread pool using `run_in_threadpool` to prevent blocking the async FastAPI event loop.
3. **Double Caching**: When modifying transcription or highlight engines, ensure the fallback reading of `.json` (speaker metadata) and `.srt` cache files remains functional to avoid calling expensive external APIs.
4. **No Secrets**: Never commit real API keys to the repository. Always use `.env.example` as a template.
5. **Strict Commit & Push Rules**:
   - **Check Before Committing**: Never perform automatic commits or pushes. Always check if there are major/large changes first, or wait for direct explicit instructions from the user before committing and pushing code.
   - **Tidy Git Commit Messages**: Write neat, structured, and detailed commit messages (e.g., using prefix-convention like `feat:`, `fix:`, `refactor:`) describing exactly what was modified so that the history remains clear on GitHub.

---

## 5. Workflow for Handling Contributor Bot PRs (Jules)

When receiving Pull Requests from automatic contributor bots (e.g., `google-labs-jules[bot]`), follow these strict steps to maintain a clean git history and contributor attribution:

1. **Do NOT Merge Directly on GitHub**:
   Do not use the GitHub UI merge buttons (Squash and merge, Rebase and merge, or Create a merge commit) for bot PRs. This prevents the bot from being registered as an official contributor in the repository's graphs.

2. **Pull and Test Locally**:
   Before merging, check out the PR branch locally to run and test the changes.
   * Verify there are no TypeScript compiler errors, syntax errors, or runtime breaks.
   * Run the test suite if appropriate.

3. **Manual Clean Squash-Merge**:
   To merge the changes without attributing them to the bot:
   * Apply the changes to the `main` branch locally.
   * Commit the changes under the repository owner's Git user configuration (`sansaks-jpg` / `Sandi Ardiansyah`), ensuring the author metadata is explicitly set to `sansaks-jpg`.
   * Example:
     ```powershell
     git checkout main
     # Apply changes manually or squash-merge
     git commit --author="Sandi Ardiansyah <sandisansan1407@gmail.com>" -m "merge: Description of changes (PR #X)"
     ```

4. **Push and Close the PR**:
   * Push the updated `main` branch to the remote repository: `git push origin main`.
   * Manually **Close** the PR on the GitHub web interface (do not merge it) and leave a comment stating that the changes have been integrated manually.

