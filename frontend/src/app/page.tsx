"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Youtube, Loader2, ArrowRight, Sparkles, Settings2, Trash2, History, Video, Clock } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ThemeToggle } from "@/components/theme-toggle";
import { createTask, deleteTask, getAvailableEncoders } from "@/lib/api";

const YOUTUBE_RE =
  /^(https?:\/\/)?(www\.)?(youtube\.com\/(watch\?v=|shorts\/|embed\/|live\/)|youtu\.be\/).+/i;

interface RecentTask {
  id: string;
  url: string;
  timestamp: number;
}

export default function Home() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [urlFocused, setUrlFocused] = useState(false);
  
  // Advanced Options state
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [activeCategory, setActiveCategory] = useState<"crucial" | "style">("crucial");
  const [numClips, setNumClips] = useState("5");
  const [aspectRatio, setAspectRatio] = useState("9:16");
  const [language, setLanguage] = useState("auto");
  const [subtitleStyle, setSubtitleStyle] = useState("viral-bold");
  const [faceDetector, setFaceDetector] = useState("yunet");
  const [encoder, setEncoder] = useState("auto");
  const [availableEncoders, setAvailableEncoders] = useState<string[]>(["auto", "cpu"]);

  // Fetch available encoders on mount
  useEffect(() => {
    getAvailableEncoders().then((res) => {
      setAvailableEncoders(res.available);
      setEncoder(res.current);
    }).catch(() => {});
  }, []);

  // Custom Style overrides state
  const [customStyle, setCustomStyle] = useState(false);
  const [subtitleFont, setSubtitleFont] = useState("Montserrat");
  const [subtitleColorPrimary, setSubtitleColorPrimary] = useState("#FFFFFF");
  const [subtitleColorHighlight, setSubtitleColorHighlight] = useState("#00FFFF");

  // Recent tasks state
  const [recentTasks, setRecentTasks] = useState<RecentTask[]>([]);

  // Realtime animation state for subtitle preview
  const [wordProgressIndex, setWordProgressIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setWordProgressIndex((prev) => (prev + 1) % 12);
    }, 600);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    // Load recent tasks from localStorage
    const saved = localStorage.getItem("clip_ai_recent_tasks");
    if (saved) {
      try {
        setRecentTasks(JSON.parse(saved));
      } catch (e) {
        /* ignore corrupt data */
      }
    }
  }, []);

  const isValid = YOUTUBE_RE.test(url.trim());

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid || submitting) return;

    setSubmitting(true);
    try {
      const opts = {
        num_clips: parseInt(numClips, 10),
        aspect_ratio: aspectRatio,
        language: language === "auto" ? undefined : language,
        subtitle_style: subtitleStyle,
        face_detector: faceDetector,
        encoder,
        ...(customStyle ? {
          subtitle_font: subtitleFont,
          subtitle_color_primary: subtitleColorPrimary,
          subtitle_color_highlight: subtitleColorHighlight,
        } : {}),
      };

      const { task_id } = await createTask(url.trim(), opts);
      
      // Save to recent tasks
      const newTask: RecentTask = {
        id: task_id,
        url: url.trim(),
        timestamp: Date.now(),
      };
      const updated = [newTask, ...recentTasks.filter(t => t.id !== task_id)].slice(0, 10);
      setRecentTasks(updated);
      localStorage.setItem("clip_ai_recent_tasks", JSON.stringify(updated));

      toast.success("Tugas pembuatan klip berhasil dimulai!");
      router.push(`/tasks/${task_id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Gagal memulai tugas.");
    } finally {
      setSubmitting(false);
    }
  };

  const removeRecentTask = async (id: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await deleteTask(id);
    } catch (err) {
      console.error("Gagal menghapus tugas dari server:", err);
    }
    const updated = recentTasks.filter(t => t.id !== id);
    setRecentTasks(updated);
    localStorage.setItem("clip_ai_recent_tasks", JSON.stringify(updated));
    toast.success("Riwayat tugas dan file penyimpanan berhasil dihapus");
  };

  // Helper to extract video ID or display clean label
  const getCleanUrlLabel = (fullUrl: string) => {
    try {
      const u = new URL(fullUrl);
      if (u.hostname.includes("youtube.com")) {
        const v = u.searchParams.get("v");
        if (v) return `youtube.com/watch?v=${v.substring(0, 8)}...`;
      } else if (u.hostname.includes("youtu.be")) {
        return `youtu.be/${u.pathname.substring(1, 9)}...`;
      }
      return fullUrl.length > 40 ? `${fullUrl.substring(0, 37)}...` : fullUrl;
    } catch (e) {
      return fullUrl;
    }
  };

  // getDynamicPreviewStyles — colors must mirror backend STYLES dict exactly
  const getDynamicPreviewStyles = (styleKey: string) => {
    // Font — matches backend 'font' key
    const fontMap: Record<string, string> = {
      "viral-bold":    "Montserrat",
      "tiktok":        "Plus Jakarta Sans",
      "word-pop":      "Plus Jakarta Sans",
      "clean-minimal": "Helvetica",
      "highlight-box": "Plus Jakarta Sans",
      "neon-gradient": "Montserrat",
      "minimalist":    "Helvetica",
      "neon-glow":     "Montserrat",
      "classic-popup": "Helvetica",
    };
    const fontFamily = customStyle ? subtitleFont : (fontMap[styleKey] ?? "Helvetica");

    // Primary text color (inactive words) — matches backend ASS primary_color
    const primaryMap: Record<string, string> = {
      "viral-bold":    "#FFFFFF",
      "tiktok":        "#FFFFFF",
      "word-pop":      "#FFFFFF",
      "clean-minimal": "rgba(255,255,255,0.80)",
      "highlight-box": "#FFFFFF",
      "neon-gradient": "#FFF000",
      "minimalist":    "rgba(255,255,255,0.70)",
      "neon-glow":     "#00FFFF",
      "classic-popup": "#FFFFFF",
    };
    const primaryColor = customStyle ? subtitleColorPrimary : (primaryMap[styleKey] ?? "#FFFFFF");

    // Highlight color (active word) — matches backend ASS highlight_color
    const highlightMap: Record<string, string> = {
      "viral-bold":    "#FFFF00",
      "tiktok":        "#08E539",
      "word-pop":      "#FFFFFF",
      "clean-minimal": "rgba(255,255,255,0.40)",
      "highlight-box": "#76E600",
      "neon-gradient": "#E500FF",
      "minimalist":    "rgba(255,255,255,0.30)",
      "neon-glow":     "#FF00FF",
      "classic-popup": "#FFFF00",
    };
    const highlightColor = customStyle ? subtitleColorHighlight : (highlightMap[styleKey] ?? "#FFFF00");

    // highlight-box border/bg
    let boxColor = "#76E600";
    let boxBgColor = "rgba(118,230,0,0.15)";
    if (styleKey === "highlight-box" && customStyle) {
      boxColor = subtitleColorHighlight;
      const hex = subtitleColorHighlight.startsWith("#") ? subtitleColorHighlight : "#" + subtitleColorHighlight;
      const r = parseInt(hex.slice(1, 3), 16);
      const g = parseInt(hex.slice(3, 5), 16);
      const b = parseInt(hex.slice(5, 7), 16);
      boxBgColor = `rgba(${isNaN(r)?118:r},${isNaN(g)?230:g},${isNaN(b)?0:b},0.15)`;
    }

    // outline simulation — only neon-gradient has colored outline
    const outlineColor = styleKey === "neon-gradient" ? (customStyle ? subtitleColorPrimary : "#FFF000") : undefined;

    return { fontFamily, primaryColor, highlightColor, boxColor, boxBgColor, outlineColor };
  };

  return (
    <main className="min-h-screen bg-gradient-to-b from-stone-50 via-white to-stone-100/50 dark:from-stone-950 dark:via-stone-900 dark:to-stone-950 text-foreground transition-colors duration-300 relative overflow-x-hidden">
      {/* Animated Background Blobs */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden -z-10">
        <div className="absolute -top-40 -left-40 w-[500px] h-[500px] rounded-full bg-gradient-to-br from-amber-200/30 via-rose-200/20 to-transparent dark:from-amber-500/5 dark:via-rose-500/5 blur-3xl animate-blob" />
        <div className="absolute -bottom-40 -right-40 w-[600px] h-[600px] rounded-full bg-gradient-to-tl from-violet-200/30 via-fuchsia-200/20 to-transparent dark:from-violet-500/5 dark:via-fuchsia-500/5 blur-3xl animate-blob-2 animation-delay-2000" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[400px] h-[400px] rounded-full bg-gradient-to-r from-cyan-200/20 to-sky-200/20 dark:from-cyan-500/5 dark:to-sky-500/5 blur-3xl animate-blob-3 animation-delay-4000" />
      </div>

      {/* Top Navbar */}
      <header className="border-b border-stone-200/50 dark:border-stone-855 sticky top-0 z-10 glass-strong transition-colors">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-amber-500 to-rose-500 flex items-center justify-center shadow-lg shadow-amber-500/20">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <span className="font-extrabold text-xl tracking-tight font-syne bg-clip-text text-transparent bg-gradient-to-r from-stone-900 to-stone-600 dark:from-white dark:to-stone-400">
              Clip AI
            </span>
          </div>
          <ThemeToggle />
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-12 sm:py-16 relative">
        {/* Hero Section */}
        <div className="text-center mb-14 animate-in fade-in slide-in-from-bottom-4 duration-700">
          <div className="inline-flex items-center gap-2 mb-5 px-4 py-1.5 rounded-full glass text-xs font-semibold text-stone-600 dark:text-stone-300 shadow-sm hover:scale-105 transition-all duration-300">
            <Sparkles className="w-3.5 h-3.5 text-amber-500" />
            <span>AI-Powered Viral Short Video Clipper</span>
          </div>
          <h1 className="text-5xl sm:text-7xl font-extrabold text-stone-900 dark:text-white mb-5 tracking-tight leading-[1.05]">
            Tempel Link YouTube.
            <br />
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-amber-500 via-rose-500 to-violet-600 dark:from-amber-400 dark:via-rose-400 dark:to-violet-500 animate-gradient">
              Hasilkan Video Viral 9:16.
            </span>
          </h1>
          <p className="text-stone-500 dark:text-stone-400 max-w-2xl mx-auto text-base sm:text-lg font-light leading-relaxed">
            AI akan mengunduh, mentranskripsi, mendeteksi momen viral, melacak wajah, dan memotong video vertikal dengan subtitle karaoke — semuanya otomatis.
          </p>
        </div>

        {/* Input Form & Config Box */}
        <div className="glass-strong rounded-2xl p-6 sm:p-8 shadow-xl dark:shadow-stone-950/30 mb-12 animate-in fade-in slide-in-from-bottom-6 duration-700 delay-100 hover:shadow-2xl transition-shadow duration-500">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="relative group">
              <Youtube className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-stone-400 dark:text-stone-500 group-focus-within:text-red-500 transition-all duration-300 group-focus-within:scale-110" />
              <Input
                type="url"
                placeholder="https://www.youtube.com/watch?v=..."
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onFocus={() => setUrlFocused(true)}
                onBlur={() => setUrlFocused(false)}
                className={`h-14 pl-12 pr-4 text-base rounded-xl border-2 transition-all duration-300 bg-stone-50/50 dark:bg-stone-950/30 ${
                  urlFocused
                    ? "border-amber-500/50 dark:border-amber-400/50 bg-white dark:bg-stone-950 shadow-[0_0_20px_-5px_rgba(245,158,11,0.3)]"
                    : "border-stone-200 dark:border-stone-800 focus:border-stone-400 dark:focus:border-stone-700"
                }`}
                autoFocus
              />
            </div>

            {/* Collapsible Advanced Options */}
            <div className="border-t border-stone-100 dark:border-stone-855 pt-4">
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="flex items-center gap-2 text-sm text-stone-500 dark:text-stone-400 hover:text-stone-800 dark:hover:text-stone-250 transition-colors font-medium"
              >
                <Settings2 className={`w-4 h-4 transition-transform duration-300 ${showAdvanced ? 'rotate-90 text-amber-500' : ''}`} />
                <span>Pengaturan Lanjutan</span>
              </button>

              {showAdvanced && (
                <div className="space-y-6 mt-4 p-5 rounded-2xl bg-stone-50 dark:bg-stone-950/50 border border-stone-100 dark:border-stone-855 animate-in fade-in slide-in-from-top-2 duration-300">
                  {/* Category Selection Tabs */}
                  <div className="flex border-b border-stone-200 dark:border-stone-800 pb-1">
                    <button
                      type="button"
                      onClick={() => setActiveCategory("crucial")}
                      className={`flex items-center gap-2 pb-2 px-3 text-xs sm:text-sm font-semibold border-b-2 transition-all duration-200 ${
                        activeCategory === "crucial"
                          ? "border-amber-500 text-amber-600 dark:text-amber-400"
                          : "border-transparent text-stone-500 hover:text-stone-800 dark:hover:text-stone-300"
                      }`}
                    >
                      <Settings2 className="w-4 h-4" />
                      <span>Pengaturan Krusial</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveCategory("style")}
                      className={`flex items-center gap-2 pb-2 px-3 text-xs sm:text-sm font-semibold border-b-2 transition-all duration-200 ${
                        activeCategory === "style"
                          ? "border-amber-500 text-amber-600 dark:text-amber-400"
                          : "border-transparent text-stone-500 hover:text-stone-800 dark:hover:text-stone-300"
                      }`}
                    >
                      <Sparkles className="w-4 h-4" />
                      <span>Gaya & Desain Subtitle</span>
                    </button>
                  </div>

                  {/* Crucial Category Panel */}
                  {activeCategory === "crucial" && (
                    <div className="grid grid-cols-1 sm:grid-cols-5 gap-4 animate-in fade-in duration-200">
                      <div className="space-y-2">
                        <Label htmlFor="num-clips" className="text-xs text-stone-500 dark:text-stone-400">Jumlah Klip</Label>
                        <Select value={numClips} onValueChange={setNumClips}>
                          <SelectTrigger id="num-clips" className="bg-white dark:bg-stone-900 border-stone-200 dark:border-stone-850">
                            <SelectValue placeholder="Pilih Jumlah" />
                          </SelectTrigger>
                          <SelectContent>
                            {[3, 5, 7, 10, 15].map((n) => (
                              <SelectItem key={n} value={n.toString()}>
                                {n} Klip
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="aspect-ratio" className="text-xs text-stone-500 dark:text-stone-400">Rasio Aspek</Label>
                        <Select value={aspectRatio} onValueChange={setAspectRatio}>
                          <SelectTrigger id="aspect-ratio" className="bg-white dark:bg-stone-900 border-stone-200 dark:border-stone-855">
                            <SelectValue placeholder="Pilih Rasio" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="9:16">9:16 Vertikal</SelectItem>
                            <SelectItem value="1:1">1:1 Persegi</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="language" className="text-xs text-stone-500 dark:text-stone-400">Bahasa Transkripsi</Label>
                        <Select value={language} onValueChange={setLanguage}>
                          <SelectTrigger id="language" className="bg-white dark:bg-stone-900 border-stone-200 dark:border-stone-850">
                            <SelectValue placeholder="Pilih Bahasa" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="auto">Deteksi Otomatis</SelectItem>
                            <SelectItem value="id">Bahasa Indonesia (id)</SelectItem>
                            <SelectItem value="en">English (en)</SelectItem>
                            <SelectItem value="es">Español (es)</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="face-detector" className="text-xs text-stone-500 dark:text-stone-400">Detektor Wajah</Label>
                        <Select value={faceDetector} onValueChange={setFaceDetector}>
                          <SelectTrigger id="face-detector" className="bg-white dark:bg-stone-900 border-stone-200 dark:border-stone-850">
                            <SelectValue placeholder="Pilih Detektor" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="yunet">YuNet ONNX</SelectItem>
                            <SelectItem value="mediapipe">MediaPipe BlazeFace</SelectItem>
                            <SelectItem value="yolov8-face">YOLOv8-Face Nano</SelectItem>
                            <SelectItem value="ssd">Caffe SSD ResNet-10</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="encoder" className="text-xs text-stone-500 dark:text-stone-400">Encoder GPU/CPU</Label>
                        <Select value={encoder} onValueChange={setEncoder}>
                          <SelectTrigger id="encoder" className="bg-white dark:bg-stone-900 border-stone-200 dark:border-stone-850">
                            <SelectValue placeholder="Pilih Encoder" />
                          </SelectTrigger>
                          <SelectContent>
                            {availableEncoders.includes("auto") && <SelectItem value="auto">Auto-detect</SelectItem>}
                            {availableEncoders.includes("nvidia") && <SelectItem value="nvidia">NVIDIA NVENC</SelectItem>}
                            {availableEncoders.includes("intel") && <SelectItem value="intel">Intel QSV</SelectItem>}
                            {availableEncoders.includes("amd") && <SelectItem value="amd">AMD AMF</SelectItem>}
                            {availableEncoders.includes("cpu") && <SelectItem value="cpu">CPU (libx264)</SelectItem>}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                  )}

                  {/* Style Category Panel */}
                  {activeCategory === "style" && (
                    <div className="space-y-5 animate-in fade-in duration-200">
                      {/* Color & Font Overrides Section */}
                      <div className="p-4 rounded-xl border border-stone-200/70 dark:border-stone-800 bg-white dark:bg-stone-900 space-y-4">
                        <div className="flex items-center justify-between">
                          <div className="space-y-0.5">
                            <Label className="text-sm font-semibold text-stone-800 dark:text-stone-200">Kustomisasi Font & Warna</Label>
                            <p className="text-[11px] text-stone-500 dark:text-stone-400">Gunakan warna dan font khusus di luar default template style</p>
                          </div>
                          <button
                            type="button"
                            onClick={() => setCustomStyle(!customStyle)}
                            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 ${
                              customStyle ? "bg-amber-500" : "bg-stone-200 dark:bg-stone-700"
                            }`}
                          >
                            <span
                              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform duration-200 ${
                                customStyle ? "translate-x-6" : "translate-x-1"
                              }`}
                            />
                          </button>
                        </div>

                        {customStyle && (
                          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-3 border-t border-stone-100 dark:border-stone-800/80 animate-in fade-in slide-in-from-top-1 duration-200">
                            <div className="space-y-2">
                              <Label htmlFor="sub-font" className="text-xs text-stone-500 dark:text-stone-400">Jenis Font</Label>
                              <Select value={subtitleFont} onValueChange={setSubtitleFont}>
                                <SelectTrigger id="sub-font" className="bg-white dark:bg-stone-900 border-stone-200 dark:border-stone-800">
                                  <SelectValue placeholder="Pilih Font" />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="Montserrat">Montserrat</SelectItem>
                                  <SelectItem value="Plus Jakarta Sans">Plus Jakarta Sans</SelectItem>
                                  <SelectItem value="Helvetica">Helvetica</SelectItem>
                                  <SelectItem value="Arial">Arial</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>

                            <div className="space-y-2">
                              <Label className="text-xs text-stone-500 dark:text-stone-400 block">Warna Utama (Text Color)</Label>
                              <div className="flex items-center gap-2">
                                <Input
                                  type="color"
                                  value={subtitleColorPrimary}
                                  onChange={(e) => setSubtitleColorPrimary(e.target.value)}
                                  className="w-10 h-10 p-0.5 rounded-md border border-stone-200 dark:border-stone-800 cursor-pointer bg-transparent"
                                />
                                <Input
                                  type="text"
                                  value={subtitleColorPrimary}
                                  onChange={(e) => setSubtitleColorPrimary(e.target.value)}
                                  className="h-10 text-xs font-mono uppercase bg-white dark:bg-stone-900 border-stone-200 dark:border-stone-800"
                                />
                              </div>
                            </div>

                            <div className="space-y-2">
                              <Label className="text-xs text-stone-500 dark:text-stone-400 block">Warna Aktif (Highlight Word)</Label>
                              <div className="flex items-center gap-2">
                                <Input
                                  type="color"
                                  value={subtitleColorHighlight}
                                  onChange={(e) => setSubtitleColorHighlight(e.target.value)}
                                  className="w-10 h-10 p-0.5 rounded-md border border-stone-200 dark:border-stone-800 cursor-pointer bg-transparent"
                                />
                                <Input
                                  type="text"
                                  value={subtitleColorHighlight}
                                  onChange={(e) => setSubtitleColorHighlight(e.target.value)}
                                  className="h-10 text-xs font-mono uppercase bg-white dark:bg-stone-900 border-stone-200 dark:border-stone-800"
                                />
                              </div>
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Subtitle Template Selection */}
                      <div className="space-y-2">
                        <Label className="text-xs text-stone-500 dark:text-stone-400">Template Gaya Subtitle</Label>
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                          {([
                            // ── Definisi template — sinkron dengan backend STYLES dict ──────
                            {
                              key: "viral-bold",
                              label: "Viral Bold",
                              bg: "from-zinc-900 to-zinc-950",
                              // backend: font=Montserrat, case=upper, bold=True, outline=4px black, highlight=#FFFF00
                              animation: "karaoke",
                              bold: true,
                              caseTransform: "uppercase" as const,
                              outlineWidth: 4,
                              outlineColor: "#000",
                              words: ["INI", "CONTOH", "SUBTITLE", "VIRAL", "BOLD"],
                              marginBottom: "26%",
                            },
                            {
                              key: "tiktok",
                              label: "TikTok Style",
                              bg: "from-zinc-900 to-zinc-950",
                              // backend: font=Plus Jakarta Sans, case=upper, bold=True, outline=20px black, highlight=#08E539, font_size_ratio=0.062 (largest)
                              animation: "karaoke",
                              bold: true,
                              caseTransform: "uppercase" as const,
                              outlineWidth: 20,
                              outlineColor: "#000",
                              words: ["INI", "CONTOH", "SUBTITLE", "TIKTOK"],
                              marginBottom: "18%",
                              fontSize: "13px",
                            },
                            {
                              key: "word-pop",
                              label: "Word Pop",
                              bg: "from-zinc-900 to-zinc-950",
                              // backend: font=Plus Jakarta Sans, case=upper, bold=True, outline=5px black, satu kata tengah scale pop
                              animation: "wordpop",
                              bold: true,
                              caseTransform: "uppercase" as const,
                              outlineWidth: 5,
                              outlineColor: "#000",
                              words: ["SUBTITLE", "WORD", "POP"],
                              marginBottom: "26%",
                              fontSize: "14px",
                            },
                            {
                              key: "clean-minimal",
                              label: "Clean Minimal",
                              bg: "from-zinc-900 to-zinc-950",
                              // backend: font=Helvetica, case=lower, bold=False, outline=0, fade-in
                              animation: "fadein",
                              bold: false,
                              caseTransform: "lowercase" as const,
                              outlineWidth: 0,
                              outlineColor: "transparent",
                              words: ["ini", "contoh", "subtitle", "clean", "minimal"],
                              marginBottom: "22%",
                              fontSize: "9px",
                            },
                            {
                              key: "highlight-box",
                              label: "Highlight Box",
                              bg: "from-zinc-900 to-zinc-950",
                              // backend: font=Plus Jakarta Sans, case=normal, bold=True, box_border=14px #76E600
                              animation: "box",
                              bold: true,
                              caseTransform: "none" as const,
                              outlineWidth: 0,
                              outlineColor: "transparent",
                              words: ["Ini", "Contoh", "Subtitle", "Box"],
                              marginBottom: "26%",
                            },
                            {
                              key: "neon-gradient",
                              label: "Neon Gradient",
                              bg: "from-zinc-900 to-zinc-950",
                              // backend: font=Montserrat, case=upper, bold=True, outline=2px #FFF000, blur=4
                              animation: "karaoke",
                              bold: true,
                              caseTransform: "uppercase" as const,
                              outlineWidth: 2,
                              outlineColor: "#FFF000",
                              words: ["INI", "CONTOH", "NEON", "GRADIENT"],
                              marginBottom: "26%",
                            },
                            {
                              key: "minimalist",
                              label: "Minimalist",
                              bg: "from-zinc-900 to-zinc-950",
                              // backend: font=Helvetica, case=normal, bold=False, outline=1px dark gray, fade-in
                              animation: "fadein",
                              bold: false,
                              caseTransform: "none" as const,
                              outlineWidth: 1,
                              outlineColor: "#444",
                              words: ["Ini", "Contoh", "Subtitle", "Minimalist"],
                              marginBottom: "22%",
                              fontSize: "9px",
                            },
                            {
                              key: "neon-glow",
                              label: "Neon Glow",
                              bg: "from-zinc-900 to-zinc-950",
                              // backend: font=Montserrat, case=normal, bold=True, outline=4px black, karaoke sweep
                              animation: "popup",
                              bold: true,
                              caseTransform: "none" as const,
                              outlineWidth: 4,
                              outlineColor: "#000",
                              words: ["Ini", "Contoh", "Neon", "Glow"],
                              marginBottom: "26%",
                            },
                            {
                              key: "classic-popup",
                              label: "Classic Pop-up",
                              bg: "from-zinc-900 to-zinc-950",
                              // backend: font=Helvetica, case=normal, bold=True, outline=2px black, word_popup
                              animation: "popup",
                              bold: true,
                              caseTransform: "none" as const,
                              outlineWidth: 2,
                              outlineColor: "#000",
                              words: ["Ini", "Contoh", "Subtitle", "Classic"],
                              marginBottom: "26%",
                            },
                          ] as const).map((style) => {
                            const preview = getDynamicPreviewStyles(style.key);
                            const totalWords = style.words.length;
                            const activeWordIdx = wordProgressIndex % totalWords;
                            // font-size default: word-pop bigger, tiktok bigger, rest normal
                            const fsize = (style as {fontSize?: string}).fontSize ?? "10px";

                            // text-shadow simulation of ASS outline using CSS text-shadow
                            const makeTextShadow = (ow: number, oc: string) => {
                              if (ow === 0) return "none";
                              const r = Math.min(ow, 10);
                              const shadows = [];
                              for (let dx = -r; dx <= r; dx += Math.max(1, Math.floor(r/2))) {
                                for (let dy = -r; dy <= r; dy += Math.max(1, Math.floor(r/2))) {
                                  if (dx === 0 && dy === 0) continue;
                                  shadows.push(`${dx}px ${dy}px 0 ${oc}`);
                                }
                              }
                              return shadows.join(",");
                            };
                            const textShadow = makeTextShadow(style.outlineWidth, style.outlineColor);

                            const baseWordStyle = {
                              fontFamily: preview.fontFamily,
                              fontWeight: style.bold ? "900" : "400",
                              fontSize: fsize,
                              letterSpacing: style.caseTransform === "uppercase" ? "0.04em" : "normal",
                              textTransform: style.caseTransform,
                              textShadow,
                              lineHeight: "1.3",
                            } as React.CSSProperties;

                            return (
                              <button
                                key={style.key}
                                type="button"
                                onClick={() => setSubtitleStyle(style.key)}
                                className={`relative group rounded-xl overflow-hidden border-2 transition-all duration-200 cursor-pointer ${
                                  subtitleStyle === style.key
                                    ? "border-amber-500 ring-2 ring-amber-500/30 scale-[1.02] shadow-lg shadow-amber-500/10"
                                    : "border-stone-200 dark:border-stone-700/50 hover:border-stone-400 dark:hover:border-stone-500 hover:shadow-md"
                                }`}
                              >
                                {/* Preview mockup — aspect-[9/16] simulates real 9:16 video */}
                                <div className={`aspect-[9/16] bg-gradient-to-b ${style.bg} relative overflow-hidden`}>
                                  {/* scan line effect */}
                                  <div className="absolute inset-0 bg-[repeating-linear-gradient(0deg,transparent,transparent_2px,rgba(255,255,255,0.015)_2px,rgba(255,255,255,0.015)_4px)] pointer-events-none" />
                                  {/* fake video silhouette */}
                                  <div className="absolute inset-0 flex items-center justify-center">
                                    <svg className="w-6 h-6 text-white/10" fill="currentColor" viewBox="0 0 24 24">
                                      <path d="M8 6.82v10.36c0 .79.87 1.27 1.54.84l8.14-5.18a1 1 0 000-1.69L9.54 5.98A.998.998 0 008 6.82z"/>
                                    </svg>
                                  </div>

                                  {/* subtitle area — pinned at bottom matching ASS margin_v_ratio */}
                                  <div
                                    className="absolute left-0 right-0 flex items-end justify-center px-2"
                                    style={{ bottom: (style as {marginBottom?: string}).marginBottom ?? "26%" }}
                                  >
                                    {style.animation === "box" ? (
                                      // Highlight Box — karaoke active word gets neon-border box
                                      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "3px" }}>
                                        {style.words.map((w, i) => {
                                          const isActive = i === activeWordIdx;
                                          return (
                                            <span
                                              key={i}
                                              className="transition-all duration-200"
                                              style={{
                                                ...baseWordStyle,
                                                color: customStyle
                                                  ? (isActive ? preview.highlightColor : preview.primaryColor)
                                                  : (isActive ? preview.highlightColor : "rgba(255,255,255,0.75)"),
                                                padding: isActive ? "1px 3px" : "1px 3px",
                                                boxShadow: isActive
                                                  ? `inset 0 0 0 2px ${customStyle ? preview.boxColor : "#76E600"}`
                                                  : "none",
                                                backgroundColor: isActive
                                                  ? (customStyle ? preview.boxBgColor : "rgba(118,230,0,0.15)")
                                                  : "transparent",
                                              }}
                                            >{w}</span>
                                          );
                                        })}
                                      </div>
                                    ) : style.animation === "wordpop" ? (
                                      // Word Pop — one word at a time, scale bounce
                                      <span
                                        key={activeWordIdx}
                                        className="transition-all duration-200"
                                        style={{
                                          ...baseWordStyle,
                                          color: customStyle ? preview.highlightColor : preview.primaryColor,
                                          display: "inline-block",
                                          transform: "scale(1.15)",
                                        }}
                                      >{style.words[activeWordIdx]}</span>
                                    ) : style.animation === "popup" ? (
                                      // Popup / Sweep — active word scales up, others dim
                                      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "2px" }}>
                                        {style.words.map((w, i) => {
                                          const isActive = i === activeWordIdx;
                                          return (
                                            <span
                                              key={i}
                                              className="transition-all duration-200"
                                              style={{
                                                ...baseWordStyle,
                                                display: "inline-block",
                                                color: customStyle
                                                  ? (isActive ? preview.highlightColor : preview.primaryColor)
                                                  : (isActive ? preview.highlightColor : preview.primaryColor),
                                                transform: isActive ? "scale(1.25) translateY(-1px)" : "scale(1)",
                                                opacity: isActive ? 1 : 0.6,
                                              }}
                                            >{w}</span>
                                          );
                                        })}
                                      </div>
                                    ) : style.animation === "fadein" ? (
                                      // Fade-in — words appear one by one
                                      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "2px" }}>
                                        {style.words.map((w, i) => {
                                          const isVisible = i <= activeWordIdx;
                                          return (
                                            <span
                                              key={i}
                                              className="transition-all duration-300"
                                              style={{
                                                ...baseWordStyle,
                                                color: customStyle ? preview.primaryColor : preview.primaryColor,
                                                opacity: isVisible ? 1 : 0.1,
                                              }}
                                            >{w}</span>
                                          );
                                        })}
                                      </div>
                                    ) : (
                                      // Karaoke Fill — words fill color left to right (viral-bold, tiktok, neon-gradient)
                                      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "2px" }}>
                                        {style.words.map((w, i) => {
                                          const isActive = i <= activeWordIdx;
                                          return (
                                            <span
                                              key={i}
                                              className="transition-all duration-250"
                                              style={{
                                                ...baseWordStyle,
                                                color: customStyle
                                                  ? (isActive ? preview.highlightColor : preview.primaryColor)
                                                  : (isActive ? preview.highlightColor : preview.primaryColor),
                                                opacity: isActive ? 1 : 0.45,
                                              }}
                                            >{w}</span>
                                          );
                                        })}
                                      </div>
                                    )}
                                  </div>
                                </div>
                                {/* Label */}
                                <div className={`px-2 py-2 text-[10px] font-semibold text-center tracking-wide transition-colors ${
                                  subtitleStyle === style.key
                                    ? "bg-gradient-to-r from-amber-50 to-amber-100 dark:from-amber-950/50 dark:to-amber-900/30 text-amber-700 dark:text-amber-300"
                                    : "bg-white/80 dark:bg-stone-900/80 text-stone-600 dark:text-stone-400"
                                }`}>
                                  {style.label}
                                </div>
                                {/* Checkmark */}
                                {subtitleStyle === style.key && (
                                  <div className="absolute top-1.5 right-1.5 w-5 h-5 rounded-full bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center shadow-lg shadow-amber-500/40">
                                    <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                                    </svg>
                                  </div>
                                )}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            <Button
              type="submit"
              size="lg"
              className="w-full h-12 text-base rounded-xl font-semibold bg-gradient-to-r from-amber-500 via-rose-500 to-violet-600 hover:from-amber-600 hover:via-rose-600 hover:to-violet-700 dark:from-amber-400 dark:via-rose-400 dark:to-violet-500 dark:hover:from-amber-500 dark:hover:via-rose-500 dark:hover:to-violet-600 text-white transition-all shadow-lg shadow-amber-500/20 hover:shadow-xl hover:shadow-amber-500/30 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={!isValid || submitting}
            >
              {submitting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Memulai Proses...
                </>
              ) : (
                <>
                  Hasilkan Video Shorts
                  <ArrowRight className="w-4 h-4 ml-2 group-hover:translate-x-1 transition-transform" />
                </>
              )}
            </Button>
          </form>
        </div>

        {/* Recent Tasks List */}
        {recentTasks.length > 0 && (
          <div className="space-y-4 animate-in fade-in slide-in-from-bottom-8 duration-700 delay-200">
            <div className="flex items-center gap-2 text-stone-700 dark:text-stone-300 font-semibold pb-2">
              <History className="w-4 h-4 text-amber-500" />
              <h2>Riwayat Pembuatan Klip</h2>
              <span className="ml-auto text-[11px] text-stone-400 font-normal">{recentTasks.length} tugas</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {recentTasks.map((t) => (
                <div
                  key={t.id}
                  onClick={() => router.push(`/tasks/${t.id}`)}
                  className="flex items-center justify-between p-4 rounded-xl glass-strong hover:bg-white/90 dark:hover:bg-stone-800/80 hover:shadow-lg hover:-translate-y-0.5 cursor-pointer transition-all group duration-300"
                >
                  <div className="flex items-center gap-3 overflow-hidden">
                    <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-red-50 to-rose-50 dark:from-red-950/30 dark:to-rose-950/20 flex items-center justify-center border border-red-100 dark:border-red-900/20 flex-shrink-0 group-hover:scale-110 group-hover:rotate-[-5deg] transition-all duration-300">
                      <Video className="w-5 h-5 text-red-500 dark:text-red-400" />
                    </div>
                    <div className="overflow-hidden">
                      <p className="text-sm font-medium text-stone-800 dark:text-stone-200 truncate pr-2">
                        {getCleanUrlLabel(t.url)}
                      </p>
                      <span className="flex items-center gap-1 text-[11px] text-stone-400">
                        <Clock className="w-3 h-3" />
                        {new Date(t.timestamp).toLocaleDateString("id-ID", {
                          hour: "2-digit",
                          minute: "2-digit"
                        })}
                      </span>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={(e) => removeRecentTask(t.id, e)}
                    className="text-stone-400 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/20 w-8 h-8 rounded-lg opacity-0 group-hover:opacity-100 transition-all duration-200"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              ))}
            </div>
          </div>
        )}

        <footer className="text-center text-xs text-stone-400 dark:text-stone-500 mt-20">
          <p>© {new Date().getFullYear()} Clip AI. Tanpa pendaftaran. Semua data disimpan secara lokal.</p>
        </footer>
      </div>
    </main>
  );
}

