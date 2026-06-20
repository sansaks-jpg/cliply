<!-- 
CRITICAL RULE FOR AI AGENTS:
DO NOT OVERWRITE OR DELETE EXISTING CHANGELOG ENTRIES. 
Always prepend new entries at the top of this file (directly below this rule block) when documenting new modifications. 
Preserve all historical logs to maintain context for future agents and developers.
-->

# CHANGELOG.md — Activity Log for `clip-ai` Workspace

This file documents the history of major modifications made to the `clip-ai` workspace, providing chronological context for developers and AI agents.

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
