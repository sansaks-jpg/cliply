# Cliply Frontend Design Document

## Frontmatter (YAML)
```yaml
title: Cliply Frontend Design & Color Palette
status: approved
author: Antigravity / Cliply Team
date: 2026-06-30
```

---

## 1. Overview
Dokumen ini menjelaskan arsitektur antarmuka, filosofi desain, sistem pewarnaan (color palette), tipografi, serta optimasi performa frontend pada proyek **Cliply** (aplikasi desktop Tauri + Next.js untuk konversi otomatis video YouTube menjadi klip pendek/shorts vertikal 9:16).

---

## 2. Goals & Non-Goals

### Goals
- **Cinematic & Achromatic Aesthetic**: Menyajikan desain premium bernuansa gelap sinematik (dark mode) serta monokrom bersih (light mode) yang memanjakan mata pengguna.
- **Fluid & Responsive Layout**: Memastikan antarmuka stabil dan pas di layar tanpa adanya pergeseran layout (layout shifts), memberikan sensasi seperti aplikasi native desktop.
- **GPU Resource Conservation**: Menghentikan animasi berat saat jendela tidak aktif/diminimize guna meminimalkan penggunaan daya GPU.
- **Real-time Pipeline Visibility**: Mempermudah pengguna melacak progress pembuatan klip melalui stage progress visual (dari download hingga rendering selesai).

### Non-Goals
- Pemrosesan video (seperti cropping, transcoding, transkripsi AI) tidak dilakukan di sisi frontend (seluruhnya diserahkan ke Python FastAPI backend).
- Manajemen database relasional di sisi client. Data histori dan tugas disimpan secara lokal atau via memory cache backend.

---

## 3. User Stories
- **Sebagai Kreator Konten**, saya ingin memasukkan URL YouTube di halaman utama agar saya bisa memotong video panjang menjadi klip pendek secara instan.
- **Sebagai Editor**, saya ingin melihat pratinjau (preview) gaya teks subtitle yang dinamis (seperti gaya TikTok atau Neon) sebelum klip dirender agar saya tahu hasil akhirnya.
- **Sebagai Pengguna Desktop**, saya ingin memilih direktori penyimpanan file video ekspor saya sendiri agar tidak memenuhi drive sistem (C:) secara tidak sengaja.
- **Sebagai Pengguna Profesional**, saya ingin antarmuka yang tidak memakan daya GPU saat saya sedang me-minimize aplikasi ke background.

---

## 4. Architecture
Frontend Cliply dibangun di atas Next.js 15 (App Router, static export) yang berjalan di dalam Rust Tauri v2 Shell. Frontend berkomunikasi dengan Python FastAPI server lokal di port 8003.

```mermaid
graph TD
    subgraph Client-Side (Tauri Desktop App)
        A[Next.js App Router UI] <-->|Inter-Process Communication| B[Rust Tauri Core]
        A <-->|HTTP / SSE / Static Files| C[FastAPI Backend - Port 8003]
        B <-->|Spawn & Monitor| C
    end
    
    subgraph external [External APIs]
        C <-->|Download Video| D[yt-dlp Engine]
        C <-->|Transcription| E[Gemini 2.5 Flash / Groq Whisper]
        C <-->|Highlight Detection| F[Gemini / OpenAI LLM]
    end
```

---

## 5. Detailed Design

### A. Color Palette & Visual Theme
Cliply menggunakan sistem tema dinamis (gelap dan terang) yang dikonfigurasi melalui `@theme` pada Tailwind CSS v4 di file [globals.css](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/frontend/src/app/globals.css).

