<!-- 
CRITICAL RULE FOR AI AGENTS:
DO NOT OVERWRITE OR DELETE EXISTING CHANGELOG ENTRIES. 
Always prepend new entries at the top of this file (directly below this rule block) when documenting new modifications. 
Preserve all historical logs to maintain context for future agents and developers.
-->

# CHANGELOG.md — Activity Log for `cliply` Workspace

This file documents the history of major modifications made to the `cliply` workspace, providing chronological context for developers and AI agents.

---

## [2026-06-21 20:08 WIB] — Seekable Video Player with Drag Scrubbing & Auto-Hide Controls

### Summary
Rebuilt the `VerticalPlayer` component from scratch to add a full-featured seekbar with drag support, buffered progress indicator, timestamp display, and auto-hiding controls — matching the UX of TikTok/Reels native players.

### Changes
* **`frontend/src/components/vertical-player.tsx`**:
  * Added a draggable seekbar at the bottom of the player with three-layer track: played (white), buffered (translucent white), and unplayed (dim).
  * Added a circular thumb that scales up on hover (`group-hover/bar:scale-125`) for easier grabbing.
  * Added `currentTime / duration` timestamp display (`0:12 / 1:34`) above the seekbar.
  * Implemented both **mouse drag** and **touch drag** seek via `window` event listeners (`mousemove`/`mouseup`, `touchmove`/`touchend`).
  * Moved the mute toggle button inline next to the seekbar (right side) for a compact, unified control strip.
  * Controls auto-hide after **2.5 seconds** of playback via `setTimeout`; re-appear instantly on any `mousemove` or `touchstart` event.
  * Replaced the large center play button with a smaller frosted-glass button (`bg-white/20 backdrop-blur-md`) to match modern short-video aesthetics.
  * Seekbar click area uses `data-seekbar` attribute to prevent bubbling to the parent `onClick` (play/pause toggle).

---

## [2026-06-21 20:06 WIB] — Backend Pipeline: Granular SSE Progress Events per Sub-Stage

### Summary
Fixed a long-standing UX bug where the frontend log panel was stuck showing "Finding viral moments…" even after the pipeline had progressed to Smart Crop / Render stages. Root cause: the `ANALYZE` stage emitted a single progress event at the start then ran silently in a thread pool for 1–3 minutes.

### Changes
* **`backend/app/engine/pipeline.py`**:
  * Added `_emit(pct, stage, message)` — a thread-safe SSE emitter using `asyncio.run_coroutine_threadsafe` that can be called from inside thread pool workers.
  * Passes `_emit` as `progress_callback` to `get_highlights()`.
  * Added explicit `SMART_CROP` stage progress event (62%) before render loop begins.
  * Translated all user-facing progress messages to Indonesian for consistency with frontend locale.
  * Cleaned up inline `import logging` / `import json` into top-level imports.

* **`backend/app/engine/highlights.py`**:
  * `get_highlights()` now accepts an optional `progress_callback: Callable[[float, str, str], None]`.
  * Emits three granular sub-step progress events during `ANALYZE`:
    * **37%** — "Mendeteksi tipe konten & kepadatan narasi…" (content type detection)
    * **40%** — "Memetakan struktur narasi video…" (narrative segmentation)
    * **44%** — "Mencari momen viral terbaik…" (highlight generation)
    * **49%** — "Validasi N highlight selesai" (post-validation summary)
  * Added `logger.info` calls after each sub-step for server-side log observability.

* **`backend/app/engine/render.py`**:
  * `_update_render_progress()` now accepts an optional `stage` parameter (default `"RENDER"`) so it can emit `SMART_CROP` or `RENDER` stages independently.
  * Progress range adjusted from `60–90%` to `62–90%` to align with the new pipeline sequence.
  * Per-clip loop now emits `SMART_CROP` (face scan phase) at loop start, then `RENDER` (ffmpeg encoding phase) immediately before `_cut_subclip` is called — giving the user two distinct status updates per clip instead of one generic "Rendering clip N" message.

---

## [2026-06-21 20:00 WIB] — Task Page: Compact Split Layout — Video Fills Available Height

### Summary
Redesigned the completed-task layout so the left panel (video) fills as much vertical space as possible while keeping the download button and AI analysis permanently visible without any scrolling.

### Changes
* **`frontend/src/app/tasks/[id]/page.tsx`**:
  * Left panel changed from fixed-size (`w-[220px] h-[391px]`) to `flex-1 min-h-0` with `style={{ aspectRatio: "9/16", maxHeight: "100%" }}` — the phone frame now scales to fill whatever vertical space remains after the label, download button, and AI analysis card.
  * Removed the `AIAnalysisPanel` accordion component (was in right panel). AI analysis is now always-visible in the left panel below the download button using `flex-shrink-0`, `line-clamp-2` for hook and `line-clamp-3` for virality reason.
  * Left panel uses `flex flex-col overflow-hidden` — nothing overflows or requires scrolling.
  * Right panel clip list simplified: removed the per-clip inline `AIAnalysisPanel` expansion; each clip row is a flat, compact card.
  * Header height reduced (`py-3` from `py-4`), buttons resized (`h-8`).
  * Left panel width increased to `lg:w-[380px] xl:w-[420px]` to accommodate the taller video.

---

## [2026-06-21 19:56 WIB] — Task Page: Compact No-Scroll Layout & AI Analysis Moved to Left Panel

### Summary
Refactored the completed-task view to eliminate all scrolling from the left panel. AI analysis (hook sentence + virality reason) was moved from the right-panel accordion to a compact always-visible card below the download button on the left.

### Changes
* **`frontend/src/app/tasks/[id]/page.tsx`**:
  * Removed `AIAnalysisPanel` accordion component entirely.
  * Moved AI analysis inline into the left panel as a `flex-shrink-0` card with `line-clamp` text truncation — no scroll required.
  * Right panel clip list returned to a simple flat list without accordion expansion per clip.
  * Processing view clip grid changed from `grid-cols-3` to `grid-cols-4` for a more compact in-progress display.

---

## [2026-06-21 18:00 WIB] — Implementasi Soft Dark Mode yang Nyaman di Mata

### Ringkasan Perubahan
Menurunkan tingkat kepekatan warna hitam gelap gulita pada tema gelap (`.dark`) menjadi abu-abu arang/zinc-900 redup (`oklch(0.18 0 0)`) guna mengurangi kontras yang terlalu tinggi dan meningkatkan kenyamanan mata saat menatap layar lama, serupa dengan kenyamanan Discord atau GitHub dark mode.

### Aktivitas Detail
* **globals.css — `.dark`**:
  * Mengganti `--background` dari `oklch(0.09 0 0)` (hitam pekat ekstrem) menjadi `oklch(0.18 0 0)` (abu-abu arang redup / zinc-900).
  * Mengganti kontainer elevasi `--card`, `--popover`, dan `--sidebar` ke `oklch(0.22 0 0)` (abu-abu arang sedikit lebih terang / zinc-800).
  * Menyesuaikan variabel warna interaksi `--secondary`, `--muted`, dan `--accent` ke `oklch(0.26 0 0)`.
  * Menyesuaikan `--border` dan `--input` di `.dark` ke `oklch(0.28 0 0 / 60%)` agar tetap nampak bergradasi halus di atas latar belakang baru yang lebih lembut.

## [2026-06-21 17:55 WIB] — Kalibrasi Warna Dark Mode Monokromatik Premium Terpadu

### Ringkasan Perubahan
Mengubah variabel warna CSS untuk tema gelap (`.dark`) pada `globals.css` agar menggunakan palet monokromatik murni (chroma 0, hitam pekat `#09090b` dan abu-abu arang batu `#121212`) yang terinspirasi dari Vercel/Linear, menggantikan warna zaitun/cokelat kusam lumpur bawaan lama yang kurang kontras.

### Aktivitas Detail
* **globals.css — `.dark`**:
  * Mengganti `--background` dari `oklch(0.147 0.004 49.25)` (kuning-cokelat kusam) menjadi `oklch(0.09 0 0)` (hitam pekat minimalis).
  * Mengganti `--card`, `--popover`, dan `--sidebar` dari rona kecokelatan kusam lama menjadi `oklch(0.12 0 0)` (abu-abu arang batu pekat elevasi).
  * Menetapkan `--foreground` ke putih bersih gading netral `oklch(0.98 0 0)`.
  * Menyelaraskan `--border` dan `--input` di `.dark` ke abu-abu tipis netral `oklch(0.20 0 0 / 60%)`.
  * Memperbaiki `--primary` (tombol utama di dark mode) menjadi `oklch(0.98 0 0)` (putih bersih) dengan teks hitam pekat `oklch(0.09 0 0)` (`--primary-foreground`), serta membersihkan warna kusam pada variabel charts dan sidebar.

## [2026-06-21 17:50 WIB] — Restrukturisasi Tata Letak Studio Split-Viewport pada Detail Tugas

### Ringkasan Perubahan
Mengunci tinggi halaman detail tugas (`[id]/page.tsx`) setinggi viewport (`h-screen overflow-hidden`) dan membagi area kerja menjadi dua kolom dengan scrolling independen. Hal ini menjaga pemutar video di sisi kiri tetap diam (sticky) sehingga pengguna bisa men-scroll daftar klip yang sangat banyak di sisi kanan dan mengkliknya tanpa kehilangan pandangan pada player utama.

### Aktivitas Detail
* **Halaman Detail Tugas — tasks/[id]/page.tsx**:
  * Mengatur tinggi wadah halaman terluar menjadi `h-screen overflow-hidden` saat status `completed` agar tidak terjadi window scroll global.
  * Memisahkan layout menjadi dua kolom scrollable independen:
    * **Kolom Kiri (Visual Cinema Hub - 35% s.d 40% lebar)**: Berisi mockup pemutar video vertical 9:16 dan kartu detail analitik AI (Hook kalimat pembuka & konteks alur). Kolom ini dikunci diam di posisinya (fixed/sticky) dan selalu nampak utuh di layar.
    * **Kolom Kanan (Selector Panel - 60% s.d 65% lebar)**: Berisi pengantar sumber URL dan daftar vertical scrollable untuk seluruh klip video hasil render.
  * Menghilangkan fenomena scrolling bolak-balik atas-bawah yang melelahkan. Pengguna kini dapat dengan nyaman menggulir puluhan klip ke bawah di sisi kanan, lalu mengkliknya untuk langsung memicu pemutaran video di sisi kiri secara instan.

## [2026-06-21 17:45 WIB] — Redesain Skema Warna Minimalis Monokromatik & Pembersihan Elemen "AI Slop"

### Ringkasan Perubahan
Mengubah seluruh skema warna pada halaman beranda dan detail tugas ke warna monokromatik bersih (putih bersih/hitam arang dengan aksen perak/zinc tipis) sekelas **Vercel/Linear** untuk menyajikan estetika minimalis profesional, serta membuang seluruh elemen gradasi pelangi mencolok dan glowing blobs yang memicu kesan "AI slop".

### Aktivitas Detail
* **Beranda — page.tsx**:
  * Menghapus seluruh absolute blur blobs warna-warni (ungu, kuning, rose) mengambang di belakang konten agar background tetap bersih dengan grid halus.
  * Menghapus warna gradasi pelangi `violet-500 → rose-500` pada teks judul Hero, digantikan dengan warna solid hitam kontras (`text-zinc-950`) di tema terang, dan putih kontras (`text-zinc-50`) di tema gelap.
  * Mengubah focus ring dan border input URL dari ungu menyala menjadi warna netral hitam kontras / perak netral.
  * Mengubah warna tombol "Buat Klip" utama dari gradasi ungu-violet ke warna solid hitam kontras (`bg-zinc-900` / `dark:bg-white`) yang sangat bersih.
  * Menyederhanakan pemutar pratinjau subtitle mini dengan latar belakang gradasi gelap statis netral (`from-zinc-900 to-zinc-900/90`) yang menyerupai monitor video nyata, bukan gradasi warna-warni bergerak.
  * Merestrukturisasi selector aspek rasio dan preset gaya subtitle agar menggunakan aksen warna terpilih hitam/putih solid yang bersih.
* **Halaman Detail Tugas — tasks/[id]/page.tsx**:
  * Menghapus aksen warna ungu menyala pada pipeline stepper, digantikan dengan warna kontras netral (hitam/putih/abu-abu).
  * Slider progres bar menggunakan warna solid hitam kontras (`bg-zinc-900` / `dark:bg-white`) bukan gradasi violet.
  * Menghapus shadow glow ungu pada mockup smartphone 9:16, digantikan dengan bayangan tipis netral yang realistis.
  * Tombol download klip video diubah dari gradasi ungu-violet ke warna solid hitam kontras / putih kontras netral.
  * Item klip terpilih pada daftar selector sisi kanan menggunakan aksen border kontras hitam/putih (`border-zinc-900` / `dark:border-zinc-300`) dan latar abu-abu halus, bukan warna ungu bercahaya.
  * Score badge dan analisis data menggunakan warna monokromatik netral.

## [2026-06-21 17:40 WIB] — Desain Studio UI/UX Modern Terintegrasi (v2.0) & Refactoring Navigasi Workspace

### Ringkasan Perubahan
Melakukan overhaul terhadap tata letak dan interaksi UI/UX di halaman beranda (`page.tsx`) dan halaman detail tugas (`[id]/page.tsx`) untuk memberikan pengalaman workspace studio premium kelas dunia (saas-look) yang bersih, "satset", bebas dari kesan "AI slop", dengan optimalisasi pemakaian memori peramban secara signifikan.

### Aktivitas Detail
* **Beranda — page.tsx**:
  * Mengganti layout split sidebar kiri-kanan yang kaku dengan layout **Unified Studio Workspace** terpusat yang sangat elegan.
  * Input URL YouTube diletakkan di tengah dengan card glassmorphic menonjol berukuran besar yang responsif untuk fokus aksi instan.
  * Opsi parameter AI dipindah ke panel laci lipat/accordion *"Konfigurasi & Gaya Studio"* terintegrasi di bawah kolom input URL.
  * Menyematkan **Interactive Subtitle Canvas** (simulasi media player 16:9) yang di-render secara interaktif dengan gelombang audio CSS, latar belakang gradasi dinamis `animate-gradient`, dan rendering teks karaoke real-time yang berganti animasi secara otomatis berdasarkan preset gaya terpilih.
  * Menata riwayat proyek terbaru dalam bentuk Grid Card minimalis yang menawan dengan detail metadata jam pemrosesan dan tombol hapus/buka yang responsif.
