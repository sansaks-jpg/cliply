"use client";

import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import {
  Youtube,
  Loader2,
  ArrowRight,
  Trash2,
  History,
  Video,
  Sliders,
  Sparkles,
  Languages,
  Cpu,
  Film,
  Settings,
  Smartphone,
  Monitor,
  Check,
  ExternalLink,
  ChevronDown
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ThemeToggle } from "@/components/theme-toggle";
import { API_URL, createTask, deleteTask, getAvailableEncoders, waitForBackend, type BackendStatus } from "@/lib/api";
import Link from "next/link";
import { isTauri, type AppSettings } from "@/lib/tauri";
import { SetupWizard } from "@/components/setup-wizard";

const YOUTUBE_RE =
  /^(https?:\/\/)?(www\.)?(youtube\.com\/(watch\?v=|shorts\/|embed\/|live\/)|youtu\.be\/).+/i;

interface RecentTask {
  id: string;
  url: string;
  timestamp: number;
}

const STYLE_DEFINITIONS: Record<string, {
  bold: boolean,
  caseTransform: "uppercase" | "lowercase" | "none",
  outlineWidth: number,
  outlineColor: string,
  words: string[],
  animation: string
}> = {
  "viral-bold": {
    bold: true,
    caseTransform: "uppercase",
    outlineWidth: 3,
    outlineColor: "#000000",
    words: ["KITA", "TIDAK", "HANYA", "BERPIKIR", "TETAPI", "BERTINDAK", "NYATA", "SEKARANG"],
    animation: "karaoke"
  },
  "tiktok": {
    bold: true,
    caseTransform: "uppercase",
    outlineWidth: 4,
    outlineColor: "#000000",
    words: ["INILAH", "GAYA", "TEKS", "TIKTOK"],
    animation: "karaoke"
  },
  "word-pop": {
    bold: true,
    caseTransform: "uppercase",
    outlineWidth: 4,
    outlineColor: "#000000",
    words: ["FOKUS", "CEPAT", "DAN", "SATSET"],
    animation: "wordpop"
  },
  "clean-minimal": {
    bold: false,
    caseTransform: "lowercase",
    outlineWidth: 0,
    outlineColor: "transparent",
    words: ["gaya", "minimalis", "bersih", "dan", "elegan"],
    animation: "fadein"
  },
  "highlight-box": {
    bold: true,
    caseTransform: "none",
    outlineWidth: 0,
    outlineColor: "transparent",
    words: ["Momen", "viral", "dalam", "kotak", "highlight"],
    animation: "box"
  },
  "neon-gradient": {
    bold: true,
    caseTransform: "uppercase",
    outlineWidth: 2,
    outlineColor: "#FFF000",
    words: ["TEKS", "GRADASI", "NEON", "MENYALA"],
    animation: "karaoke"
  },
  "minimalist": {
    bold: false,
    caseTransform: "none",
    outlineWidth: 1,
    outlineColor: "#444444",
    words: ["Simpel", "tanpa", "banyak", "distraksi"],
    animation: "fadein"
  },
  "neon-glow": {
    bold: true,
    caseTransform: "none",
    outlineWidth: 4,
    outlineColor: "#000000",
    words: ["Cahaya", "glamur", "efek", "neon", "glow"],
    animation: "popup"
  },
  "classic-popup": {
    bold: true,
    caseTransform: "none",
    outlineWidth: 2,
    outlineColor: "#000000",
    words: ["Gaya", "klasik", "popup", "animasi", "lembut"],
    animation: "popup"
  }
};