#### 1. Light Theme (Clean White Monochrome)
Setup monokrom bersih dengan dominasi warna putih absolut dan aksen hitam pekat.
- **Background**: `#ffffff` (Absolute White)
- **Foreground**: `#09090b` (Zinc Dark / Text)
- **Card**: `#fafafa` (Zinc Light Container - Elevasi Tier 1)
- **Primary**: `#09090b` (Solid Black)
- **Secondary / Muted / Accent**: `#f4f4f5` (Zinc Gray)
- **Border**: `#e4e4e7` (Micro-border Tier 1)
- **Ring**: `#d4d4d8` (Border Tier 2)
- **Shadows (Invisible Shadows)**: Menggunakan difusi ekstrem dengan opasitas sangat rendah (`rgba(0, 0, 0, 0.03)` sampai `0.08`) untuk memberi kedalaman tanpa terlihat mencolok.

#### 2. Dark Theme (Achromatic Cinematic Setup)
Setup hitam absolut sinematik untuk efisiensi layar OLED serta visual yang premium.
- **Background**: `#000000` (Absolute Black)
- **Foreground**: `#e5e1e4` (Warm White-Gray)
- **Card**: `#09090b` (Zinc Dark - Elevasi Tier 1)
- **Popover**: `#18181b` (Zinc Elevated - Elevasi Tier 2)
- **Primary**: `#ffffff` (Pure White)
- **Secondary**: `#c6c6cf`
- **Muted**: `#09090b`
- **Accent**: `#18181b`
- **Border**: `#27272a` (Micro-border Tier 1)
- **Ring**: `#3f3f46` (Border Popover Tier 2)
- **Shadows (Invisible Shadows)**: Difusi pendaran putih halus (`rgba(255, 255, 255, 0.04)` sampai `0.08`).

---

### B. Glassmorphism & Visual Effects
Untuk memperkuat estetika premium, Cliply mengimplementasikan kelas Glassmorphism:
- **`.glass`**: Background transparan (`rgba(..., 0.6)`) dengan `backdrop-filter: blur(16px)` dan border tipis.
- **`.glass-strong`**: Transparansi (`rgba(..., 0.8)`) dengan blur lebih tebal (`24px`).
- **`.glass-panel`**: Panel sinematik utama dengan efek *inset border* tipis di dark mode serta bayangan lembut menyebar.

---

### C. Typography
Cliply mengimpor dan menggabungkan beberapa font modern melalui Google Fonts:
- **Sans/Body Font**: `Plus Jakarta Sans` dan `Geist` (menjamin keterbacaan teks informasi tinggi).
- **Display/Header Font**: `Plus Jakarta Sans` dan `Syne` (memberikan karakter tegas dan artistik pada judul).
- **Subtitles Preview Font**: `Montserrat` dan `Plus Jakarta Sans` (memiliki bobot *bold* yang tebal, sangat cocok untuk format subtitle video portrait/shorts).

---