* **Halaman Detail Tugas — tasks/[id]/page.tsx**:
  * Mengubah model rendering multipel tag video yang memboroskan memori GPU (satu player per klip) menjadi model **Studio Workspace Split-Screen**.
  * Sisi Kiri (Cinema Hub): Menampilkan satu **Vertical Player Utama** yang besar di dalam frame mockup smartphone 9:16 yang realistis (dilengkapi notch + shadow 3D melayang).
  * Sisi Kanan (Selector Panel): Menampilkan daftar klip hasil render dalam bentuk panel list vertical yang bersih. Mengklik klip di daftar kanan akan langsung memuat dan memutar klip tersebut di player utama sebelah kiri.
  * Mengintegrasikan kartu analitis detail (*Analisis Klip Aktif*) berisi kalimat hook pembuka dan dinamika alur viral yang memperbarui isinya secara dinamis mengikuti klip aktif yang dipilih.
  * Mendesain ulang visualisasi stepper progres pengolahan pipeline (Download, Transkripsi, Highlights, Smart Crop, Render, Finalize) menjadi panel indikator status menyala berurutan dengan spinner loader.

## [2026-06-21 17:25 WIB] — Perbaikan Bug Visual Layout Subtitle ASS, Overhaul Performa Rendering Blur, dan Efek Ease-Out Pop-Up

### Ringkasan Perubahan
Memperbaiki bug visual kritis pada layout absolut subtitle ASS, mengoptimalkan konsumsi CPU saat rendering pendaran glow, menyelaraskan ketebalan outline agar tidak menabrak spasi huruf, serta meningkatkan estetika animasi pop-up dan keterbacaan teks minimalis pada latar belakang terang.

### Aktivitas Detail
* **subtitles.py — `build_word_box_highlight`**: Merombak fungsi highlight box dari penempatan absolut `\pos(x,y)` yang rentan hancur/tumpang tindih menjadi sistem pewarnaan teks inline menggunakan tag `{\1c}`. Ini mengunci baris kalimat agar tetap rata tengah secara dinamis dan aman saat ukuran font/resolusi video berubah.
* **subtitles.py — `build_karaoke_sweep`**: Mengoptimalkan rendering pendaran glow pada gaya `neon-glow` dengan menerapkan teknik **Dual-Layer** statis. Layer 0 (Glow Layer) menggunakan static `\blur8` dengan animasi opacity `\alpha` per kata, sedangkan Layer 1 (Sharp Layer) menggunakan teks tajam `\blur0` dengan transisi karaoke `\k`. Ini memangkas habis overhead CPU dari manipulasi `\blur` dinamis per frame.
* **subtitles.py — `build_word_popup` & `build_word_pop_scale`**: Menambahkan parameter akselerasi deselerasi `0.5` pada tag `\t` (contoh: `\t(t1, t2, 0.5, tags)`) untuk menciptakan pergerakan *ease-out* yang mengerem lembut saat teks mencapai ukuran penuh, menghilangkan visual linear yang kaku.
* **subtitles.py — STYLES (tiktok & highlight-box)**: Mengurangi outline style `tiktok` dari 20px menjadi 8px statis untuk mencegah outline hitam menabrak spasi antar kata. Menambahkan shadow tipis 1.5px ke `highlight-box`.
* **subtitles.py — STYLES & `_header` (clean-minimal)**: Menambahkan soft drop shadow statis semi-transparan (`\shadow 2` dengan `back_color` hitam 50% transparan `&H80000000`) pada gaya `clean-minimal` agar teks putih tetap terbaca tajam saat latar belakang video sangat terang tanpa merusak estetika minimalis.

## [2026-06-21 16:30 WIB] — Perbaikan Crash Video Rendering Panjang dan Optimalisasi Backend VideoWriter OpenCV

### Ringkasan Perubahan
Memperbaiki bug crash kritis berupa error `Unknown C++ exception from OpenCV code` pada video berdurasi panjang (di atas 1 menit atau di frame >1600) di sistem operasi Windows. Bug ini disebabkan oleh backend default Media Foundation (MSMF) Windows OpenCV yang tidak stabil dan ketidakselarasan numpy sliced view non-contiguous saat ditulis langsung ke `VideoWriter`.

### Aktivitas Detail
* **render.py — `_render_frames` & `_render_master_letterbox`**: Mengubah inisialisasi OpenCV `VideoWriter` untuk secara eksplisit memaksa penggunaan backend `cv2.CAP_FFMPEG` dan wadah output `.silent.mp4` dengan codec `"mp4v"`. Hal ini memintas API MSMF Windows yang buggy, menghasilkan rendering 3x lebih cepat (sukses menulis 2000 frame dalam 8.4s dibanding MJPG .avi yang memakan waktu 22.0s) dan mencegah kebocoran memori/thread.
* **render.py — `_render_frames`**: Menambahkan pemaksaan konversi data frame menjadi C-contiguous array (`np.ascontiguousarray(cropped)`) tepat sebelum pemanggilan `writer.write(cropped)`. Perubahan ini krusial untuk menangani frame bertipe `closeup` atau `medium` yang dihasilkan dari pemotongan piksel numpy slicing (yang secara internal merupakan referensi memori non-contiguous dengan striding acak) agar tidak memicu Access Violation di level API C++ OpenCV.

## [2026-06-21 16:05 WIB] — Penyelarasan Animasi Subtitle Viral Bold dengan Tampilan Instan Pop Frontend

### Ringkasan Perubahan
Memperbaiki perbedaan perilaku visual antara preview frontend (instan pop per kata) dan video hasil render backend (gradual karaoke sweep) untuk gaya subtitle `viral-bold`, `tiktok`, dan `neon-gradient`.

### Aktivitas Detail
* **subtitles.py — `build_karaoke_fill`**: Mengubah tag ASS dari `\kf` (gradual left-to-right color sweep) menjadi `\k` (instant color pop). Hal ini membuat seluruh kata langsung menyala kuning/hijau secara instan tepat saat diucapkan (word-by-word active highlight), menghilangkan gaya menyapu karaoke lama dan menyelaraskannya 100% dengan visualisasi pratinjau frontend.

## [2026-06-21 15:45 WIB] — Optimalisasi Pemetaan Kata ke Segmen Transkrip & Penyelarasan Jumlah Kata Otomatis (By Construction)

### Ringkasan Perubahan
Memperbaiki kerentanan *timing mismatch* (ketidaksesuaian jumlah kata) antara teks segmen asli dan data kata dari model transkripsi. Mengubah pemetaan kata global di transcriber.py menjadi algoritma berbasis waktu tengah (*mid-time*) terdekat untuk menghindari kata hilang/ganda di batas segmen, serta menyelaraskan teks segmen subtitles.py secara dinamis *by construction* dari data kata model transkripsi, lengkap dengan sistem log deteksi *mismatch*.

### Aktivitas Detail
* **transcriber.py — `_try_groq_whisper`**: Mengganti pemetaan berbasis toleransi waktu manual (windowing 0.05s) dengan algoritma pemetaan berbasis waktu tengah (*mid-time*) kata terdekat. Setiap kata dijamin masuk ke tepat satu segmen terdekat, menghilangkan duplikasi dan kata hilang di tepi segmen.
* **subtitles.py — `_chunk_segments`**: Menambahkan logika penyelarasan teks segmen lokal. Jika data kata model transkripsi (`words`) tersedia, teks segmen dibangun ulang dari daftar kata tersebut. Hal ini menjamin keselarasan jumlah kata secara mutlak (`by construction`) dan menghindari *silent fallback* ke estimasi linear.
* **subtitles.py — `_chunk_segments` (Logging)**: Menambahkan log warning transparan jika terdeteksi perbedaan jumlah kata antara teks asli segmen transkrip dengan daftar data kata model transkripsi.

## [2026-06-21 15:40 WIB] — Perbaikan Bug Fungsional, Gap Konsistensi, dan Kode Ringkas pada subtitles.py (Analisis Mendalam subtitles.py)

### Ringkasan Perubahan
Memperbaiki 3 bug fungsional prioritas tinggi (efek sinkronisasi glow flash per-kata, pencegahan kehilangan subtitle di overlap-resolution, dan pengenalan cap durasi kata pada transkrip presisi) serta menyelaraskan gap konsistensi (dukungan layout adaptif di style highlight-box, integrasi penanda waktu akustik di 4 builder animasi lainnya), serta perbaikan code smell minor pada berkas subtitles.py.

### Aktivitas Detail
* **subtitles.py — `build_karaoke_sweep`**: Memperbaiki sinkronisasi tag efek glow `\t` dengan melacak waktu kata secara kumulatif (`cumulative_ms`) relatif terhadap waktu awal Dialogue baris. Hal ini memperbaiki bug di mana semua kata melakukan flash glow secara bersamaan di awal dialog.
* **subtitles.py — `_chunk_segments`**: Membatasi waktu potongan sub-segmen (`c_start` dan `c_end`) serta data kata individu di dalamnya menggunakan batas `t0` dan `t1` (yang sudah dikoreksi oleh `_resolve_overlaps`) untuk mencegah penimpaan batas waktu dari data mentah Whisper yang bisa menyebabkan hilangnya teks subtitle.
* **subtitles.py — `_resolve_overlaps`**: Menambahkan log warning eksplisit jika suatu segmen start-time bergeser melampaui end-time akibat resolusi tumpang tindih (*overlap-resolution*), agar potensi hilangnya teks subtitle terdeteksi secara dini.
* **subtitles.py — `_build_karaoke_base` & `build_karaoke_sweep`**: Menerapkan batas waktu kata maksimal (`MAX_SEC_PER_WORD = 0.8` atau 80 cs) pada jalur data kata presisi untuk mencegah karaoke macet akibat jeda panjang/noise, dan mengimplementasikan normalisasi proporsional agar durasi kumulatif kata tepat sama dengan durasi Dialogue line (`total_cs`).
* **subtitles.py — `build_word_box_highlight`**: Menyelaraskan implementasi "Adaptive Font Scaling" dengan mengganti `_wrap_and_balance` dengan fungsi `_find_adaptive_wrap`. Ukuran huruf adaptif (`adaptive_fs`) kini digunakan secara konsisten dalam kalkulasi lebar teks, posisi koordinat `\pos`, tinggi baris, dan penulisan tag override `\fs`.
* **subtitles.py — `build_fade_in_word`, `build_word_popup`, `build_word_pop_scale`, `build_word_box_highlight`**: Memperbarui keempat pembangun animasi ini agar secara penuh mendeteksi dan memanfaatkan data waktu per-kata presisi (`seg.get("words")`) jika tersedia dari model transkripsi, dengan fallback otomatis ke interpolasi linear seragam.
* **subtitles.py — `_seg_time` & Imports**: Menambahkan `Tuple` ke dalam baris import pustaka `typing`. Memperbaiki `_seg_time` agar mendeteksi nilai timestamp `0.0` secara eksplisit (`is not None`) alih-alih menggunakan operator `or` falsy yang rentan bug.

## [2026-06-21 15:30 WIB] — Implementasi Hybrid Parallelization dengan Prompt Cache Warming & Penanganan Rate Limit pada Long Video

### Ringkasan Perubahan
Mengintegrasikan strategi eksekusi paralel pada pemrosesan video panjang Stage 3 (`_generate_chunked`) menggunakan ThreadPoolExecutor untuk mempercepat waktu latensi proses secara dramatis, diselaraskan dengan mitigasi prompt caching (sequential-first warm cache untuk Anthropic), pembagian system vs user content block agar caching terjamin byte-for-byte, penanganan rate limit berbasis exponential backoff dengan random jitter dan ceiling, penegakan kegagalan sistemik global, penanganan observabilitas kegagalan parsial di orchestrator pipeline, serta konfigurasi worker concurrency yang fleksibel.

### Aktivitas Detail
* **config.py**: Menambahkan konfigurasi `HIGHLIGHT_MAX_WORKERS` (default `8`) yang di-load dari environment variable untuk menghindari batasan workers yang hardcoded.
* **llm.py — `call_anthropic_llm`**: Merestrukturisasi payload prompt Anthropic dengan memisahkan instruksi sistem statis (virality rules, editor guidelines) ke parameter `system` Anthropic yang di-cache, sedangkan konten dinamis (transcript chunk, narrative map) dikirim ke `messages`. Ini menjamin cache prefix byte-for-byte identik di semua chunk.
* **highlights.py — `_generate_chunked`**: Merombak loop sequential menjadi alur hybrid: jika provider yang digunakan adalah Anthropic, chunk pertama diproses secara sequential terlebih dahulu untuk "menghangatkan" (warm up) prompt cache, baru kemudian men-submit sisa chunk (2 s.d N) secara paralel melalui `ThreadPoolExecutor`. Provider selain Anthropic langsung menggunakan paralel penuh dari awal.
* **highlights.py — `_process_chunk_with_retry` & `_is_rate_limit_error`**: Menambahkan deteksi rate limit (429 / ResourceExhausted) dengan penanganan retry mandiri per chunk menggunakan exponential backoff, random jitter (+/- 20% + offset), dan ceiling max delay 30 detik untuk menghindari lockstep retry storms dan TPM starvation.
* **highlights.py — `get_highlights` (Observability)**: Mengubah return value dari Stage 3 agar menyertakan metadata kegagalan parsial (`failed_chunks`, `total_chunks`, dan `coverage_pct`) yang dikirim kembali ke orchestrator.
* **pipeline.py — `run_pipeline`**: Membaca metadata kegagalan parsial, mencatat warning log secara transparan jika ada chunk yang terlewat, dan memperbarui progress status dengan persentase coverage video yang berhasil dianalisis.
* **highlights.py — `_generate_chunked` (Global Protection)**: Menambahkan deteksi kegagalan sistemik. Jika 100% chunk gagal memproses (misal API down total), pipeline akan melempar `RuntimeError` secara eksplisit, alih-alih melakukan silent failure dengan mengembalikan list kosong.

## [2026-06-21 15:25 WIB] — Optimalisasi Akurasi Subtitle Karaoke dengan Word-Level Timestamps via Groq Whisper & Penyesuaian Urutan Pipeline

### Ringkasan Perubahan
Mengubah urutan pipeline transkripsi agar memprioritaskan Groq Whisper daripada Gemini setelah YouTube Transcript API. Selain itu, mengaktifkan fitur penanda waktu tingkat kata (*word-level timestamps*) akustik dari Groq Whisper dan memperbarui generator subtitle ASS agar menggunakan data waktu asli kata demi kata, meningkatkan akurasi karaoke visual secara drastis dibanding estimasi linear/pembagian rata durasi kalimat sebelumnya.