const getDynamicPreviewStyles = (styleKey: string) => {
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
  const fontFamily = fontMap[styleKey] ?? "Helvetica";

  const primaryMap: Record<string, string> = {
    "viral-bold":    "#FFFFFF",
    "tiktok":        "#FFFFFF",
    "word-pop":      "#FFFFFF",
    "clean-minimal": "rgba(255,255,255,0.90)",
    "highlight-box": "#FFFFFF",
    "neon-gradient": "#FFF000",
    "minimalist":    "rgba(255,255,255,0.75)",
    "neon-glow":     "#00FFFF",
    "classic-popup": "#FFFFFF",
  };
  const primaryColor = primaryMap[styleKey] ?? "#FFFFFF";

  const highlightMap: Record<string, string> = {
    "viral-bold":    "#FFFF00",
    "tiktok":        "#08E539",
    "word-pop":      "#FFFFFF",
    "clean-minimal": "rgba(255,255,255,0.50)",
    "highlight-box": "#76E600",
    "neon-gradient": "#E500FF",
    "minimalist":    "rgba(255,255,255,0.30)",
    "neon-glow":     "#FF00FF",
    "classic-popup": "#FFFF00",
  };
  const highlightColor = highlightMap[styleKey] ?? "#FFFF00";

  const boxColor = "#76E600";
  const boxBgColor = "rgba(118,230,0,0.2)";
  const outlineColor = styleKey === "neon-gradient" ? "#FFF000" : undefined;

  return { fontFamily, primaryColor, highlightColor, boxColor, boxBgColor, outlineColor };
};

const makeTextShadow = (ow: number, oc: string) => {
  if (ow === 0) return "none";
  const r = Math.min(ow, 4);
  const shadows = [];
  for (let dx = -r; dx <= r; dx += Math.max(1, Math.floor(r/2))) {
    for (let dy = -r; dy <= r; dy += Math.max(1, Math.floor(r/2))) {
      if (dx === 0 && dy === 0) continue;
      shadows.push(`${dx}px ${dy}px 0 ${oc}`);
    }
  }
  return shadows.join(",");
};

