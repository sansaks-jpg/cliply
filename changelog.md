<!-- 
CRITICAL RULE FOR AI AGENTS:
DO NOT OVERWRITE OR DELETE EXISTING CHANGELOG ENTRIES. 
Always prepend new entries at the top of this file (directly below this rule block) when documenting new modifications. 
Preserve all historical logs to maintain context for future agents and developers.
-->

# CHANGELOG.md — Activity Log for `clip-ai` Workspace

This file documents the history of major modifications made to the `clip-ai` workspace, providing chronological context for developers and AI agents.

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