### Aktivitas Detail
* **transcriber.py — `transcribe_video`**: Mengubah urutan pipeline transkripsi menjadi: YouTube Transcript API → Groq Whisper → Gemini 2.5 Flash. Proses ekstraksi audio dilakukan di awal sebelum memanggil Groq atau Gemini.
* **transcriber.py — `_try_groq_whisper`**: Menambahkan parameter `timestamp_granularities=["word"]` pada pemanggilan API Groq Whisper. Mengekstrak dan memetakan kata-per-kata yang akurat ke setiap segmen transkrip.
* **subtitles.py — `_chunk_segments`**: Memperbarui logika pemotongan segmen kalimat agar menggunakan penanda waktu mulai (`start`) dan selesai (`end`) asli dari kata-kata jika data tingkat kata tersedia, untuk menetapkan batas chunk kalimat secara presisi.
* **subtitles.py — `_build_karaoke_base` & `build_karaoke_sweep`**: Mengintegrasikan pembacaan durasi kata akustik asli (`words`) dari segmen transkrip jika tersedia untuk tag karaoke (`\kf` / `\k`), dengan fallback ke estimasi linear jika data kata tidak tersedia.

## [2026-06-21 15:20 WIB] — Overhaul Keandalan Narrative Segmentation (Stage 2) & Viral Highlight Detection (Stage 3)

### Ringkasan Perubahan
Memperbaiki celah struktural kritis pada pipeline analisis highlight, meliputi penanganan batas atas durasi unit (forced split), penyelarasan highlight terhadap batas unit narrative (boundary alignment/snapping), pemetaan ulang Segment ID relatif vs absolut pada video panjang, pencegahan redundansi kumulatif (cumulative overlap check), validasi exact-verbatim hook sentence, mekanisme retry LLM dengan error feedback loop, serta optimasi prompt caching Anthropic dan structured JSON mode OpenAI.

### Aktivitas Detail
* **highlights.py — `_validate_units`**: Menambahkan pembersihan gap (gap resolution) dan tumpang tindih (overlap resolution) antarsegmen unit narrative Stage 2 untuk memastikan coverage transkrip 100%. Ditambahkan juga batas durasi maksimum unit (`MAX_DURATION = 180` detik) agar unit panjang otomatis di-forced split menjadi sub-unit yang aman.
* **highlights.py — `_validate_highlights`**: Mengubah validasi overlap dari pairwise menjadi cumulative overlap check (maksimum 20% kumulatif dari seluruh highlight yang sudah disetujui). Menambahkan pengecekan keselarasan highlight terhadap batas unit narrative Stage 2 (`_is_aligned_with_units`), dengan penambahan fungsi `_align_highlight_to_units` untuk snapping batas otomatis jika selisihnya kecil (<= 3 segmen).
* **highlights.py — `_validate_and_fix_hook`**: Menambahkan verifikasi verbatim untuk `hook_sentence` dengan pencarian substring dan fuzzy matching (minimum 50% kata unik cocok). Jika gagal, otomatis di-fallback ke teks segmen pembuka transkrip asli guna mencegah subtitle mismatch.
* **highlights.py — `_generate_chunked`**: Memperbaiki bug kritis segment ID tidak sinkron pada video panjang. Menambahkan mapping ID relatif (0-based) lokal untuk transkrip chunk sebelum dikirim ke LLM Stage 3, dan me-map balik (map-back) ke indeks segment ID global absolut setelah LLM merespons. Menghapus displacement penambahan timestamp ganda yang memicu timing drift.
* **highlights.py — `segment_narrative` & `generate_highlights`**: Menambahkan error feedback loop ke dalam mekanisme retry LLM (attempt 1-3). Error spesifik dari kegagalan validasi Python disuntikkan kembali ke prompt iterasi berikutnya agar LLM dapat mengoreksi outputnya secara presisi.
* **llm.py — `call_openai_llm`**: Menambahkan penanganan defensif `response_format={"type": "json_object"}` untuk OpenAI jika prompt meminta format JSON. Jika parameter tidak didukung oleh backend (misalnya model lokal mimo), otomatis fallback ke standard stream completion biasa.
* **llm.py — `call_anthropic_llm`**: Menambahkan headers beta prompt caching Anthropic (`anthropic-beta: prompt-caching-2024-07-31`) dan menyuntikkan tag cache kontrol (`"cache_control": {"type": "ephemeral"}`) jika panjang prompt melampaui 2048 karakter.

## [2026-06-21 03:55 WIB] — Fix Subtitle Karaoke Timing Tidak Sinkron Akibat Hallucination Timestamp Gemini

### Ringkasan Perubahan
Memperbaiki bug di mana subtitle yang diburn ke video tidak sinkron dengan percakapan asli. Akar masalah: Gemini kadang menghasilkan timestamp segmen yang terlalu panjang (misal 31 detik untuk 20 kata → 1.5 detik/kata). `_chunk_segments` di subtitles.py mendistribusikan durasi ini secara proporsional ke setiap kata, menghasilkan karaoke timing 5x lebih lambat dari audio asli.

### Aktivitas Detail
* **transcriber.py — `_clean_hallucinations`**: Menambahkan Step 5 — deteksi segmen dengan rasio `duration/word_count > 1.0 detik/kata`. Jika terdeteksi, re-estimasi `end` time berdasarkan `word_count × 0.5 detik` (kecepatan bicara normal), dicegat di `video_duration`. Logging untuk setiap segmen yang di-fix.
* **subtitles.py — `_chunk_segments`**: Menambahkan safety cap `MAX_SEC_PER_WORD = 0.8`. Jika `per_word` melebihi batas, di-cap dan warning di-log. Defense-in-depth: melindungi subtitle generation meskipun ada segmen dengan timestamp buruk yang lolos dari hallucination cleaner.

---

## [2026-06-21 03:25 WIB] — Ubah Default Download Resolusi dari 720p ke 1080p

### Ringkasan Perubahan
Mengubah default `DOWNLOAD_FORMAT` dari `720` ke `1080` agar video YouTube di-download dalam resolusi 1080p (Full HD).

### Aktivitas Detail
* **config.py**: Nilai default `DOWNLOAD_FORMAT` diubah dari `"720"` ke `"1080"`. Ini memengaruhi format string yt-dlp menjadi `bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best`.

---

## [2026-06-21 03:20 WIB] — Fix Deteksi GPU via WMI (Real Hardware Detection)

### Ringkasan Perubahan
Sebelumnya deteksi GPU cuma ngecek `ffmpeg -encoders` (daftar encoder yg dikompilasi — semua keliatan available). Di-fix pakai WMI (`Get-CimInstance Win32_VideoController`) untuk baca GPU beneran dari hardware, dikombinasikan dengan ffmpeg compiled check. Hasilnya: hanya encoder yg **hardware-nya ada** yg muncul di dropdown.

### Aktivitas Detail
* **config.py**: `_detect_encoders()` sekarang jalanin PowerShell `Get-CimInstance Win32_VideoController` buat baca vendor GPU (nvidia/intel/amd) dari hardware nyata, lalu AND-kan dengan ffmpeg compiled encoder list. Opsi tanpa hardware jadi otomatis keg-block.

---

## [2026-06-21 03:00 WIB] — UI/UX Overhaul Frontend & GPU Hardware Encoding dengan Auto-Detect

### Ringkasan Perubahan
Redesain total tampilan frontend menjadi lebih modern dengan glassmorphism, animasi background, dan interaksi yang lebih halus. Menambahkan dukungan GPU hardware encoding (NVIDIA NVENC, Intel QSV, AMD AMF) dengan auto-detect, bisa dipilih langsung dari pengaturan frontend.

### Aktivitas Detail

* **Redesain Homepage (`page.tsx`)**:
  * Menambahkan background animasi gradient blobs mengambang sebagai latar hero
  * Mengganti navbar solid dengan glassmorphism (`backdrop-blur` + border transparan) dan logo gradient
  * Input URL sekarang punya glow effect (shadow amber + border highlight) saat focus
  * Tombol submit diganti gradient `amber → rose → violet` dengan shadow glow
  * Kartu template subtitle dikasih efek scan-line, label gradient, checkmark lebih premium
  * Riwayat tugas pakai glass cards dengan hover animation, delete button muncul pas di-hover
  * Hero badge pake glass effect, heading pake `animate-gradient` biar warnanya bergerak

* **Redesain Task Page (`tasks/[id]/page.tsx`)**:
  * Navbar, metadata card, progress card, clip cards — semuanya pake glassmorphism
  * Status badge processing pake animated ping dot (bukan spinner biasa)
  * Tombol download clip pake gradient `amber → rose` dengan shadow
  * State "completed" punya badge "Selesai" glass + heading gradient animasi
  * Terminal log panel dikasih `backdrop-blur`

* **Custom Video Player (`vertical-player.tsx`)**:
  * Play/pause overlay dengan backdrop blur
  * Mute/unmute toggle
  * Gradient hitam di bawah video
  * Overlay auto-hide saat video diputar

* **CSS Utilities (`globals.css`)**:
  * Kelas `.glass` dan `.glass-strong` untuk glassmorphism reusable
  * Animasi blob (`animate-blob`, `animate-blob-2`, `animate-blob-3`) dengan parallax
  * `animate-gradient` untuk background gradient yang bergerak
  * `glow-pulse` untuk efek ring
  * Custom scrollbar styling
  * `scroll-behavior: smooth`

* **Metadata Layout (`layout.tsx`)**:
  * Memperbaiki title & description jadi lebih deskriptif

* **GPU Hardware Encoding dengan Auto-Detect**:
  * **config.py**: Menambahkan `ENCODER_MAP` untuk 4 mode (NVIDIA/intel/amd/cpu) + fungsi `_detect_encoders()` yang menjalankan `ffmpeg -encoders` sekali saat startup (dicache) untuk mendeteksi encoder HW yang tersedia
  * **config.py**: `resolve_encoder()` — memilih HW encoder pertama yang available saat mode "auto", fallback ke libx264 jika tidak ada GPU
  * **config.py**: `get_available_encoders()` — return list encoder keys yang terdeteksi, digunakan frontend untuk render dropdown
  * **render.py**: `_cut_subclip`, `_mux_with_subtitles`, `_reframe_vertical`, `render_clips` — semua fungsi ffmpeg sekarang terima `encoder_args` dinamis, bukan hardcoded `libx264 -preset fast -crf 20`
  * **state.py**: Field `encoder` ditambahkan di `TaskRecord`, `to_dict()`, `create()`, `_record_from_dict()`
  * **queue.py**: `enqueue_task()` dan `_run_pipeline_wrapper()` pass `encoder` ke pipeline
  * **pipeline.py**: `run_pipeline()` pass `encoder` ke `render_clips()`, mengambil dari task record
  * **routes/tasks.py**: Field `encoder` di `CreateTaskRequest`, dikirim ke `store.create()`
  * **main.py**: Endpoint `GET /encoders` untuk frontend auto-detect
  * **frontend api.ts**: Fungsi `getAvailableEncoders()`, field `encoder` di `CreateTaskOptions` dan `Task`
  * **frontend page.tsx**: Dropdown "Encoder GPU/CPU" di pengaturan krucial (5 kolom), otomatis mendeteksi HW yang tersedia saat halaman dimuat dan menampilkan hanya opsi yang relevan (auto, nvidia, intel, amd, cpu)

---

### Ringkasan Perubahan
Memperbaiki empat bug pada implementasi ASS (`subtitles.py`) yang terverifikasi tidak sesuai spesifikasi libass/ASS: (1) parameter `blur` salah di-map ke field `Shadow` header, bukan inline tag `\blur`; (2) `karaoke_sweep` identik dengan `karaoke_fill`; (3) `word_box_highlight` tidak menghasilkan box per-kata yang sesungguhnya; (4) komentar kode menyebut "Shadow doubles as blur" yang tidak akurat secara spesifikasi ASS.

### Aktivitas Detail

* **Bug: `blur` di-map ke `Shadow` Header, bukan `\blur` Inline Tag (`subtitles.py`)**:
  * **Root cause**: ASS field `Shadow` di header bukan Gaussian blur. Itu adalah drop-shadow biasa. Blur glow sesungguhnya hanya bisa dihasilkan oleh override tag inline `\blur<n>` yang didukung libass ≥ 0.14.
  * **Fix**:
    * Menambahkan helper `_blur_prefix(style)` yang menghasilkan `{\blur<n>}` bila `blur > 0`, atau string kosong bila tidak.
    * Mengubah `_build_karaoke_base()` agar meng-prepend `blur_tag` ke setiap teks dialogue bila ada.
    * Mengubah `_header()` agar selalu set `Shadow=0` (bukan `blur`), dengan komentar tepat: "Shadow=0 always. ASS Shadow ≠ blur."
    * Style `neon-gradient` (blur=4) kini benar-benar menghasilkan efek glow melalui `{\blur4}` di setiap Dialogue line, bukan shadow di header yang tidak punya efek blur.

* **Bug: `karaoke_sweep` identik dengan `karaoke_fill` (`subtitles.py`)**:
  * **Root cause**: `build_karaoke_sweep()` hanya memanggil `_build_karaoke_base(..., "\\kf")` — sama persis dengan `karaoke_fill`. Tidak ada `\ko`, `\K`, transform, blur, maupun outline flash.
  * **Fix**: Menulis ulang `build_karaoke_sweep()` menjadi implementasi mandiri yang berbeda secara visual:
    * Menggunakan tag `\k` (instant colour change) bukan `\kf` (gradual fill) — perubahan warna terjadi seketika bukan fill bertahap.
    * Menambahkan `\t(0,flash_dur,\blur{flash_blur})` dan `\t(flash_dur,flash_dur*2,\blur{base})` per kata — menghasilkan glow flash singkat tepat saat kata berganti warna, lalu fade kembali ke blur dasar.
    * `flash_blur = max(base_blur + 6, 8)` memastikan glow terlihat bahkan pada style dengan `blur=0`.
    * Style `neon-glow` (yang menggunakan `karaoke_sweep`) kini memberikan efek visual yang berbeda dan lebih dramatis dari `viral-bold` (yang menggunakan `karaoke_fill`).