### D. Optimasi Performa & GPU (GpuOptimizer)
Aplikasi desktop sering kali berjalan di latar belakang (background). Untuk menghemat daya baterai dan penggunaan GPU (khususnya rendering animasi CSS):
1. Komponen [GpuOptimizer](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/frontend/src/components/gpu-optimizer.tsx) memantau fokus jendela (`blur`, `focus`, dan `visibilitychange`).
2. Jika jendela diminimize atau tidak fokus, kelas `.window-inactive` akan disuntikkan ke root dokumen (`<html>`).
3. Di dalam [globals.css](file:///C:/Users/WORKPLUS/Documents/WEB/clip-ai/frontend/src/app/globals.css#L355-L370), seluruh animasi dinamis (seperti floating blobs background, glow pulse, dan text gradient shift) langsung dinonaktifkan (`animation: none !important; display: none !important;`).

---
### E. Struktur Halaman & Layout Utama

#### 1. Halaman Utama (Home - `/`)
- **Fungsi**: Menerima input tautan URL YouTube dan menampilkan riwayat proyek lokal/tugas aktif dengan antarmuka yang sangat ringkas dan terfokus.
- **Desain**: Input URL YouTube sinematik dengan visual neon glow ringkas, diikuti riwayat tugas recent workspace.
- **SetupWizard**: Modal onboarding awal yang memaksa pengguna memilih folder penyimpanan video lokal jika baru pertama kali membuka aplikasi.

#### 2. Halaman Studio Editor (Customize - `/customize`)
- **Fungsi**: Workspace konfigurasi parameter studio, pemilihan tipe template (`podcast`, `gaming`, `split`), dan pratinjau hasil sebelum rendering.
- **Desain**: Antarmuka 2-Panel Universal *Viewport-Fit* (tanpa scroll desktop global):
  - **Panel Kiri (Setelan Studio)**: Memuat tab switcher horizontal dinamis (Template & Klip, Subtitle & Gaya, Lanjutan) untuk menekan tinggi visual. Menggunakan animasi transisi micro-interaction elegan di mana card aktif membesar dengan penjelasan penuh dan card non-aktif meredup & menyusut.
  - **Panel Kanan (Preview & Render)**: Memuat kartu info YouTube terintegrasi link URL, player perbandingan video horizontal lebar (Original 16:9 berdampingan dengan HP Mockup 9:16 berukuran 150px), simulasi teks subtitle karaoke aktif, dan tombol rendering utama.

#### 3. Halaman Tugas & Status (Tasks - `/tasks`)
- **Fungsi**: Melacak progress pembuatan klip (Pipeline 7 Stages) dan memutar video klip yang sudah selesai dibuat.
- **Desain**: Menggunakan layout panel `.glass-panel` yang membagi area pelacakan status (menggunakan SSE connection untuk update real-time) dan galeri hasil video vertikal.
- **VerticalPlayer**: Player video 9:16 kustom buatan sendiri dengan kontrol seekbar minimalis dan penyesuaian volume hover untuk pengalaman menonton yang clean.

#### 4. Halaman Pengaturan (Settings - `/settings`)
- **Fungsi**: Konfigurasi kunci API (Gemini, Groq, OpenAI), pengaturan sensitivitas deteksi klip viral, pemilihan model LLM, penggantian folder penyimpanan, dan pengecekan pembaruan versi (tauri-plugin-updater).
- **Desain**: Layout berkolom rapi dengan ikon indikator yang jelas menggunakan Lucide React.

---

### F. Subtitle Style Definitions & Previews
Sistem pratinjau teks subtitle pada halaman studio editor (`/customize`) menggunakan pemetaan gaya visual dinamis:
- **`viral-bold`**: Huruf besar, tebal, dengan shadow stroke hitam 3px (Font: Montserrat). Animasi karaoke kuning.
- **`tiktok`**: Teks khas aplikasi TikTok dengan stroke hitam 4px (Font: Plus Jakarta Sans). Animasi karaoke hijau terang.
- **`word-pop`**: Kata yang muncul satu per satu dengan transisi popup yang cepat.
- **`clean-minimal`**: Huruf kecil semua tanpa border/stroke, bergaya estetik minimalis.
- **`highlight-box`**: Teks dikelilingi kotak sorotan semi-transparan.
- **`neon-gradient`**: Gaya cyberpunk dengan gradasi warna neon menyala (cyan & magenta) dan stroke tipis.

---

## 6. Alternatives Considered

### 1. Menggunakan Library Pemutar Video Pihak Ketiga (seperti React-Player)
- *Alternatif*: React-player atau Video.js.
- *Keputusan*: Ditolak. Kita membuat komponen **VerticalPlayer** sendiri menggunakan elemen HTML5 `<video>` native untuk kontrol penuh atas tata letak aspek rasio 9:16 vertikal, performa rendering yang sangat ringan, dan integrasi gaya kontrol pemutar yang selaras dengan tema monokrom/achromatic Cliply.

### 2. Penggunaan Tailwind CSS v3 vs v4
- *Alternatif*: Tetap menggunakan v3 dengan file `tailwind.config.js` standar.
- *Keputusan*: Memilih Tailwind CSS v4. Integrasi v4 menggunakan deklarasi `@import "tailwindcss"` dan pengenalan variabel CSS langsung pada `@theme` di globals.css membuat sintaks penulisan tema jauh lebih bersih dan mempermudah sinkronisasi variabel CSS Next.js dengan Tauri Rust Core.