export default function Home() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [urlFocused, setUrlFocused] = useState(false);

  // Configurations
  const [numClips, setNumClips] = useState("auto");
  const [aspectRatio, setAspectRatio] = useState("9:16");
  const [language, setLanguage] = useState("auto");
  const [subtitleStyle, setSubtitleStyle] = useState("viral-bold");
  const [faceDetector, setFaceDetector] = useState("yunet");
  const [encoder, setEncoder] = useState("auto");
  const [availableEncoders, setAvailableEncoders] = useState<string[]>(["auto", "cpu"]);
  const [showAdvanced, setShowAdvanced] = useState(true);
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("checking");
  const [backendError, setBackendError] = useState<string | null>(null);

  const [isTauriApp, setIsTauriApp] = useState(false);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [showSetup, setShowSetup] = useState(false);

  useEffect(() => {
    const tauriActive = isTauri();
    setIsTauriApp(tauriActive);
    if (tauriActive) {
      import("@/lib/tauri").then(({ getSettings }) => {
        getSettings().then((s) => {
          if (s) {
            setSettings(s);
            if (s.first_run) {
              setShowSetup(true);
            }
          }
        });
      });
    }
  }, []);

  const handleSetupComplete = async (selectedPath: string) => {
    try {
      const { setStorageDir, restartBackend } = await import("@/lib/tauri");
      await setStorageDir(selectedPath);
      await restartBackend(selectedPath);
      setShowSetup(false);
      setSettings((prev: AppSettings | null) => prev ? { ...prev, storage_dir: selectedPath, first_run: false } : null);
      
      const status = await waitForBackend(15000, 1000);
      setBackendStatus(status);
      toast.success("Setup selesai! Backend berhasil dihubungkan.");
    } catch (e) {
      console.error(e);
      toast.error("Terjadi kesalahan saat menyimpan konfigurasi.");
    }
  };

  const handlePickDir = async () => {
    const { pickStorageDir } = await import("@/lib/tauri");
    return await pickStorageDir();
  };

  // Tunggu backend siap sebelum melakukan request lain (penting untuk Tauri)
  useEffect(() => {
    waitForBackend(30_000, 1_000).then((status) => {
      setBackendStatus(status);
      if (status === "ready") {
        getAvailableEncoders().then((res) => {
          setAvailableEncoders(res.available);
          setEncoder(res.current);
        }).catch((e) => { console.warn("getAvailableEncoders (poll) failed", e); });
      }
    });
  }, []);

  // Listen for Tauri backend events
  useEffect(() => {
    if (!isTauriApp) return;
    let unlisten: (() => void) | undefined;

    import("@tauri-apps/api/event").then(({ listen }) => {
      listen<string>("backend-ready", () => {
        setBackendStatus("ready");
        setBackendError(null);
        getAvailableEncoders().then((res) => {
          setAvailableEncoders(res.available);
          setEncoder(res.current);
        }).catch((e) => { console.warn("getAvailableEncoders (event) failed", e); });
      }).then((fn) => { unlisten = fn; });

      listen<string>("backend-error", (event) => {
        setBackendStatus("unavailable");
        setBackendError(event.payload);
      });

      listen<number>("backend-crashed", () => {
        setBackendStatus("unavailable");
        toast.error("Backend mati mendadak", {
          description: "Server lokal Cliply berhenti secara tidak terduga.",
          duration: 10000,
          action: {
            label: "Restart",
            onClick: async () => {
              const { restartBackend } = await import("@/lib/tauri");
              setBackendStatus("checking");
              try {
                await restartBackend(settings?.storage_dir ?? "");
              } catch (e) {
                console.error("restartBackend failed", e);
                toast.error("Gagal merestart backend");
              }
            },
          },
        });
      });
    });

    return () => { unlisten?.(); };
  }, [isTauriApp]);

  const [recentTasks, setRecentTasks] = useState<RecentTask[]>([]);

  useEffect(() => {
    // Migrate any history stored under the legacy "clip_ai_recent_tasks" key,
    // then read from the current "cliply_recent_tasks" key.
    const legacy = localStorage.getItem("clip_ai_recent_tasks");
    const current = localStorage.getItem("cliply_recent_tasks");
    const source = current ?? legacy;
    if (legacy && !current) {
      localStorage.setItem("cliply_recent_tasks", legacy);
      localStorage.removeItem("clip_ai_recent_tasks");
    }
    if (source) {
      try {
        setRecentTasks(JSON.parse(source));
      } catch (e) {
        console.warn("Failed to parse recent tasks from localStorage", e);
      }
    }
  }, []);

  // Sync recent tasks from backend on mount
  useEffect(() => {
    const syncBackendTasks = async () => {
      try {
        const res = await fetch(`${API_URL}/tasks`);
        if (!res.ok) return;
        const data = await res.json();
        const backendTasks = (data.tasks || []).map((t: any) => ({
          id: t.task_id,
          url: t.url,
          timestamp: t.created_at * 1000,
          status: t.status,
        }));
        const current = localStorage.getItem("cliply_recent_tasks");
        const localTasks: RecentTask[] = current ? JSON.parse(current) : [];
        const localIds = new Set(localTasks.map((t) => t.id));
        
        const merged = [...localTasks];
        for (const bt of backendTasks) {
          if (!localIds.has(bt.id)) {
            merged.push(bt);
            localIds.add(bt.id);
          }
        }
        merged.sort((a, b) => b.timestamp - a.timestamp);
        const trimmed = merged.slice(0, 20);
        setRecentTasks(trimmed);
        localStorage.setItem("cliply_recent_tasks", JSON.stringify(trimmed));
      } catch (e) {
        console.warn("Failed to sync tasks from backend:", e);
      }
    };
    syncBackendTasks();
  }, []);

  // Subtitle animation progress tick
  const [wordProgressIndex, setWordProgressIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setWordProgressIndex((prev) => (prev + 1) % 12);
    }, 550);
    return () => clearInterval(timer);
  }, []);

  // Memoize heavy style calculations that depend only on subtitleStyle
  const memoizedStyles = useMemo(() => {
    const activeStyle = STYLE_DEFINITIONS[subtitleStyle] || STYLE_DEFINITIONS["viral-bold"];
    const preview = getDynamicPreviewStyles(subtitleStyle);
    const textShadow = makeTextShadow(activeStyle.outlineWidth, activeStyle.outlineColor);
    return { activeStyle, preview, textShadow };
  }, [subtitleStyle]);

  const isValid = YOUTUBE_RE.test(url.trim());

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid || submitting) return;

    setSubmitting(true);
    try {
      const opts = {
        num_clips: numClips === "auto" ? 0 : parseInt(numClips, 10),
        aspect_ratio: "9:16",
        language: undefined, // Selalu autodeteksi bahasa
        subtitle_style: subtitleStyle,
        face_detector: faceDetector,
        encoder,
      };

      const { task_id } = await createTask(url.trim(), opts);

      const newTask: RecentTask = {
        id: task_id,
        url: url.trim(),
        timestamp: Date.now(),
      };
      const updated = [newTask, ...recentTasks.filter(t => t.id !== task_id)].slice(0, 6);
      setRecentTasks(updated);
      localStorage.setItem("cliply_recent_tasks", JSON.stringify(updated));

      toast.success("Tugas klip berhasil dimulai!");
      router.push(`/tasks?id=${task_id}`);
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
      const updated = recentTasks.filter(t => t.id !== id);
      setRecentTasks(updated);
      localStorage.setItem("cliply_recent_tasks", JSON.stringify(updated));
      toast.success("Riwayat tugas berhasil dihapus");
    } catch (err) {
      console.error("Gagal menghapus tugas:", err);
      toast.error("Gagal menghapus tugas dari server. Coba lagi.");
    }
  };

  const getCleanUrlLabel = (fullUrl: string) => {
    try {
      const u = new URL(fullUrl);
      if (u.hostname.includes("youtube.com")) {
        const v = u.searchParams.get("v");
        if (v) return `youtube.com/watch?v=${v}`;
        if (u.pathname.includes("shorts")) return `youtube.com/shorts/${u.pathname.split("/").pop()}`;
      } else if (u.hostname.includes("youtu.be")) {
        return `youtu.be/${u.pathname.substring(1)}`;
      }
      return fullUrl;
    } catch (e) {
      console.warn("getCleanUrlLabel: invalid URL", e);
      return fullUrl;
    }
  };

  // Loading screen saat backend sedang boot
  if (backendStatus === "checking") {
    return (
      <div className="h-screen bg-background text-foreground flex flex-col items-center justify-center gap-6 font-sans antialiased">
        <div className="fixed inset-0 pointer-events-none -z-10 overflow-hidden">
          <div className="absolute top-[-12%] left-[-8%] w-[44rem] h-[44rem] rounded-full blur-[120px] opacity-25 dark:opacity-40 bg-[radial-gradient(circle_at_center,var(--accent-violet),transparent_70%)] animate-blob" />
        </div>
        <Loader2 className="w-10 h-10 text-[var(--accent-violet)] animate-spin" />
        <div className="text-center space-y-2">
          <p className="text-lg font-semibold">Menghubungkan ke Backend...</p>
          <p className="text-sm text-muted-foreground">Menunggu server lokal Cliply siap. Ini bisa memakan waktu hingga 30 detik.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen overflow-y-auto bg-background text-foreground transition-colors duration-300 flex flex-col font-sans antialiased overflow-x-hidden relative">

      {/* Ambient violet glow blobs */}
      <div className="fixed inset-0 pointer-events-none -z-10 overflow-hidden">
        <div className="absolute top-[-12%] left-[-8%] w-[44rem] h-[44rem] rounded-full blur-[120px] opacity-25 dark:opacity-40 bg-[radial-gradient(circle_at_center,var(--accent-violet),transparent_70%)] animate-blob" />
        <div className="absolute bottom-[-18%] right-[-10%] w-[40rem] h-[40rem] rounded-full blur-[120px] opacity-20 dark:opacity-35 bg-[radial-gradient(circle_at_center,var(--accent-indigo),transparent_70%)] animate-blob-2 animation-delay-2000" />
        <div className="absolute top-[35%] right-[20%] w-[26rem] h-[26rem] rounded-full blur-[110px] opacity-10 dark:opacity-20 bg-[radial-gradient(circle_at_center,var(--accent-violet),transparent_70%)] animate-blob-3 animation-delay-4000" />
      </div>

      {/* Top Header */}
      <header className="border-b border-border/60 sticky top-0 z-30 glass">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Image
              src="/logo-rectangle.png"
              alt="cliply"
              width={240}
              height={64}
              priority
              className="h-16 w-auto"
            />
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            {isTauriApp && (
              <Link href="/settings" className="p-2 hover:bg-neutral-900 border border-transparent hover:border-neutral-800 rounded-xl transition-all" title="Pengaturan">
                <Settings className="w-5 h-5 text-neutral-300" />
              </Link>
            )}
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-5xl w-full mx-auto px-6 py-20 flex-grow flex flex-col gap-16">

        {/* Backend tidak tersedia — tampilkan banner peringatan */}
        {backendStatus === "unavailable" && (
          <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-4 flex items-start gap-3 animate-in fade-in slide-in-from-top-4 duration-500">
            <div className="w-8 h-8 rounded-lg bg-red-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
              <span className="text-red-400 text-base font-bold">!</span>
            </div>
            <div className="space-y-1 min-w-0">
              <p className="text-sm font-semibold text-red-400">Backend tidak dapat dihubungi</p>
              {backendError ? (
                <div className="space-y-1">
                  <p className="text-xs text-red-300/80 leading-relaxed break-words">{backendError}</p>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Server lokal di <code className="font-mono">localhost:8003</code> tidak merespons.
                  Pastikan backend Python sudah berjalan: <code className="font-mono">uvicorn app.main:app --port 8003</code>
                </p>
              )}
            </div>
          </div>
        )}

        {/* Hero Section */}
        <section className="text-center space-y-6 max-w-3xl mx-auto animate-in fade-in slide-in-from-bottom-4 duration-700">


          <h1
            className="text-5xl sm:text-6xl font-extrabold tracking-tight leading-[1.05]"
            style={{ fontFamily: "var(--font-display)" }}
          >
            Ubah Video Panjang
            <br />
            <span className="text-gradient-violet">Menjadi Shorts Viral</span>
          </h1>

          <p className="text-base sm:text-lg text-muted-foreground max-w-xl mx-auto leading-relaxed">
            Studio terpadu untuk ekstraksi klip viral, pelacakan wajah cerdas (Smart Crop),
            dan penempelan gaya teks karaoke secara otomatis.
          </p>
        </section>

        {/* Action Form Panel */}
        <section className="w-full space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700 delay-100">
          <form onSubmit={handleSubmit} className="w-full">
            <div
              className={`relative flex items-center p-1.5 rounded-2xl glass-panel transition-all duration-300 ${
                urlFocused
                  ? "ring-2 ring-[var(--accent-violet)]/40 glow-accent-md"
                  : "ring-1 ring-border/40"
              }`}
            >
              <Youtube className="absolute left-4 w-5 h-5 text-muted-foreground" />
              <Input
                id="youtube-url"
                type="url"
                placeholder="Tempel tautan video YouTube di sini..."
                aria-label="Tautan video YouTube"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onFocus={() => setUrlFocused(true)}
                onBlur={() => setUrlFocused(false)}
                className="h-12 pl-11 pr-36 text-sm font-medium border-0 bg-transparent focus-visible:ring-0 focus-visible:ring-offset-0 placeholder:text-muted-foreground/60 w-full shadow-none"
                autoFocus
              />
              <Button
                type="submit"
                disabled={!isValid || submitting}
                className="absolute right-2 h-9 px-5 rounded-xl bg-gradient-violet hover:opacity-90 text-white font-bold text-sm transition-all disabled:opacity-30 disabled:cursor-default shadow-md flex items-center gap-1.5 [&_svg]:size-4"
              >
                {submitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Memproses</span>
                  </>
                ) : (
                  <>
                    <span>Buat Klip</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </Button>
            </div>
          </form>

          {/* Quick Toggle Configuration Drawer */}
          <div className="rounded-2xl glass-panel overflow-hidden">
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              aria-expanded={showAdvanced}
              aria-controls="advanced-settings-panel"
              className="w-full px-5 py-4 flex items-center justify-between font-bold text-xs uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            >
              <div className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-[var(--accent-violet)]" />
                <span>Pengaturan & Gaya Subtitle</span>
              </div>
              <ChevronDown className={`w-4 h-4 transition-transform duration-300 ${showAdvanced ? "rotate-180" : ""}`} />
            </button>

            {showAdvanced && (
              <div id="advanced-settings-panel" className="p-5 grid grid-cols-1 lg:grid-cols-12 gap-8 items-start border-t border-border/40">
                {/* Left Side: Parameters */}
                <div className="lg:col-span-7 space-y-5">
                  <div className="flex items-center gap-2">
                    <Settings className="w-4 h-4 text-[var(--accent-violet)]" />
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Parameter Studio</span>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="num-clips" className="text-xs font-bold text-muted-foreground flex items-center gap-1.5">
                      <Film className="w-3.5 h-3.5" />
                      Target Klip
                    </Label>
                    <Select value={numClips} onValueChange={setNumClips}>
                      <SelectTrigger id="num-clips" className="bg-background/40 border-border rounded-xl h-10 text-sm font-semibold shadow-none">
                        <SelectValue placeholder="Jumlah Klip" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="auto">Auto (Rekomendasi AI)</SelectItem>
                        <SelectItem value="3">3 Klip Video</SelectItem>
                        <SelectItem value="5">5 Klip Video</SelectItem>
                        <SelectItem value="10">10 Klip Video</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="face-detector" className="text-xs font-bold text-muted-foreground flex items-center gap-1.5">
                      <Sliders className="w-3.5 h-3.5" />
                      Face Tracker
                    </Label>
                    <Select value={faceDetector} onValueChange={setFaceDetector}>
                      <SelectTrigger id="face-detector" className="bg-background/40 border-border rounded-xl h-10 text-sm font-semibold shadow-none">
                        <SelectValue placeholder="Detektor Wajah" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="yunet">YuNet (Akurat)</SelectItem>
                        <SelectItem value="mediapipe">MediaPipe BlazeFace (Cepat)</SelectItem>
                        <SelectItem value="yolov8-face">YOLOv8-Face (Terbaik)</SelectItem>
                        <SelectItem value="ssd">SSD ResNet (Ringan)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Gaya Subtitle Section */}
                  <div className="space-y-3 pt-2">
                    <div className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-[var(--accent-violet)]" />
                      <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Gaya Subtitle</span>
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                      {(["viral-bold", "tiktok", "word-pop", "clean-minimal", "highlight-box", "minimalist", "neon-glow", "classic-popup"] as const).map((styleKey) => {
                        const isActive = subtitleStyle === styleKey;
                        return (
                          <button
                            key={styleKey}
                            type="button"
                            onClick={() => setSubtitleStyle(styleKey)}
                            className={`text-xs font-bold px-3 py-2.5 rounded-xl border transition-all text-left flex items-center justify-between cursor-pointer ${
                              isActive
                                ? "bg-gradient-violet border-transparent text-white shadow-md glow-accent"
                                : "bg-background/40 border-border text-muted-foreground hover:bg-secondary/60"
                            }`}
                          >
                            <span className="capitalize">{styleKey.replace(/-/g, " ")}</span>
                            {isActive && <Check className="w-3.5 h-3.5" />}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>

                {/* Right Side: Live 9:16 Phone Preview */}
                <div className="lg:col-span-5 flex flex-col items-center justify-center space-y-4 py-4 min-h-[360px]">
                  <div className="text-center w-full">
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground block mb-2">Live Preview Subtitle</span>
                  </div>

                  <div className="relative">
                    {/* Violet glow halo behind phone */}
                    <div className="absolute inset-0 rounded-[2.2rem] bg-[var(--accent-violet)] opacity-20 blur-3xl scale-110 pointer-events-none" />

                    <div className="relative w-[210px] aspect-[9/16] rounded-[2.2rem] overflow-hidden bg-black border-[4px] border-zinc-800 dark:border-zinc-700/80 shadow-2xl flex flex-col">
                      {/* Notch */}
                      <div className="absolute top-2 left-1/2 -translate-x-1/2 w-16 h-4 rounded-full bg-black z-20 flex items-center justify-center">
                        <div className="w-1.5 h-1.5 rounded-full bg-zinc-700" />
                      </div>

                      {/* Simulated abstract video bg */}
                      <div className="absolute inset-0 bg-gradient-to-br from-zinc-900 via-[#15101f] to-zinc-950 pointer-events-none" />
                      <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,rgba(124,58,237,0.18),transparent_60%)] pointer-events-none" />

                      {/* Top audio bars */}
                      <div className="absolute top-6 left-3 flex gap-0.5 items-end h-4 pointer-events-none opacity-30">
                        <div className="w-0.5 bg-white rounded-full animate-bounce h-2" style={{ animationDelay: "0.1s" }} />
                        <div className="w-0.5 bg-white rounded-full animate-bounce h-3.5" style={{ animationDelay: "0.3s" }} />
                        <div className="w-0.5 bg-white rounded-full animate-bounce h-1.5" style={{ animationDelay: "0.5s" }} />
                        <div className="w-0.5 bg-white rounded-full animate-bounce h-2.5" style={{ animationDelay: "0.2s" }} />
                      </div>

                      <span className="absolute top-6 right-3 text-[7px] font-bold text-white/40 uppercase tracking-wider z-10">
                        Live
                      </span>

                      {/* Rendering Subtitle Text */}
                      <div className="w-full h-full z-10 flex items-end justify-center text-center pb-12 px-3">
                        {(() => {
                          const { activeStyle, preview, textShadow } = memoizedStyles;
                          const totalWords = activeStyle.words.length;
                          const activeWordIdx = wordProgressIndex % totalWords;
                          const fsize = "11px";

                          const baseWordStyle = {
                            fontFamily: preview.fontFamily,
                            fontWeight: activeStyle.bold ? "900" : "400",
                            fontSize: fsize,
                            letterSpacing: activeStyle.caseTransform === "uppercase" ? "0.05em" : "normal",
                            textTransform: activeStyle.caseTransform,
                            textShadow,
                            lineHeight: "1.3",
                          } as React.CSSProperties;

                          return (
                            <div className="w-full flex items-end justify-center text-center">
                              {activeStyle.animation === "box" ? (
                                <div className="flex flex-wrap justify-center gap-1">
                                  {activeStyle.words.map((w, i) => {
                                    const isActive = i === activeWordIdx;
                                    return (
                                      <span
                                        key={i}
                                        style={{
                                          ...baseWordStyle,
                                          color: isActive ? preview.highlightColor : preview.primaryColor,
                                          padding: "1px 4px",
                                          borderRadius: "3px",
                                          boxShadow: isActive ? `inset 0 0 0 1px ${preview.boxColor}` : "none",
                                          backgroundColor: isActive ? preview.boxBgColor : "transparent",
                                        }}
                                      >{w}</span>
                                    );
                                  })}
                                </div>
                              ) : activeStyle.animation === "wordpop" ? (
                                <span
                                  key={activeWordIdx}
                                  className="transition-transform duration-200"
                                  style={{
                                    ...baseWordStyle,
                                    color: preview.highlightColor,
                                    display: "inline-block",
                                    transform: "scale(1.2)",
                                  }}
                                >{activeStyle.words[activeWordIdx]}</span>
                              ) : activeStyle.animation === "popup" ? (
                                <div className="flex flex-wrap justify-center gap-1">
                                  {activeStyle.words.map((w, i) => {
                                    const isActive = i === activeWordIdx;
                                    return (
                                      <span
                                        key={i}
                                        className="transition-all duration-200"
                                        style={{
                                          ...baseWordStyle,
                                          display: "inline-block",
                                          color: isActive ? preview.highlightColor : preview.primaryColor,
                                          transform: isActive ? "scale(1.2) translateY(-1.5px)" : "scale(1)",
                                          opacity: isActive ? 1 : 0.65,
                                        }}
                                      >{w}</span>
                                    );
                                  })}
                                </div>
                              ) : activeStyle.animation === "fadein" ? (
                                <div className="flex flex-wrap justify-center gap-1">
                                  {activeStyle.words.map((w, i) => {
                                    const isVisible = i <= activeWordIdx;
                                    return (
                                      <span
                                        key={i}
                                        className="transition-opacity duration-300"
                                        style={{
                                          ...baseWordStyle,
                                          color: preview.primaryColor,
                                          opacity: isVisible ? 1 : 0.15,
                                        }}
                                      >{w}</span>
                                    );
                                  })}
                                </div>
                              ) : (
                                // Karaoke Fill
                                <div className="flex flex-wrap justify-center gap-1">
                                  {activeStyle.words.map((w, i) => {
                                    const isActive = i <= activeWordIdx;
                                    return (
                                      <span
                                        key={i}
                                        className="transition-all duration-150"
                                        style={{
                                          ...baseWordStyle,
                                          color: isActive ? preview.highlightColor : preview.primaryColor,
                                          opacity: isActive ? 1 : 0.5,
                                        }}
                                      >{w}</span>
                                    );
                                  })}
                                </div>
                              )}
                            </div>
                          );
                        })()}
                      </div>

                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Recent Project Workspace Cards */}
        {recentTasks.length > 0 && (
          <section className="space-y-5 animate-in fade-in duration-700">
            <div className="flex items-center gap-2 text-muted-foreground font-bold text-xs uppercase tracking-wider">
              <History className="w-4 h-4 text-[var(--accent-violet)]" />
              <span>Riwayat Workspace Proyek</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {recentTasks.map((t) => (
                <div
                  key={t.id}
                  className="relative group rounded-2xl glass-panel p-4 hover:glow-accent hover:border-[var(--accent-violet)]/30 transition-all duration-300 flex items-center justify-between gap-4 focus-within:ring-2 focus-within:ring-[var(--accent-violet)]"
                >
                  <div className="space-y-2 overflow-hidden flex-grow">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-xl bg-gradient-violet/15 flex items-center justify-center flex-shrink-0 group-hover:bg-gradient-violet group-hover:text-white text-[var(--accent-violet)] transition-all">
                        <Video className="w-4 h-4" />
                      </div>
                      <div className="overflow-hidden">
                        <h4 className="text-sm font-bold truncate">
                          <Link href={`/tasks?id=${t.id}`} className="focus-visible:outline-none before:absolute before:inset-0">
                            {getCleanUrlLabel(t.url)}
                          </Link>
                        </h4>
                        <span className="text-xs text-muted-foreground font-mono block">
                          ID: {t.id.slice(0, 8)}...
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="relative z-10 flex items-center gap-1 flex-shrink-0">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={(e) => removeRecentTask(t.id, e)}
                      aria-label="Delete history"
                      title="Delete history"
                      className="text-muted-foreground hover:text-red-500 hover:bg-red-500/10 w-9 h-9 rounded-lg opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                    <div className="w-9 h-9 rounded-lg bg-secondary/60 flex items-center justify-center text-muted-foreground group-hover:text-[var(--accent-violet)] transition-all">
                      <ExternalLink className="w-4 h-4" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}


      </main>

      {/* Footer */}
      <footer className="border-t border-border/60 py-8 text-center text-xs text-muted-foreground">
        <p>© {new Date().getFullYear()} cliply</p>
      </footer>
      {showSetup && settings && (
        <SetupWizard
          defaultStorageDir={settings.storage_dir}
          onPickDir={handlePickDir}
          onComplete={handleSetupComplete}
        />
      )}
    </div>
  );
}