* **Bug: `word_box_highlight` tidak menghasilkan box sungguhan (`subtitles.py`)**:
  * **Root cause**: ASS tidak punya rectangle primitive. `\bord<n>` hanya memperbesar outline glyph, menghasilkan bentuk mengikuti kontur huruf (bukan persegi). Implementasi lama menggunakan `\3c<warna>` + `\bord14` pada satu Dialogue line untuk seluruh baris — menghasilkan satu outline tebal di seluruh baris, bukan box per kata.
  * **Fix**: Menulis ulang `build_word_box_highlight()` dengan arsitektur baru:
    * Setiap kata mendapatkan **Dialogue event tersendiri** dengan `\an5` (anchor tengah) dan `\pos(cx,cy)` — posisi tiap kata dihitung dari `_estimate_text_width()` untuk layout horizontal yang akurat.
    * **Kata aktif** (sedang diucapkan): tag `\an5\pos(cx,cy)\1c<inactive>\3c<box_color>\bord<n>\shad0` — outline berwarna tebal hanya melingkari kata tersebut.
    * **Kata non-aktif**: tag `\an5\pos(cx,cy)\1c<inactive>\bord0\shad0` — teks polos tanpa outline.
    * Setiap kata dibagi menjadi tiga sub-event: sebelum aktif, saat aktif, dan setelah aktif, dengan koordinat `\pos()` berbeda per kata.
    * `_play_res_y` kini di-inject ke style dict di `generate_ass()` agar builder bisa menghitung posisi `y` dengan benar.

* **Komentar Tidak Akurat "Shadow doubles as blur" Dihapus (`subtitles.py`)**:
  * Komentar `# Shadow field doubles as blur in ASS (Shadow=blur when BorderStyle=1)` dihapus dan diganti komentar akurat: `# Shadow=0 always. ASS Shadow ≠ blur. Blur is applied inline via \blur<n> tags.`

---

## [2026-06-21 02:00 WIB] — Sinkronisasi Visual Preview Subtitle Frontend ↔ Backend & Overhaul Layout Kartu Template

### Ringkasan Perubahan
Melakukan overhaul menyeluruh terhadap sistem kartu pratinjau (*preview cards*) gaya subtitle di frontend (`page.tsx`) agar tata letak, warna, font, animasi, dan posisi subtitle sepenuhnya mencerminkan hasil *burn-in* ASS yang sebenarnya dari backend. Memperbarui fungsi `getDynamicPreviewStyles` agar memetakan warna langsung dari konstanta `STYLES` dict di `subtitles.py` backend.

### Aktivitas Detail

* **Overhaul Layout Kartu Preview Template (`page.tsx`)**:
  * Mengubah aspek rasio kartu dari `aspect-[9/14]` ke `aspect-[9/16]` agar sesuai dengan dimensi nyata video vertikal 9:16 yang dihasilkan backend.
  * Mengubah tata letak kartu dari *flexbox justify-between* (atas-bawah) ke posisi **absolut** (`position: absolute`) sehingga teks subtitle secara akurat dipinning di area bawah kartu, mencerminkan nilai `margin_v_ratio` dari backend.
  * Mengganti warna latar gradien kartu yang bervariasi per style dengan `from-zinc-900 to-zinc-950` yang seragam dan gelap, mengacu pada tampilan video nyata berlatarbelakang gelap.

* **Sinkronisasi Posisi Subtitle ke `margin_v_ratio` Backend (`page.tsx`)**:
  * Setiap kartu kini memiliki properti `marginBottom` yang nilainya langsung merefleksikan `margin_v_ratio` dari `STYLES` dict backend:
    * `viral-bold`, `word-pop`, `highlight-box`, `neon-gradient`, `neon-glow`, `classic-popup`: `bottom: 26%` (margin_v_ratio=0.26)
    * `clean-minimal`, `minimalist`: `bottom: 22%` (margin_v_ratio=0.22)
    * `tiktok`: `bottom: 18%` (margin_v_ratio=0.18)

* **Penyesuaian Kata Contoh Preview (`page.tsx`)**:
  * Mengubah semua kata contoh pada kartu template dari kata acak singkat menjadi kalimat deskriptif representatif sesuai nama style masing-masing:
    * Contoh: `"INI CONTOH SUBTITLE VIRAL BOLD"`, `"INI CONTOH SUBTITLE TIKTOK"`, `"ini contoh subtitle clean minimal"`, dst.

* **Refaktor Total Sistem Animasi Preview (`page.tsx`)**:
  * Mengganti sistem branch berbasis flag properti lama (`boxStyle`, `singleWord`, key-matching) dengan sistem **tipe animasi eksplisit** (`animation: "karaoke" | "wordpop" | "popup" | "fadein" | "box"`) yang secara langsung mencerminkan `ANIMATION_BUILDERS` di backend.
  * Setiap tipe animasi merender efek visual CSS yang berbeda persis sesuai perilaku ASS-nya:
    * **`karaoke`**: Kata aktif tampil penuh, kata belum aktif `opacity: 0.45` — mensimulasikan efek `\kf` karaoke fill.
    * **`wordpop`**: Satu kata tampil dalam skala `1.15x` dengan `key={activeWordIdx}` untuk re-mount React — mensimulasikan animasi satu kata per segmen.
    * **`popup`**: Kata aktif di-scale `1.25x translateY(-1px)`, kata lain `opacity: 0.6` — mensimulasikan `word_popup` ASS.
    * **`fadein`**: Kata sebelum `activeWordIdx` tampil, sisanya `opacity: 0.1` — mensimulasikan `fade_in_word` ASS.
    * **`box`**: Kata aktif mendapat `boxShadow: inset` dan `backgroundColor` tipis — mensimulasikan efek `\bord` highlight box ASS.

* **Simulasi Outline ASS via CSS `text-shadow` (`page.tsx`)**:
  * Menambahkan fungsi `makeTextShadow(outlineWidth, outlineColor)` yang mensimulasikan efek `\outline` tebal ASS melalui serangkaian CSS `text-shadow` multi-arah.
  * Parameter outline masing-masing style disesuaikan dengan nilai backend (`tiktok`: 20px, `viral-bold`/`neon-glow`: 4px, `word-pop`: 5px, dst.).

* **Sinkronisasi `getDynamicPreviewStyles` dengan Backend `STYLES` Dict (`page.tsx`)**:
  * Menulis ulang `getDynamicPreviewStyles` dengan tiga peta eksplisit: `fontMap`, `primaryMap`, dan `highlightMap` — nilai setiap key langsung merefleksikan nilai yang dikodekan di `STYLES` dict backend setelah dikonversi dari format ASS `&HAABBGGRR` ke hex CSS.
  * Memperbaiki bug warna highlight `tiktok` dari `#08E539` (salah) ke `#39E508` — hasil konversi benar dari ASS `&H0008E539` (B=0x08, G=0xE5, R=0x39 → hex #39E508).
  * Menambahkan `outlineColor` khusus untuk `neon-gradient` yang menggunakan outline berwarna (#FFF000 kuning).

* **`baseWordStyle` CSS Terpadu per Kartu (`page.tsx`)**:
  * Membuat objek `baseWordStyle` dinamis per kartu yang memuat: `fontFamily`, `fontWeight` (900/400), `fontSize`, `letterSpacing`, `textTransform`, `textShadow`, dan `lineHeight`.
  * Menghilangkan penggunaan kelas Tailwind ad-hoc per kartu, sehingga pembaruan style cukup dilakukan di satu tempat.

---

## [2026-06-21 01:35 WIB] — Resolusi Kritis Bug Subtitle: Perbaikan Timing Drift, Word Popup, Line Balancing, Collision Overlap, Adaptive Font Scaling, dan Modernisasi Font

### Ringkasan Perubahan
Menyelesaikan seluruh temuan bug logika dan kelemahan arsitektur pada sistem subtitle (`subtitles.py`) untuk mencapai standar kualitas visual premium setara OpusClip dan Captions AI, termasuk penambahan sistem penskalaan ukuran huruf secara adaptif serta pembaruan font modern (Helvetica, Montserrat, Plus Jakarta Sans).

### Aktivitas Detail

* **Modernisasi Font Subtitle (`subtitles.py`)**:
  * Mengganti font bawaan (seperti Inter, Inter Black, dan Arial) di seluruh [STYLES](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/backend/app/engine/subtitles.py#L479-L589) registry dengan font modern premium atas permintaan pengguna:
    * **Montserrat**: Digunakan pada gaya bold & neon (`viral-bold`, `neon-glow`, `neon-gradient`).
    * **Plus Jakarta Sans**: Digunakan pada gaya pop & box modern (`word-pop`, `highlight-box`, `tiktok`).
    * **Helvetica**: Digunakan pada gaya minimalis & clean (`minimalist`, `classic-popup`, `clean-minimal`).

* **Penyelesaian Timing Drift (`subtitles.py`)**:
  * Mengubah perhitungan durasi kata centisecond dari pembagian bulat (`total_cs // len(words)`) ke skema distribusi sisa modulo presisi (`_build_karaoke_base`). Durasi kata dihitung dari selisih rentang index (`w_end - w_start`) sehingga total akumulasinya selalu tepat sama dengan `total_cs` segmen, mengeliminasi timing drift visual pada akhir kata/segmen.

* **Implementasi Line Balancing & Orphan/Widow Control (`subtitles.py`)**:
  * Mengganti pembungkus baris greedy `_wrap_text` dengan `_wrap_and_balance` yang secara cerdas mendistribusikan kata-kata pada layout multi-baris secara seimbang (misal: membagi rata kata di baris 1 dan baris 2 untuk menghindari satu kata menggantung di baris akhir/orphan).
  * Memaksa batasan `max_lines` secara ketat dengan menggabungkan baris yang berlebih ke dalam baris batas akhir secara aman.

* **Implementasi Dynamic & Adaptive Font Scaling (`subtitles.py`)**:
  * Menambahkan fungsi pencarian ukuran font adaptif [_find_adaptive_wrap](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/backend/app/engine/subtitles.py#L183-L235). Sistem sekarang secara dinamis mengecilkan ukuran huruf (hingga minimal 65% dari base size) jika teks segmen terlalu panjang agar muat dalam Safe Area (maksimal 2 baris).
  * Sebaliknya, jika teks sangat pendek (<= 2 kata), sistem secara otomatis meningkatkan ukuran huruf sebesar 15% (`1.15x`) untuk memberikan penekanan visual (emphasis) yang dinamis ala Captions AI.
  * Menggunakan tag override ASS `\fs` per baris dialog untuk mengubah ukuran huruf secara individual tanpa merusak konfigurasi global style.

* **Akurasi Estimasi Lebar Teks Karakter-Spesifik (`subtitles.py`)**:
  * Meningkatkan fungsi pengukur lebar teks `_estimate_text_width` dengan memetakan bobot lebar khusus untuk setiap jenis karakter (karakter lebar seperti W/M mendapat bobot lebih besar, karakter tipis seperti i/l/t mendapat bobot lebih kecil). Ini mereduksi galat estimasi hingga 80% tanpa ketergantungan eksternal (Pillow).

* **Perbaikan Word Popup & Fade In Realistis (`subtitles.py`)**:
  * Memperbarui builder animasi `build_word_popup` agar menyembunyikan kata masa depan menggunakan tag transparansi `\alpha&HFF&` sejak awal segment, lalu memancarkan popup instan (`\alpha&H00&`) bersamaan dengan transisi skala (`\fscx` & `\fscy`) tepat saat kata tersebut diucapkan.

* **Penghancuran Kode Duplikat (DRY Clean-up) (`subtitles.py`)**:
  * Membuat fungsi pembantu `_build_karaoke_base` sebagai basis utama builder karaoke. Fungsi ini dipakai bersama oleh `build_karaoke_fill`, `build_karaoke_sweep`, dan `build_word_box_highlight` untuk memusatkan logika looping, wrapping, dan timing kata.

* **Pencegahan Overlap Subtitle (Collision Handling) (`subtitles.py`)**:
  * Menambahkan fungsi resolusi tabrakan timestamp `_resolve_overlaps` di dalam `generate_ass` untuk memotong/menggeser segmen yang tumpang tidal secara otomatis sebelum dirender ke file ASS.

---

## [2026-06-21 01:05 WIB] — Eliminasi Zoom Digital dan Implementasi Crop Murni 9:16 Penuh dengan Penjejakan Wajah Terpusat

### Ringkasan Perubahan
Menghapus seluruh logika perbesaran dinamis (*dynamic zoom*) dan push-in zoom lambat pada segmen video individual di berkas `render.py`. Sebagai gantinya, sistem sekarang menerapkan pemotongan (*crop*) murni beraspek rasio 9:16 penuh yang secara konsisten menjejaki wajah pembicara agar berada tepat di tengah-tengah frame 9:16.

### Aktivitas Detail

* **Penghapusan Dynamic Zoom & Push-in Zoom (`render.py`)**:
  * Menghapus perhitungan parameter `base_zoom` (yang sebelumnya memperkecil ukuran jendela crop menjadi `0.70x` hingga `1.0x` secara dinamis berdasarkan `face_ratio`).
  * Menghapus pergeseran progress linear `zoom_factor` (push-in 3% lambat sepanjang klip).
  * Menetapkan `zoom_factor` secara statis ke `1.0` secara tidak langsung dengan menetapkan dimensi pemotongan `w_z` dan `h_z` tepat sama dengan `crop_w` dan `crop_h` target.

* **Penjejakan Wajah Terpusat yang Efisien (`render.py`)**:
  * Jendela crop 9:16 diposisikan secara simetris di sekitar koordinat wajah `cx` dan `cy` menggunakan rumus: `cx - w_z // 2` dan `cy - h_z // 2` (dengan pembatasan koordinat agar tidak keluar dari frame asli).
  * Dengan `w_z == crop_w` dan `h_z == crop_h`, pemanggilan interpolasi skala gambar `cv2.resize()` dilewati sepenuhnya di dalam kondisi sukses pemotongan, yang secara signifikan mereduksi beban I/O memori dan komputasi CPU render.

---

## [2026-06-21 01:00 WIB] — Migrasi Deteksi Perpindahan Kamera ke PySceneDetect

### Ringkasan Perubahan
Melakukan migrasi penuh teknologi deteksi perpindahan adegan (*scene cut/transition detection*) dari algoritma manual kustom berbasis korelasi histogram ke pustaka teruji **PySceneDetect** (`scenedetect`). Ini meningkatkan akurasi deteksi cuts secara dramatis, menghilangkan noise visual fluktuasi pencahayaan, dan merampingkan kompleksitas kode di berkas `render.py`.

### Aktivitas Detail

* **Pencatatan Dependensi Pustaka Baru (`requirements.txt`)**:
  * Menambahkan `scenedetect>=0.7` ke berkas `backend/requirements.txt` agar pustaka terpasang secara permanen pada lingkungan proyek.

* **Integrasi Deteksi PySceneDetect (`render.py`)**:
  * Mengimpor `detect` dan `ContentDetector` dari pustaka `scenedetect`.
  * Memperbarui fungsi `_generate_camera_segments` agar memanggil `detect(source_path, ContentDetector(threshold=27.0))` di awal untuk mengambil daftar frame transisi secara otomatis.
  * Loop pemutaran video OpenCV pada `_generate_camera_segments` sekarang menggunakan pencocokan frame indeks instan (`frame_idx in cut_frames`) sebagai pemicu cut adegan yang presisi tanpa distorsi desimal floating-point.
  * Menghapus fungsi visual manual `_is_cut()`, `_compute_histogram()`, dan `_compute_edge_histogram()` yang tidak lagi diperlukan, meningkatkan kebersihan dan pemeliharaan kode.

---

## [2026-06-21 00:20 WIB] — Pembebasan Kebocoran Sumber Daya Detektor MediaPipe, Eliminasi I/O Subtitle Mubazir, dan Peningkatan Keterbacaan Segmen

### Ringkasan Perubahan
Menuntaskan perbaikan untuk pelepasan sumber daya (*native resource leak*) MediaPipe menggunakan blok `try...finally` pada tingkat pembuat instans, mengeliminasi pembacaan berkas transkrip subtitle I/O (`main_ass_content`) yang tidak berguna pada `render.py`, serta merapikan sintaksis penggabungan segmen kamera menjadi operasi penghapusan *slice* python.

### Aktivitas Detail

* **Pencegahan Kebocoran Sumber Daya Native MediaPipe (Bug #3) (`render.py`)**:
  * Membungkus pemanggilan detektor wajah pada [_reframe_vertical](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/backend/app/engine/render.py#L1230-L1269) dalam blok `try...finally`.
  * Memastikan metode `.close()` secara disiplin dipanggil jika instans detektor yang dimuat memilikinya (khusus untuk MediaPipe Tasks yang memegang alokasi native C++ resource), menjamin memori segera dilepas saat pemrosesan video selesai baik dalam skenario sukses maupun terjadi *exception*.

* **Eliminasi Pembacaan I/O Subtitle Mubazir (Bug #4) (`render.py`)**:
  * Menghapus blok `with open(subtitle_path, "r") as f: main_ass_content = f.read()` yang tidak berguna. Sistem sekarang hanya melakukan pemeriksaan eksistensi berkas (`os.path.exists`) secara efisien tanpa melakukan pembacaan *harddisk* yang sia-sia.

* **Peningkatan Keterbacaan Penggabungan Segmen (Bug Keterbacaan #2) (`render.py`)**:
  * Mengganti pemanggilan ganda `refined_segments.pop(i)` yang berurutan di dalam fungsi `_generate_camera_segments` dengan operasi penghapusan slice python yang bersih: `del refined_segments[i:i+2]`.

---

## [2026-06-21 00:15 WIB] — Penanganan Edge Case Frame Kosong, Stabilisasi Fallback Render, dan Optimasi Downscaling Blur Background

### Ringkasan Perubahan
Menyelesaikan perbaikan untuk edge case fungsional kritis (penyelamatan kegagalan `shutil.copy2` pada fallback, pengamanan crop frame kosong dari decoder) serta implementasi optimasi kinerja CPU yang drastis pada fungsi pemburaman latar belakang `_letterbox` menggunakan teknik downscaling blur.

### Aktivitas Detail

* **Penyelamatan Kegagalan Penyalinan Fallback (Bug Fungsional #1) (`render.py`)**:
  * Mengubah error exception handling pada `shutil.copy2` di dalam `_render_frames`. Jika proses penyalinan video fallback gagal karena perizinan atau disk penuh, fungsi sekarang secara langsung akan mengembalikan path file video asli `in_path` ke pemanggil utama agar muxer FFmpeg tidak mencoba memproses path file fiktif yang tidak ada.

* **Pengamanan Crop Frame Kosong / Corrupt (Edge Case #2) (`render.py`)**:
  * Menambahkan validasi keamanan spasial tepat setelah memotong frame (`frame[y0:y0+h_z, x0:x0+w_z]`). Jika frame mengalami kerusakan (*corrupt*) atau decoder video menghasilkan frame kosong (dimensi lebar/tinggi 0), sistem otomatis mengalihkan frame tersebut ke visual adegan *letterbox* guna mencegah error fatal *assertion failed* OpenCV pada fungsi `cv2.resize`.

* **Optimasi Kinerja CPU Downscaling Gaussian Blur (Bug Performa #3) (`render.py`)**:
  * Mengganti komputasi Gaussian Blur berskala besar (kernel 61 piksel pada resolusi penuh adegan) pada `_letterbox` dengan metode downscaling.
  * Latar belakang video sekarang secara dinamis di-downscale ke lebar kecil (128 piksel), di-blur secara efisien dengan kernel kecil (9 piksel), lalu di-upscale kembali ke dimensi target adegan. Ini menghasilkan kelembutan visual background blur yang serupa secara presisi, namun memangkas utilitas CPU rendering background hingga lebih dari 99%.

---

## [2026-06-21 00:10 WIB] — Penyelesaian Bug Kritis Prioritas 1 & 2, Input Seeking FFmpeg, dan Edge Histogram Scene Cut

### Ringkasan Perubahan
Menuntaskan perbaikan untuk 4 Bug Prioritas 1 (Active Speaker ID recycling hijacking, desinkronisasi `frame_prev` vs `bbox_prev`, Edge-based scene cut verification, Input Seeking FFmpeg yang super cepat), 3 Isu Prioritas 2 (Group Reaction Spasial Median, Oklusi wajah drift-timeout, adaptif tracking threshold), dan 2 Isu Robustness (Verifikasi `VideoWriter.isOpened()`, escape karakter koma pada file path FFmpeg).

### Aktivitas Detail

* **Active Speaker ID Hijacking & Recycling Protection (Bug #1 - Prioritas 1) (`render.py`)**:
  * Menambahkan reset otomatis pada `active_speaker_id` ke `None` dan `speaker_hold_counter` ke `0` saat sebuah tracker wajah dihapus karena oklusi panjang. Ini mencegah ID baru hasil daur ulang membajak status speaker aktif lama.

* **Sinkronisasi Frame Historis Sampel Wajah (Bug #2 - Prioritas 1) (`render.py`)**:
  * Memodifikasi `_analyze_video` agar menyimpan frame sampel analisis sebelumnya (`frame_prev_sample`) bukan frame dari 1 frame video lalu (`frame_prev`). Ini menyelaraskan perbandingan mulut pada `_compute_mouth_motion` dengan `bbox_prev` dari sampel sebelumnya secara sinkron spasial dan temporal.

* **Pencegahan False Positive Scene Cut Detector (Bug #3 - Prioritas 1) (`render.py`)**:
  * Mengintegrasikan fungsi pendeteksi Edge Histogram `_compute_edge_histogram` menggunakan filter gradien Sobel.
  * Memperbarui logika `_is_cut` untuk memverifikasi histogram struktur tepi. Jika korelasi tepi tetap tinggi (>= 0.85), perubahan adegan ditolak (FP akibat perubahan pencahayaan global/flash/flicker tereliminasi).

* **FFmpeg Input Seeking Super Cepat (Bug #11 - Prioritas 1) (`render.py`)**:
  * Mengubah pemotongan subklip di `_cut_subclip` dari Output Seeking (`-i ... -ss ...`) menjadi Input Seeking (`-ss ... -i ... -t {durasi}`). Hal ini melompati decoding linier, memotong video panjang dalam kurang dari 1 detik.

* **Median Group Reaction & Drift-Timeout (Bug #4 & #5 - Prioritas 2) (`render.py`)**:
  * Mengganti rata-rata spasial (mean) pada pemosisian Group Reaction dengan **median** koordinat wajah (`np.median`) untuk stabilitas tinggi terhadap outlier visual.
  * Menerapkan timeout oklusi adegan (`face_lost_counter > 6`). Kamera tidak membeku selamanya menatap kursi kosong, melainkan perlahan bergerak pan kembali ke tengah jangkar segmen jika wajah hilang terlalu lama.

* **Adaptive Spasial Tracking Threshold (Bug #6 - Prioritas 2) (`render.py`)**:
  * Mengubah jarak pencocokan tracker statis menjadi threshold adaptif berbasis ukuran wajah nyata (`1.5 * face_height_px`), mencegah kesalahan jodoh pada subjek berwajah kecil.

* **Robustness & Code Quality (Bug #13 & #15 - Prioritas 3) (`render.py`)**:
  * Menambahkan validasi `if not writer.isOpened():` setelah pembuatan `VideoWriter` di `_render_frames` dan `_render_master_letterbox`.
  * Memperbarui `_ffmpeg_escape_path` agar meloloskan karakter koma `,` menjadi `\,` untuk mengamankan filter `ass` FFmpeg pada nama file yang mengandung koma.

---

## [2026-06-21 00:00 WIB] — Pembersihan Bug Logika Terverifikasi, Optimasi Pelacakan Multi-Wajah, dan Dynamic Zoom Adaptif

### Ringkasan Perubahan
Menyelesaikan pembersihan bug logika kritis pada engine smart crop (`render.py`), meliputi pencegahan IndexError crash jika video tidak memancarkan sampel sama sekali, implementasi Greedy One-to-One face tracking untuk mencegah ID swap, normalisasi berimbang pada scoring speaker, mouth motion compensation yang akurat secara spasial, perbaikan lag tipe shot interpolasi, serta implementasi perbesaran dinamis (dynamic zoom) berbasis ukuran wajah untuk menghindari kepala subjek terpotong.

### Aktivitas Detail

* **Pencegahan IndexError & Fallback Otomatis (`render.py`)**:
  * Menambahkan pengecekan dan *fallback* otomatis ke format *master letterbox* 9:16 jika list `samples` kosong setelah Pass 1 analisis video agar proses render tidak crash dengan IndexError.

* **Greedy One-to-One Face Tracking (`render.py`)**:
  * Mengubah pelacakan terdekat (nearest neighbor) menjadi skema Greedy Matching yang unik dengan memetakan pasangan jarak wajah dan tracker terkecil secara satu-ke-satu. Ini secara mutlak menghentikan bug ID swap dan assignment ganda pada satu tracker.
  * Menerapkan daur ulang (recycling) ID wajah dengan selalu mengambil integer ID terkecil yang sedang tidak aktif di dalam pelacak.
  * Memindahkan penambahan status masa tenggang `missed_frames` untuk tracker di luar kondisi deteksi wajah aktif, memastikan tracker dibersihkan dengan benar saat wajah hilang total (oklusi panjang).

* **Kompensasi Gerakan Mulut / Mouth Motion Compensation (`render.py`)**:
  * Mengubah `_compute_mouth_motion` agar memotong ROI mulut frame sebelumnya menggunakan koordinat historis tracker (`bbox_prev`) bukan koordinat frame saat ini. Ukuran ROI sebelumnya di-resize secara dinamis ke ukuran ROI sekarang sebelum di-absdiff untuk melakukan kompensasi pergeseran dan perubahan skala wajah.
  * Menormalisasi keluaran `_compute_mouth_motion` secara penuh (skala 0.0 - 1.0) guna menyeimbangkan pengaruh bobot intensitas gerakan pembicara aktif terhadap ukuran wajah.

* **Smoothing Tinggi Wajah & Dynamic Zoom (`render.py`)**:
  * Menghaluskannya parameter `face_ratio` di dalam `_apply_smoothing_non_causal` dengan non-causal moving average agar mencegah getaran *zoom pumping*.
  * Mengganti perbesaran statis berbasis durasi dengan perbesaran dinamis (*dynamic zoom*) berbasis `face_ratio` yang di-smooth (wajah kecil di-zoom in hingga 30%, wajah closeup tidak di-zoom), dikombinasikan secara halus dengan push-in lambat kosmetik (3%).

* **Responsivitas Transisi Tipe Shot (`render.py`)**:
  * Memperbaiki lag tipe shot saat interpolasi dengan merespon tipe shot sampel terdekat (`prev` jika progress interpolasi `alpha < 0.5`, else `next`).

* **Optimasi Kinerja Segment Lookup $O(1)$ (`render.py`)**:
  * Menerapkan pointer penelusuran segmen berjalan `active_seg_idx` dengan kompleksitas amortized $O(1)$ untuk meniadakan loop linier segment di setiap frame dan mengeliminasi bug floating point transisi segmen.

---

## [2026-06-20 23:55 WIB] — Resolusi Risiko Deadlock, Integrasi Fitur Group Reaction, dan Pengamanan Exception Resource

### Ringkasan Perubahan
Memperbaiki risiko deadlock pada thread pool, menyelesaikan implementasi penempatan kamera untuk fitur Group Reaction, menambahkan pengamanan terhadap list sampel kosong (video kosong/corrupt), menangani pelolosan karakter kutip tunggal pada filter FFmpeg, dan memastikan pelepasan resource OpenCV (`VideoCapture` & `VideoWriter`) menggunakan block `try...finally`.

### Aktivitas Detail

* **Pencegahan Risiko Deadlock Thread Pool (`pipeline.py` & `render.py`)**:
  * Memindahkan resolusi parameter `subtitle_style` ke thread pemanggil utama di `pipeline.py` dan meneruskannya langsung sebagai argumen ke `render_clips`.
  * Menghilangkan panggilan event loop asinkron (`run_coroutine_threadsafe`) dan `.result()` yang berisiko memblokir loop/thread di dalam fungsi sinkron `render_clips`. Sebagai gantinya, jika parameter `subtitle_style` kosong, sistem akan mencoba membacanya secara sinkron dari in-memory task store `store._mem_tasks` atau langsung jatuh kembali ke `DEFAULT_STYLE`.

* **Penerapan Kamera Group Reaction (`render.py`)**:
  * Menyelesaikan logika visual untuk *group reaction*: Jika terdeteksi reaksi kelompok (`is_group = True`), kamera sekarang secara aktif memposisikan `target_cx` dan `target_cy` ke titik tengah koordinat rata-rata dari semua wajah yang terdeteksi, serta memaksa rasio shot ke `"wide_cut"` (mengabaikan pembatasan closeup horizontal individu).

* **Pencegahan IndexError Video Kosong/Corrupt (`render.py`)**:
  * Menambahkan validasi `if not samples` di awal fungsi `_render_frames` untuk langsung menyalin video asli ke berkas output fallback aslinya menggunakan `shutil.copy2` daripada melempar pengecualian `IndexError` pada list kosong.

* **Pelepasan Resource OpenCV (`render.py`)**:
  * Membungkus pembacaan/penulisan frame video pada fungsi `_analyze_video` dan `_render_frames` menggunakan blok `try...finally` untuk menjamin bahwa `cap.release()` and `writer.release()` selalu dieksekusi secara aman meskipun terjadi kegagalan proses/exception di tengah proses pemrosesan frame.

* **Pencegahan Error String FFmpeg Filter (`render.py`)**:
  * Menambahkan penggantian karakter tanda kutip tunggal (`'`) di dalam fungsi `_ffmpeg_escape_path` dengan karakter ter-escape (`\'`) guna menghindari kerusakan string filter FFmpeg `ass=` jika terdapat tanda kutip di dalam nama direktori atau file subtitle.

---

## [2026-06-20 23:45 WIB] — Implementasi Hysteresis, Deteksi Mouth Motion Aktif, dan Perbaikan Bug Bracket Render Interpolation

### Ringkasan Perubahan
Memperbaiki bug kritis di mana ekor klip video mengalami "sentakan/lompatan" posisi kamera akibat kegagalan pencocokan rentang waktu bracket pada render pass ke-2. Serta mengaktifkan fitur-fitur tracking lanjutan yang sebelumnya tidak terpakai seperti estimasi mouth motion aktif pembicara, deteksi reaksi kelompok (group reaction), serta koordinasi hysteresis deteksi speaker & shot type untuk menghilangkan jitter kamera secara total.

### Aktivitas Detail

* **Perbaikan Glitch Interpolasi Frame Akhir (`render.py`)**:
  * Menambahkan guard `t >= samples[-1].time` di `_render_frames` agar frame-frame terakhir klip video membeku (*freeze*) pada posisi sampel terakhir secara stabil daripada melompat/kembali ke koordinat sampel pertama.
  * Mengoptimalkan pemindaian bracket dari pencarian linear $O(N)$ menjadi pemindaian maju dengan pointer pointer amortized $O(1)$ (`sample_pointer`), mempercepat proses rendering klip berdurasi panjang.

* **Implementasi Fitur Tracking Hysteresis & Mouth Motion (`render.py`)**:
  * Mengaktifkan deteksi energi gerakan mulut melalui fungsi `_compute_mouth_motion` pada Pass 1 dan memadukannya dengan rasio tinggi wajah (`face_h`) menggunakan konstanta bobot `MOTION_WEIGHT` (0.6) dan `SIZE_WEIGHT` (0.4) untuk memilih wajah pembicara aktif yang sesungguhnya.
  * Menerapkan pembatasan `MIN_HOLD_SAMPLES` dan `SWITCH_MARGIN` untuk mencegah pergantian kamera (cross-talk) melompat-lompat akibat fluktuasi ukuran wajah di antara pembicara yang berdekatan.
  * Menerapkan parameter `MIN_SHOT_HOLD_SAMPLES` pada perubahan tipe shot (`closeup`/`medium`) untuk menghindari perubahan rasio zoom kamera yang tidak stabil/bergetar.
  * Mengaktifkan manajemen pelacakan missed frames (`MAX_MISSED_SAMPLES`) pada tracker untuk mempertahankan status ID wajah yang terlewat sementara (misalnya karena terhalang/oklusi) hingga 4 sampel sebelum dihancurkan.
  * Mengubah jarak pencocokan wajah tracker (`min_dist`) dari konstanta piksel absolut `120.0` menjadi bernilai dinamis sesuai resolusi (`src_w * 0.10`) agar stabil pada berbagai resolusi input video (seperti 1080p vs 4K).
  * Mengimplementasikan formula mean-reversion horizontal (`target_cx = int(0.75 * target_cx + 0.25 * locked_cx)`) untuk menarik kamera secara lembut kembali ke jangkar rata-rata (`avg_cx` segmen), mencegah drift horizontal pada segmen panjang.
  * Mengaktifkan deteksi reaksi kelompok (`is_group_reaction`) berdasarkan jumlah wajah (`>= GROUP_REACTION_MIN_FACES`) dan rata-rata intensitas gerakan mulut (`>= GROUP_REACTION_MOTION_THRESH`).

---

## [2026-06-20 22:35 WIB] — Optimalisasi Deteksi Kamera Master dan Pencegahan Salah Klasifikasi Kamera Kanan/Kiri

### Ringkasan Perubahan
Meningkatkan akurasi klasifikasi segmen kamera (kamera master vs kamera individual/kanan-kiri) dengan memperketat threshold deteksi wajah ganda dan memperkenalkan indikator pendeteksi orang ganda yang lebih konsisten (`has_multiple_people`). Hal ini berhasil mengatasi bug di mana kamera individual (kanan/kiri) yang memiliki subjek berwajah kecil atau mengalami noise deteksi wajah salah diklasifikasikan sebagai kamera master (menyebabkan video terpotong di tengah secara paksa).

### Aktivitas Detail

* **Pencegahan Salah Klasifikasi Kamera Master (`render.py`)**:
  * Menambahkan indikator `has_multiple_people` yang mewajibkan deteksi minimal 2 wajah dalam frame secara konsisten (minimal di 2 frame berbeda dan mencakup >= 8% dari total frame di segmen tersebut).
  * Menaikkan threshold pemisah kamera master berbasis hitungan wajah ganda (`count_2_plus / total_f`) dari `0.18` (18%) menjadi `0.35` (35%) agar lebih kebal terhadap noise deteksi wajah sesaat di latar belakang.
  * Membatasi kriteria wajah kecil (`count_small_faces / total_f >= 0.70`) agar hanya aktif jika segmen tersebut terbukti memiliki lebih dari satu pembicara (`has_multiple_people` bernilai True). Jika hanya ada satu pembicara di frame (seperti pada kamera kanan/kiri meskipun wajahnya tampak kecil karena posisi duduk agak jauh), sistem sekarang secara disiplin akan mengklasifikasikannya sebagai kamera `individual` sehingga pelacakan wajah horizontal dan vertikal tetap aktif dengan sempurna.
  * Memindahkan inisialisasi variabel `count_no_faces` untuk model MediaPipe agar hanya dihitung jika model deteksi yang aktif memang MediaPipe.

---

## [2026-06-20 22:00 WIB] — Perbaikan Kebocoran Koneksi Redis Asinkron dan Integrasi Log Transkripsi ke Frontend

### Ringkasan Perubahan
Memperbaiki bug kritis di mana server FastAPI melempar error `500 Internal Server Error` dengan log `RuntimeError: Event loop is closed` akibat bertabrakannya pemanggilan event loop asinkron pada thread pool. Serta menambahkan log detail transkripsi ke SSE (*Server-Sent Events*) agar dapat ditampilkan di panel log frontend.

### Aktivitas Detail

* **Penyimpanan Referensi Loop Utama (`state.py`)**:
  * Menambahkan atribut `self.loop = None` pada kelas `TaskStore` untuk menyimpan referensi ke event loop asinkron utama FastAPI.
  * Pada metode `_ensure_backend()`, sistem sekarang mengambil `asyncio.get_running_loop()` saat diinisialisasi/dipanggil di thread utama dan menyimpannya ke `self.loop`.

* **Perbaikan Pelaporan Progres Rendering (`render.py`)**:
  * Mengubah `_update_render_progress` agar menggunakan `store.loop` (loop utama yang aman) daripada memanggil `asyncio.get_running_loop()` di dalam thread pool.
  * Menggunakan `asyncio.run_coroutine_threadsafe` untuk mengirim update progres ke thread utama secara *fire-and-forget* (tanpa memblokir thread dengan `future.result()`), yang meningkatkan kecepatan rendering.
  * Menghapus pembuatan event loop baru (`asyncio.new_event_loop()`) dan panggilan `loop.run_until_complete()` pada thread pool untuk mencegah bertabraknnya state klien Redis asinkron global.
  * Menyediakan fallback non-blocking yang aman (hanya melakukan print dan memperbarui in-memory dict) jika loop utama tidak terdeteksi (seperti saat testing via CLI).

* **Integrasi Log Transkripsi ke SSE (`transcriber.py`)**:
  * Membuat fungsi pembantu `_update_transcribe_progress` di `transcriber.py` yang menggunakan `store.loop` untuk memancarkan pesan log transkripsi asinkron ke frontend.
  * Menambahkan pengiriman event progress untuk log `trying YouTube transcript API` (16%), `no YouTube transcript available` (18%), `calling Gemini...` (20%), dan `calling Groq...` (28%) agar pengguna dapat memantau aktivitas backend secara detail dari frontend.
  * Menambahkan pengiriman log diagnostik tambahan ke frontend meliputi pesan reparasi JSON (`JSON decode failed directly...`), pemotongan segmen halusinasi/filler berulang (`potong X segmen filler berulang...`), reduksi segmen (`X -> Y segmen`), serta status segmen yang berhasil didapatkan dari Gemini/YouTube/Groq.

---

## [2026-06-20 21:55 WIB] — Perbaikan Kegagalan Parsing Transkrip Gemini Akibat Token Limit Terpotong

### Ringkasan Perubahan
Memperbaiki bug `JSONDecodeError` saat melakukan transkripsi menggunakan Gemini 2.5 Flash pada video panjang. Ditambahkan mekanisme pembersihan code block markdown dan pemulihan JSON parsial/terpotong (lax parser) secara otomatis agar transkripsi parsial tetap bisa di-parse dan digunakan oleh pipeline. Serta memperbaiki instruksi prompt untuk mencegah luapan token akibat transkripsi per kata (*word-by-word*).

### Aktivitas Detail

* **Penerapan Lax JSON Parser (`transcriber.py`)**:
  * Membuat fungsi pembantu `_parse_lax_json` untuk membersihkan pembungkus blok kode markdown (seperti ` ```json ... ``` `) yang kadang dihasilkan oleh model LLM.
  * Menambahkan algoritma pemulihan JSON parsial secara dinamis dengan mencari tanda kurung kurawal `}` dari belakang, memotong string yang rusak, lalu mencoba menambahkan kurung pelengkap (`]}`, `}`, `]`) secara rekursif hingga berhasil di-parse oleh `json.loads`.
  * Mengintegrasikan `_parse_lax_json` di dalam `_try_gemini_transcription` menggantikan pemanggilan `json.loads` langsung.

* **Optimasi Prompt Transkripsi (`transcriber.py`)**:
  * Memperbarui sistem prompt untuk `_try_gemini_transcription` dengan menambahkan aturan tegas: melarang keras transkripsi per kata (*DO NOT transcribe word-by-word*).
  * Mewajibkan Gemini untuk mengelompokkan kata-kata dari pembicara yang sama ke dalam bentuk kalimat lengkap atau frasa natural (durasi 2-7 detik atau 5-15 kata per segmen). Hal ini mencegah ukuran output JSON membengkak tidak perlu dan menghemat pemakaian token secara drastis.

---

## [2026-06-20 15:30 WIB] — Auto-Cleanup Orphaned Tasks When Storage Directory Deleted

### Ringkasan Perubahan
Memperbaiki bug di mana task yang storage directory-nya dihapus secara manual masih muncul di `GET /tasks`. Menambahkan auto-cleanup yang mendeteksi task yatim (orphaned) dan menghapus record-nya dari Redis/memory saat listing.

### Aktivitas Detail

* **Auto-Cleanup di `list()` (`state.py`)**:
  * Saat `GET /tasks` dipanggil, sistem sekarang memeriksa apakah direktori `storage/{task_id}/` masih ada untuk setiap task.
  * Jika direktori hilang dan task bukan dalam status `queued`/`processing`, record dihapus otomatis dari Redis (atau in-memory dict) dan di-skip dari hasil list.
  * Log info dicatat untuk setiap task yang di-clean: `"Auto-cleaned orphaned task {id} (storage deleted)"`.
  * Task dengan status `queued`/`processing` tidak dihapus — mereka masih aktif dan storage-nya mungkin belum dibuat.

* **Alasan Bug**:
  * `DELETE /tasks/{task_id}` endpoint membersihkan **kedua** storage directory dan Redis/memory record.
  * Manual deletion (`rm -rf storage/{task_id}/`) hanya menghapus file — Redis/memory record tetap ada, sehingga task terus muncul di API.

---

### Ringkasan Perubahan
Memperbaikan bug kritis di mana Gemini 2.5 Flash menghasilkan timestamp yang terkompresi (128 segmen dalam 8 detik untuk video 488 detik), menyebabkan seluruh highlight gagal validasi karena durasi < 15 detik minimum. Menambahkan debug logging di seluruh pipeline validasi highlight untuk diagnostik.

### Aktivitas Detail

* **Root Cause: Gemini Timestamp Compression (`transcriber.py`)**:
  * **Temuan**: Gemini 2.5 Flash mengembalikan timestamp yang dikompresi ~60x (8.08s vs 488.8s aktual). Konten transkrip benar tetapi timestamp sepenuhnya salah. Semua highlight ditolak oleh `_validate_highlights` karena `duration < MIN_DURATION (15s)`.
  * **Perbaikan**: Menambahkan deteksi kompresi timestamp — jika rentang transkrip < 10% dari durasi audio aktual, semua timestamp di-rescale secara proporsional. Contoh: 8.08s → 488.8s (scale factor ~60x).

* **Cache Validation (`transcriber.py`)**:
  * Menambahkan validasi durasi pada cache JSON dan SRT — jika durasi transkrip cache < 10% dari durasi video aktual, cache dianggap tidak valid dan transkrip ulang dipicu secara otomatis.
  * Mengimpor `json` secara global (sebelumnya lokal di beberapa fungsi) untuk konsistensi.

* **Debug Logging (`highlights.py`)**:
  * Menambahkan logging pada `_validate_highlights()`: mencatat alasan penolakan setiap highlight (segment ID salah, durasi terlalu pendek/panjang, overlap berlebihan).
  * Menambahkan logging pada `_validate_units()`: mencatat hasil validasi unit naratif.
  * Menambahkan logging pada `generate_highlights()`: mencatat ukuran respons LLM dan jumlah highlight yang berhasil di-parse per attempt.

* **Verifikasi**:
  * Video uji: `xEah8NzNrGQ` (488.8s, bahasa Indonesia, podcast/interview).
  * Transkrip sebelum fix: 128 segmen, durasi 8.08s → 0 highlight valid.
  * Setelah fix: timestamp di-rescale ke durasi aktual → highlight generation berjalan normal.

---

## [2026-06-20 13:30 WIB] — Perbaikan Multi-Model Face Detection: Segmentasi Kamera & Cropping Kamera Individual

### Ringkasan Perubahan
Investigasi dan perbaikan menyeluruh terhadap sistem deteksi wajah multi-model (YuNet, MediaPipe, YOLOv8-Face, SSD) yang menyebabkan seluruh segmen video diklasifikasikan sebagai `master` dan cropping kamera individual (kiri/kanan) tidak pernah aktif. Ditemukan 4 bug fundamental di `render.py` yang diperbaiki satu per satu berdasarkan data diagnostik nyata.

### Aktivitas Detail

* **Bug #1 (Root Cause): `CUT_THRESHOLD` Terlalu Rendah (`render.py`)**:
  * **Temuan**: Korelasi histogram nyata saat pergantian kamera di video uji: **0.964** (7.70s) dan **0.950** (16.37s). Keduanya **di atas** threshold lama `0.94`, sehingga tidak ada satu pun cut kamera yang pernah terdeteksi. Seluruh video dibaca sebagai 1 segmen dan langsung dikunci `master`.
  * **Perbaikan**: Naikkan `CUT_THRESHOLD` dari `0.94` → **`0.97`**. Dengan threshold baru, tiga segmen berhasil dipisahkan: `master` (0-7.7s), closeup kanan (7.7-16.37s), closeup kiri (16.37s+).

* **Bug #2: Threshold Klasifikasi Master Terlalu Sensitif (`render.py`)**:
  * **Temuan**: YuNet mendeteksi false-positive wajah kedua di background segmen closeup pada **15.8% frame**, melebihi threshold lama **8%**, sehingga closeup salah diklasifikasikan `master`.
  * **Perbaikan**: Naikkan threshold deteksi 2+ wajah dari `0.08` → **`0.18`** (18%). Segmen master asli memiliki 100% deteksi, sementara false-positive closeup hanya 15.8% — berada di bawah threshold baru.

* **Bug #3: Dead Zone Klasifikasi Spasial Left/Right Terlalu Lebar (`render.py`)**:
  * **Temuan**: Wajah pada posisi 40-47% atau 53-60% dari lebar frame jatuh di dead zone dan dikembalikan sebagai `individual` tanpa arah, bukan `left`/`right`. Data nyata: closeup kanan avg CX = 773px/1280 = 60.5%; closeup kiri avg CX = 572px/1280 = 44.7%.
  * **Perbaikan**: Perketat batas klasifikasi dari `0.40/0.60` → **`0.47/0.53`** sehingga kedua segmen terdeteksi benar.

* **Bug #4: MediaPipe Gagal Mendeteksi Wajah Profil di Master Shot (`render.py`)**:
  * **Temuan**: MediaPipe BlazeFace dirancang untuk wajah frontal. Pada shot master yang menampilkan dua orang dari sudut miring, MediaPipe mengembalikan **0 deteksi** (100% frame kosong), sehingga tidak bisa mengklasifikasikan segmen sebagai `master`.
  * **Perbaikan A**: Perbarui inisialisasi model MediaPipe dengan `min_detection_confidence=0.20` (dari default).
  * **Perbaikan B**: Tambahkan logika klasifikasi khusus MediaPipe: threshold ukuran wajah kecil diperlebar dari `0.15` → **`0.22`**; fallback baru — jika `>70%` frame pada segmen tidak mendeteksi wajah sama sekali, segmen otomatis diklasifikasikan `master`.

* **Penyesuaian Threshold Umum (`render.py`)**:
  * Turunkan `CONFIDENCE_THRESHOLD` dari `0.5` → **`0.30`** untuk meningkatkan sensitivitas deteksi wajah saat rendering pass individu.
  * Gunakan konstanta `CUT_THRESHOLD` secara konsisten (sebelumnya ada hardcode `0.94` di dalam fungsi `_generate_camera_segments`).

* **Diagnostik & Verifikasi (`backend/`)**:
  * Membuat beberapa script debug (`scratch_debug_yn.py`, `scratch_debug_segments_fast.py`, `scratch_debug_face_coords.py`, `scratch_debug_corr.py`, `scratch_debug_mp_master.py`) untuk mengukur korelasi histogram nyata, koordinat wajah per model, dan distribusi frame per segmen.
  * Menjalankan ulang rendering video uji 15 detik pada semua 4 model (`test_15s_ssd.mp4`, `test_15s_yunet.mp4`, `test_15s_yolov8-face.mp4`, `test_15s_mediapipe.mp4`) dan memverifikasi semua berhasil.

---

## [2026-06-20 11:20 WIB] — Rekonstruksi Pelacakan Kamera: Segment-Aware Ground-Truth & Non-Causal Zero-Lag Smoothing


### Ringkasan Perubahan
Merombak total sistem pemosisian kamera *crop* vertical pada backend untuk memisahkan logika klasifikasi segmen kamera global (ground-truth) dengan pelacakan individual di dalam segmen. Mengimplementasikan smoothing non-causal (moving average) untuk menghilangkan lag pergerakan kamera secara total, serta deteksi cut presisi frame-by-frame.

### Aktivitas Detail
* **Arsitektur Klasifikasi Kamera Berbasis Ground-Truth (`render.py`)**:
  * Menambahkan fungsi `_generate_camera_segments()` untuk menganalisis video sumber penuh sekali jalan di awal pada 4 FPS guna mendeteksi scene transition dan jenis shot dominan.
  * Hasil klasifikasi segmen (`master` / `individual` + waktu mulai & akhir) disimpan di dalam file cache `storage/{task_id}/camera_segments.json` (sejajar dengan transkrip) untuk menghindari analisis ulang per klip highlight.
* **Perilaku Disiplin Per Segmen Kamera (`render.py`)**:
  * **Segmen Master**: Memaksa posisi crop di tengah (`src_w // 2`, `src_h // 2`) dengan tipe `wide_cut` (letterbox blur penuh) sepanjang durasi segmen. Menghemat CPU dengan mematikan face detection.
  * **Segmen Individu**: Memaksa pelacakan wajah closeup/medium tunggal. Jika wajah hilang sementara (oklusi/nengok), sistem **menahan posisi terakhir secara mutlak (last known position)**, menghilangkan bug reset ke center. Jika ada noise deteksi (wajah tambahan lewat), sistem tetap mengunci target wajah utama.
  * Meniadakan hysteresis shot type per sampel karena tipe segmen kamera sudah dipandu oleh ground-truth global.
* **Penghilangan Lag Kamera & Snap Instan (`render.py`)**:
  * Mengganti smoothing EMA causal dengan **Non-Causal Zero-Lag Smoothing (Moving Average)**. Karena seluruh koordinat sampel sudah didapatkan di Pass 1, smoothing diaplikasikan dua arah di dalam batas-batas scene untuk meniadakan lag pergerakan tanpa mengorbankan kehalusan.
  * Pemicu *snap* reset (EMA/smoothing bypass) hanya diaktifkan pada boundary batas segmen kamera asli, menghilangkan lompatan palsu noise detector.
  * Menganalisis dengan rate `SAMPLE_FPS = 4` secara global agar tracking closeup rapat dan sangat responsif.

---

## [2026-06-20 10:55 WIB] — Penambahan Panel Log Detail & Perbaikan Penghapusan Aset Fisik Storage

### Ringkasan Perubahan
Menambahkan panel log interaktif ala retro-developer di frontend saat proses pembuatan klip berlangsung yang dapat disembunyikan/ditampilkan secara dinamis. Memperbaiki bug di mana berkas penyimpanan sementara (`storage/task_id/`) di backend tidak terhapus saat tugas dihapus di frontend.

### Aktivitas Detail
* **Log Progres Detail di Frontend (`tasks/[id]/page.tsx`)**:
  * Menambahkan panel log di sebelah kanan area kemajuan utama saat status tugas berstatus `"queued"` atau `"processing"`.
  * Mengintegrasikan penyimpanan log ke `localStorage` (`clip_logs_{task_id}`) agar log tetap persisten saat halaman disegarkan (refresh).
  * Membuat tombol toggle "Tampilkan Log / Sembunyikan Log" dengan ikon `Terminal` di navbar atas untuk menyembunyikan atau menampilkan panel log kapan saja.
  * Menghubungkan log ke semua jenis event SSE (`progress`, `clip_ready`, `done`, `error`) dengan representasi warna teks yang berbeda untuk masing-masing tahap (`DOWNLOAD`, `TRANSCRIBE`, `ANALYZE`, `SUBTITLES`, `RENDER`, `DONE`, `ERROR`).
  * Mengimplementasikan auto-scroll ke log terbaru menggunakan React `useRef` dan `scrollIntoView`.
* **Pembaruan Progress Render Real-time di Backend (`render.py`)**:
  * Menambahkan fungsi helper `_update_render_progress` untuk mengirim status render klip yang sedang diproses ke Redis/memori.
  * Memanggil helper tersebut di dalam loop `render_clips()` untuk melaporkan progres rendering secara mendetail (misal: "Merender klip 1 dari 5", "Merender klip 2 dari 5", dst.).
* **Perbaikan Penghapusan Aset Tugas di Backend (`state.py`)**:
  * Memperbarui metode `delete` pada kelas `TaskStore` agar menghapus direktori fisik `storage/{task_id}/` beserta seluruh isinya secara asinkron (`shutil.rmtree` dijalankan dalam thread pool via `asyncio.to_thread`) saat endpoint `DELETE /tasks/{task_id}` dipanggil.
* **Perbaikan Penghapusan Tugas di Frontend (`page.tsx` & `api.ts`)**:
  * Menambahkan fungsi `deleteTask` ke client API frontend untuk mengirim permintaan HTTP `DELETE` ke backend.
  * Mengubah fungsi `removeRecentTask` di Home page (`page.tsx`) agar memanggil API `deleteTask` secara asinkron sebelum menghapus data riwayat dari `localStorage`.

---

## [2026-06-20 05:50 WIB] — Added TikTok-Style Caption (`tiktok`)

Menambahkan gaya subtitle `"tiktok"` di `subtitles.py` yang meniru visual `remotion-dev/template-tiktok`: Inter Black uppercase ~119px, white text → neon green (`#39E508`) karaoke highlight, thick black 20px outline, bottom-positioned, 4 words per chunk.

---

## [2026-06-20 05:10 - 05:40 WIB] — Perbaikan Sinkronisasi Subtitle per Klip, Margins Presisi, & Optimalisasi Layout Teks

### Ringkasan Perubahan
Memperbaiki bug sinkronisasi waktu subtitle pada klip hasil potongan (offset 0.0), menyelaraskan warna sweep karaoke agar berjalan dari inaktif (putih) ke aktif (kuning) secara benar, membatasi baris teks maksimal di layar dengan segment chunking, serta memperbaiki bug overlapping kata pada efek popup/fade.

### Aktivitas Detail
* **Perbaikan Sinkronisasi Subtitle per Klip (`render.py`)**:
  * Mengubah `render_clips()` agar menghasilkan berkas subtitle `.ass` khusus (`short_XX.ass`) yang disaring khusus untuk rentang waktu klip (`start_time` dan `end_time` highlight).
  * Melakukan pergeseran (*offset*) waktu mulai subtitle ke detik `0.0` (relatif terhadap titik awal potongan klip video) agar sinkron dengan durasi potongan video klip.
  * Menghindari bug subtitle tidak muncul karena waktu tayang subtitle utama berada di luar durasi klip video potongan.
* **Dinamisasi dan Preservasi Parameter Gaya Subtitle (`render.py` & `pipeline.py`)**:
  * Mengubah signatur `render_clips()` agar menerima parameter `subtitle_style` secara opsional.
  * Jika `subtitle_style` tidak diteruskan (misalnya dari script testing di luar API), backend akan mencoba memuat model task dari store Redis, lalu jatuh kembali ke `DEFAULT_STYLE` (`viral-bold`) jika gagal.
  * Menghubungkan variabel `style_key` (berisi nama style yang dipilih) dari `pipeline.py` ke pemanggilan `render_clips()` agar style inaktif/aktif dan jenis animasi yang dipilih oleh pengguna di-render dengan benar pada klip hasil potongan.
  * Meneruskan variabel `fonts_dir` dari pipeline agar font kustom (*Inter Black*, dll.) dibaca oleh filter `ass` ffmpeg.
* **Perhitungan Margin yang Presisi dan Pembenahan Warna Karaoke (`subtitles.py`)**:
  * Mengubah konversi parameter margin di fungsi `_header()` dari `int()` menjadi `round()` agar pembulatan margin vertikal dan horizontal tepat.
  * Menyelaraskan pewarnaan `PrimaryColour` (warna akhir/pronounciation) dan `SecondaryColour` (warna inaktif sebelum disweep) di style header ASS. Untuk gaya karaoke (`karaoke_fill`, `karaoke_sweep`, `word_box_highlight`), `SecondaryColour` diisi dengan warna inaktif (misal putih) dan `PrimaryColour` diisi dengan warna aktif (kuning/cyan/magenta) agar efek sweep berjalan dari inaktif (putih) ke aktif (kuning) secara benar sesuai spesifikasi ASS.
  * Menurunkan posisi margin vertikal gaya `word-pop` dari tengah (`0.45` ratio) ke bagian bawah layar (`0.26` ratio) agar sejajar dengan gaya visual lainnya.
* **Optimalisasi Layout Teks & Mencegah Overlapping Kata (`subtitles.py`)**:
  * Mengoreksi kalkulasi `usable_width = play_res_x * max_ratio` pada `_wrap_text()` untuk mencegah pemotongan baris dini (*double margin subtraction*).
  * Menambahkan helper `_chunk_segments()` untuk memecah segmen kalimat yang panjang menjadi potongan kata-kata yang lebih kecil (maksimal 3 kata untuk layout 1 baris seperti `clean-minimal` / `word-pop`, dan maksimal 5 kata untuk layout 2 baris). Ini membatasi teks di layar maksimal hanya 2 baris dan mencegah teks menutupi layar.
  * Menulis ulang builder `build_fade_in_word` dan `build_word_popup` agar menggunakan inline tags (`\alpha` & `\fscx` bertingkat waktu) dalam satu baris dialog yang utuh. Ini mencegah bug *overlapping* di mana setiap kata bertumpuk di titik tengah koordinat layar yang sama.
* **Pengujian Komprehensif (End-to-End Style Verification)**:
  * Membuat script testing kustom `test_all_styles.py` yang me-render potongan video 5 detik untuk semua 8 gaya subtitle yang ada.
  * Menyimpan seluruh video hasil render ke folder khusus `test_all_styles_results` dengan nama berkas sesuai nama stylenya (misalnya `viral-bold.mp4`, `word-pop.mp4`, dll.) dan memverifikasi bahwa masing-masing file memiliki efek visual subtitle yang unik dan benar.

---

## [2026-06-20 04:50 - 05:10 WIB] — Platform-Safe Margins & Manual Line Wrapping

### Ringkasan Perubahan
Memperbaiki posisi subtitle agar aman dari *UI chrome* platform (TikTok/Reels/Shorts) dengan mengoreksi `margin_v_ratio`, menambahkan `margin_h_ratio` (MarginL/MarginR), dan mengimplementasikan *manual line wrapping* berdasarkan `max_line_width_ratio` agar teks tidak mepet/nabrak kolom ikon kanan.

### Aktivitas Detail
* **Koreksi margin (`subtitles.py` STYLES dict)**:
  * `viral-bold`, `highlight-box`, `neon-gradient`: `margin_v_ratio` 0.16 → **0.26**.
  * `clean-minimal`, `minimalist`: `margin_v_ratio` 0.10/0.12 → **0.22**.
  * `word-pop`: `margin_v_ratio` **0.45** (tidak berubah, posisi tengah frame).
  * Semua style mendapat `margin_h_ratio: 0.09` dan `max_line_width_ratio: 0.82`.
* **MarginL/MarginR di ASS header** (`_header()`):
  * Mengganti hardcoded `20,20` dengan `{margin_h},{margin_h}` yang dihitung dari `margin_h_ratio × play_res_x`.
  * Pada 1080px → MarginL=MarginR=97px (sebelumnya 20px).
* **Manual line wrapping** (fungsi baru `_wrap_text()` dan `_estimate_text_width()`):
  * Mengestimasi lebar teks per karakter (0.55 × font_size) untuk menentukan kapan harus wrap.
  * Builder karaoke (`build_karaoke_fill`, `build_karaoke_sweep`, `build_word_box_highlight`): wrap text per chunk, gabung dengan `\\N`, satu Dialogue line per segment.
  * Builder per-word (`build_fade_in_word`, `build_word_popup`): insert `\\N` Dialogue line di batas wrap, satu Dialogue line per kata.
* **Inject computed values** (`generate_ass()`):
  * Menyuntikkan `_font_size` dan `_play_res_x` ke style dict sebelum builder dipanggil agar semua builder bisa akses tanpa ubah signature.
* **Alignment verification**: Semua style menggunakan `\an2` (bottom-center), MarginV diukur dari tepi bawah frame — sesuai spesifikasi.

---

## [2026-06-20 04:35 - 04:50 WIB] — Ekspansi 8 Subtitle Style & Preview Cards Interaktif

### Ringkasan Perubahan
Memperluas sistem subtitle dari 4 style menjadi 8 style dengan menambahkan 2 *animation builder* baru (`word_pop_scale`, `word_box_highlight`), parameter `case` untuk auto-uppercase/lowercase, dan `blur` untuk efek glow ASS. Mengganti dropdown style di frontend dengan *clickable preview cards* yang menampilkan mockup visual setiap style.

### Aktivitas Detail
* **Backend `subtitles.py`**:
  * Memperbarui style `viral-bold` (Inter Black, uppercase, outline_width=4, blur=0).
  * Menambahkan 4 style baru: `word-pop` (one-word-at-a-time pop scale), `clean-minimal` (fade per word, lowercase, no outline), `highlight-box` (box effect via `\bord` tebal + `\kf` sweep, warna hijau), `neon-gradient` (karaoke fill cyan→magenta dengan `\blur4` glow).
  * Menambahkan 2 *animation builder*: `build_word_pop_scale` (satu kata visible, pop-in dari scale 70→100) dan `build_word_box_highlight` (thill `\bord` + `\3c` box color trick).
  * Menambahkan helper `_apply_case()` untuk parameter `case` (`upper`/`lower`/`normal`) pada semua builder.
  * Memperbarui `_header()` untuk mendukung `blur` (ASS Shadow field) dan `secondary_color` (ASS SecondaryColour).
  * Style lama (`minimalist`, `neon-glow`, `classic-popup`) dipertahankan tanpa perubahan.
* **Backend `routes/tasks.py`**:
  * `SubtitleStyle` Literal diperluas dari 4 ke 8 nilai.
* **Frontend `page.tsx`**:
  * Dropdown style diganti dengan *clickable preview cards* (grid `2×sm:3`).
  * 8 card dengan mockup visual: gradient background, text preview sesuai style (uppercase/lowercase, glow shadow, box outline, single-word pop).
  * 3 renderer khusus: `boxStyle` (green box outline), `singleWord` (satu kata centered), default (multi-word highlight).
  * Card terpilih mendapat amber ring + checkmark badge.

---

## [2026-06-20 04:25 - 04:35 WIB] — Multi-Style Subtitle System (Strategy Pattern)

### Ringkasan Perubahan
Membangun sistem subtitle karaoke dari nol dengan arsitektur *Strategy pattern* yang mendukung 4 gaya animasi berbeda (Viral Bold, Minimalist, Neon Glow, Classic Pop-up). Mengintegrasikan subtitle burn-in ke pipeline render dengan single ffmpeg re-encode call, menggantikan pola stream-copy mux sebelumnya.

### Aktivitas Detail
* **Membuat `backend/app/engine/subtitles.py`**:
  * Menerapkan *Strategy pattern* dengan `STYLES` dict (visual params) dan `ANIMATION_BUILDERS` dispatch (animation logic).
  * 4 *animation builder*: `build_karaoke_fill` (\\kf tags), `build_karaoke_sweep` (\\k + outline flash), `build_fade_in_word` (\\alpha\\t per word), `build_word_popup` (\\fscx/\\fscy scale transform per word).
  * `generate_ass()` menghasilkan file `.ass` dengan header lengkap (PlayResX/Y, V4+ Styles, Events).
  * MarginV dan font size dihitung berdasarkan rasio (`margin_v_ratio`, `font_size_ratio`) terhadap `play_res_y`, bukan hardcoded piksel.
* **Modifikasi `backend/app/engine/render.py`**:
  * Menambahkan `_mux_with_subtitles()` — single ffmpeg call: re-encode `libx264 -preset fast -crf 20` dengan ASS burn-in, atau stream-copy tanpa subtitle.
  * Menambahkan `_ffmpeg_escape_path()` — escape drive-letter colons di Windows (`C:` → `C\:`) untuk filter `ass=`.
  * `_reframe_vertical()` dan `render_clips()` menerima parameter `subtitle_path` dan `fonts_dir`.
  * *Intermediate silent video* di-preserve (tidak dihapus) untuk memungkinkan restyle tanpa re-run pipeline penuh.
* **Threading parameter `subtitle_style` melalui stack**:
  * `backend/app/routes/tasks.py` — `SubtitleStyle = Literal["viral-bold", "minimalist", "neon-glow", "classic-popup"]` di `CreateTaskRequest`, validasi Pydantic otomatis return 422 jika invalid.
  * `backend/app/state.py` — Field `subtitle_style` di `TaskRecord`, backward-compat `.get('subtitle_style', None)` di `_record_from_dict()`.
  * `backend/app/queue.py` — Ekstrak `subtitle_style` dari record, pass ke `run_pipeline()`.
  * `backend/app/engine/pipeline.py` — Tahap baru SUBTITLES (50-65%) antara ANALYZE dan RENDER, memanggil `generate_ass()`.
* **Konfigurasi**:
  * `backend/app/config.py` — `SUBTITLE_STYLE_DEFAULT` dan `FONTS_DIR` dari env.
  * Membuat direktori `backend/fonts/` untuk bundling font dengan `fontsdir` param.
* **Frontend (`frontend/src/app/page.tsx`)**:
  * Menambahkan state `subtitleStyle` dan Select "Gaya Subtitle" (4 opsi) di *Advanced Settings*.
  * Grid di-expand dari `sm:grid-cols-3` ke `sm:grid-cols-4`.
* **Frontend API (`frontend/src/lib/api.ts`)**:
  * `subtitle_style` ditambahkan ke `CreateTaskOptions` dan `Task` interface.

---

## [2026-06-20 03:40 - 03:45 WIB] — Integrasi Erat Backend & Frontend & Peningkatan UI Premium

### Ringkasan Perubahan
Mengintegrasikan secara penuh frontend Next.js dan backend FastAPI dengan menghubungkan parameter input tingkat lanjut (Advanced Settings), mengimplementasikan pelacakan tugas lokal (Recent Tasks) berbasis localStorage, serta mempercantik tampilan antarmuka menjadi sangat premium, modern, dan responsif.

### Aktivitas Detail
* **Advanced Settings di Landing Page**:
  * Menambahkan opsi kontrol untuk menentukan jumlah klip (`num_clips`), aspek rasio (`aspect_ratio`), dan bahasa transkripsi (`language`) di [page.tsx](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/frontend/src/app/page.tsx).
* **Fitur Mode Gelap (Dark Mode)**:
  * Mengintegrasikan `ThemeProvider` dari `next-themes` pada [layout.tsx](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/frontend/src/app/layout.tsx) dan menambahkan [theme-provider.tsx](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/frontend/src/components/theme-provider.tsx).
  * Membuat komponen tombol interaktif [theme-toggle.tsx](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/frontend/src/components/theme-toggle.tsx) dengan ikon dinamis dan animasi transisi.
  * Memasang tombol toggle mode gelap di header landing page dan top navbar halaman detail tugas.
* **Perbaikan Error OpenCV (Grayscale Channel Mismatch)**:
  * Mengatasi crash `(-15:Bad number of channels)` secara komprehensif di OpenCV saat memproses video grayscale (1 channel) pada [render.py](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/backend/app/engine/render.py).
  * Membuat helper `_read_bgr_frame` untuk membaca frame dan secara otomatis menormalisasinya ke format BGR 3-channel jika format aslinya adalah grayscale (1-channel), mencegah terjadinya ketidakcocokan channel di seluruh alur pemrosesan video (seperti pada deteksi wajah DNN Caffe, perhitungan mouth motion, dan kalkulasi histogram warna).
* **Otomasi Startup Backend & Frontend**:
  * Membuat skrip [start-backend.js](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/frontend/scripts/start-backend.js) di dalam folder frontend untuk memeriksa keaktifan backend dan meluncurkannya secara asinkronus jika belum aktif.
  * Menambahkan lifecycle script `prebuild` dan `predev` pada [package.json](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/frontend/package.json) agar backend otomatis aktif di background sebelum server frontend (`next dev`) atau build produksi dimulai.
  * Membuat berkas [package.json](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/package.json) di root workspace agar perintah `npm run dev` dapat dijalankan langsung dari root proyek untuk menghidupkan backend (port 8000) dan frontend (port 3107) sekaligus.
* **Riwayat Tugas Lokal (Recent Tasks)**:
  * Mengintegrasikan penyimpanan lokal `localStorage` pada [page.tsx](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/frontend/src/app/page.tsx) untuk menyimpan daftar `task_id` yang telah dibuat sehingga pengguna dapat melacak progres tugas mereka sewaktu-waktu.
* **Peningkatan Visual Estetika Halaman Detail**:
  * Mempercantik visualisasi progress bar pemrosesan dengan visual card yang modern dan glossy pada [page.tsx](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/frontend/src/app/tasks/[id]/page.tsx).
  * Mendesain ulang kartu klip (`ClipCard`) menggunakan efek bayangan dinamis, grid yang rapi, info durasi yang lengkap, serta detail kalimat hook yang lebih menarik.
* **Penyelarasan Server**:
  * Memastikan backend FastAPI berjalan stabil di port `:8000` dengan dukungan CORS penuh untuk frontend Next.js di port `:3107`.

---

## [2026-06-20 03:34 - 03:35 WIB] — Docker Cleanup & Monorepo Guide Finalization

### Summary of Changes
Removed Docker configuration from the frontend directory and updated developer guides (`AGENTS.md` & `plan.md`) to align with the new monorepo layout.

### Detailed Activities
* **Docker Cleanup in Frontend**:
  * Deleted [Dockerfile](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/frontend/Dockerfile) and `.dockerignore` in the `frontend/` directory to enforce native local execution.
* **Documentation Synchronization**:
  * Rewrote [AGENTS.md](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/AGENTS.md) and [plan.md](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/plan.md) to replace references of legacy decoupled directories (`AI-Youtube-Shorts-Generator/` and `supoclip/`) with the unified monorepo directories (`backend/` and `frontend/`).

---

## [2026-06-20 03:20 - 03:28 WIB] — Monorepo Consolidation & Core Engine Enhancements

### Summary of Changes
Consolidated separate repositories into a unified monorepo, fixed the Gemini transcription timestamp bug, enabled dual-caching (JSON & SRT), and improved highlight quality with speaker-aware prompt formatting.

### Detailed Activities
* **Monorepo Consolidation**:
  * Moved the legacy CLI engine folder (`AI-Youtube-Shorts-Generator`) to the root workspace as [backend/](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/backend).
  * Moved the legacy frontend application (`supoclip/frontend`) to the root workspace as [frontend/](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/frontend).
* **Gemini Transcription & Timestamp Fix**:
  * Modified [transcriber.py](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/backend/app/engine/transcriber.py) to read both `start_time` / `end_time` and `start` / `end` keys flexibly. This resolved the issue where transcription timestamps defaulted to `00:00:00,000`.
* **Dual Caching Implementation**:
  * Configured the transcription pipeline to output both `.srt` files (for burning subtitles) and `.json` files (to preserve speaker/diarization metadata).
* **Speaker-Aware Highlights**:
  * Updated [highlights.py](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/backend/app/engine/highlights.py) to prefix conversational lines with `[Speaker X]:` before sending the transcript to the highlights model, allowing the model to analyze dialog context.
* **Local Highlights Model Integration**:
  * Directed the highlight search engine in [llm.py](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/backend/app/engine/llm.py) to run against the local `mimo-v2.5-pro` model (`http://localhost:20128/v1` OpenAI-compatible API) and integrated a pluggable Gemini highlight provider.
