"use client";

import React, { useState, useEffect, useRef } from "react";
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
  Film,
  Settings,
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
    outlineColor: "#00F0FF",
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

const getDynamicPreviewStyles = (styleKey: string, colorPrimary?: string, colorHighlight?: string) => {
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
    "neon-gradient": "#00F0FF",
    "minimalist":    "rgba(255,255,255,0.75)",
    "neon-glow":     "#00FFFF",
    "classic-popup": "#FFFFFF",
  };
  const primaryColor = primaryMap[styleKey] ?? "#FFFFFF";

  const highlightMap: Record<string, string> = {
    "viral-bold":    "#FFFF00",
    "tiktok":        "#39E508",
    "word-pop":      "#FFFFFF",
    "clean-minimal": "rgba(255,255,255,0.50)",
    "highlight-box": "#00E676",
    "neon-gradient": "#FF00E5",
    "minimalist":    "rgba(255,255,255,0.30)",
    "neon-glow":     "#FF00FF",
    "classic-popup": "#FFFF00",
  };
  const highlightColor = highlightMap[styleKey] ?? "#FFFF00";

  // Override dengan warna kustom jika disediakan
  const finalPrimaryColor = colorPrimary || primaryColor;
  const finalHighlightColor = colorHighlight || highlightColor;

  const boxColor = finalHighlightColor;
  const boxBgColor = finalHighlightColor.startsWith("#") ? `${finalHighlightColor}33` : "rgba(124,58,237,0.2)";
  const outlineColor = styleKey === "neon-gradient" ? finalPrimaryColor : undefined;

  return { fontFamily, primaryColor: finalPrimaryColor, highlightColor: finalHighlightColor, boxColor, boxBgColor, outlineColor };
};

const _shadowCache = new Map<string, string>();
const makeTextShadow = (ow: number, oc: string) => {
  if (ow === 0) return "none";
  const cacheKey = `${ow}-${oc}`;
  if (_shadowCache.has(cacheKey)) return _shadowCache.get(cacheKey) as string;

  const r = Math.min(ow, 4);
  const shadows = [];
  for (let dx = -r; dx <= r; dx += Math.max(1, Math.floor(r/2))) {
    for (let dy = -r; dy <= r; dy += Math.max(1, Math.floor(r/2))) {
      if (dx === 0 && dy === 0) continue;
      shadows.push(`${dx}px ${dy}px 0 ${oc}`);
    }
  }
  const result = shadows.join(",");
  _shadowCache.set(cacheKey, result);
  return result;
};

// Memoize AnimatedWordPreview to prevent unnecessary re-renders
const AnimatedWordPreview = React.memo(({ words, sDef, pStyle }: {
  words: string[],
  sDef: { outlineWidth: number, outlineColor: string, animation: string, caseTransform: "uppercase" | "lowercase" | "none", bold: boolean },
  pStyle: { primaryColor: string, highlightColor: string, boxBgColor: string, boxColor: string, fontFamily: string }
}) => {
  const [wordProgressIndex, setWordProgressIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setWordProgressIndex((prev) => (prev + 1) % 12);
    }, 550);
    return () => clearInterval(timer);
  }, []);

  const totalW = words.length;

  return (
    <div className="w-full py-1.5 px-2 rounded-lg bg-black/95 flex items-center justify-center min-h-[32px] border border-zinc-800/80 shadow-inner overflow-hidden select-none mt-2">
      <div className="flex flex-wrap justify-center gap-1">
        {words.map((w, i) => {
          const isActiveWord = i === (wordProgressIndex % totalW);

          // Word Pop (word_pop_scale) hanya menampilkan satu kata aktif saja pada satu waktu
          if (sDef.animation === "wordpop" && !isActiveWord) {
            return null;
          }

          const isPastWord = i <= (wordProgressIndex % totalW);

          let color = pStyle.primaryColor;
          let scale = "scale(1)";
          let translate = "translateY(0)";
          let opacity = 1;
          let bg = "transparent";
          let shadow = "none";
          let padding = "0px";
          let borderRadius = "0px";

          if (sDef.animation === "box") {
            color = isActiveWord ? pStyle.highlightColor : pStyle.primaryColor;
            bg = isActiveWord ? pStyle.boxBgColor : "transparent";
            shadow = isActiveWord ? `inset 0 0 0 1px ${pStyle.boxColor}` : "none";
            padding = "1px 4px";
            borderRadius = "2px";
          } else if (sDef.animation === "wordpop") {
            scale = "scale(1.2)";
            color = pStyle.highlightColor;
            opacity = 1;
          } else if (sDef.animation === "popup") {
            color = isActiveWord ? pStyle.highlightColor : pStyle.primaryColor;
            scale = isActiveWord ? "scale(1.15)" : "scale(1)";
            translate = isActiveWord ? "translateY(-1px)" : "translateY(0)";
            opacity = isActiveWord ? 1 : 0.5;
          } else if (sDef.animation === "fadein") {
            opacity = isPastWord ? 1 : 0.15;
          } else { // karaoke
            color = isPastWord ? pStyle.highlightColor : pStyle.primaryColor;
            opacity = isPastWord ? 1 : 0.55;
          }

          return (
            <span
              key={i}
              className="transition-all duration-200 inline-block font-black preview-word"
              style={{
                fontFamily: pStyle.fontFamily,
                color,
                textShadow: makeTextShadow(sDef.outlineWidth, sDef.outlineColor),
                textTransform: sDef.caseTransform,
                fontWeight: sDef.bold ? "900" : "400",
                fontSize: "10px",
                letterSpacing: sDef.caseTransform === "uppercase" ? "0.02em" : "normal",
                lineHeight: "1.1",
                transform: `${scale} ${translate}`,
                opacity,
                backgroundColor: bg,
                boxShadow: shadow,
                padding,
                borderRadius,
              }}
            >
              {w}
            </span>
          );
        })}
      </div>
    </div>
  );
});
AnimatedWordPreview.displayName = "AnimatedWordPreview";

export default function Home() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [urlFocused, setUrlFocused] = useState(false);

  // localStorage helpers
  const _lsGet = (key: string, fallback: string) => {
    if (typeof window === "undefined") return fallback;
    return localStorage.getItem(`cliply_${key}`) || fallback;
  };
  const _lsSet = (key: string, value: string) => {
    if (typeof window !== "undefined") localStorage.setItem(`cliply_${key}`, value);
  };

  // Configurations (persisted in localStorage)
  const [numClips, setNumClips] = useState(() => _lsGet("numClips", "auto"));
  const [subtitleStyle, setSubtitleStyle] = useState(() => _lsGet("subtitleStyle", "viral-bold"));
  const [faceDetector, setFaceDetector] = useState(() => {
    const val = _lsGet("faceDetector", "yolov8-face");
    return (val === "yolov8-face" || val === "yunet") ? val : "yolov8-face";
  });
  const [subtitleColorPrimary, setSubtitleColorPrimary] = useState(() => _lsGet("subtitleColorPrimary", ""));
  const [subtitleColorHighlight, setSubtitleColorHighlight] = useState(() => _lsGet("subtitleColorHighlight", ""));
  const [showColorPicker, setShowColorPicker] = useState(false);
  const [encoder, setEncoder] = useState(() => _lsGet("encoder", "auto"));
  const [template, setTemplate] = useState(() => _lsGet("template", "podcast"));
  const [sensitivity] = useState(50);  // [DEPRECATED] — auto-tuned per model
  const [videoPreview, setVideoPreview] = useState<{title: string; author: string; thumbnail: string} | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [activeTasks, setActiveTasks] = useState<Array<{task_id: string; url: string; progress: number; status: string}>>([]);
  const [showAdvanced, setShowAdvanced] = useState(true);
  const [showAllStyles, setShowAllStyles] = useState(false);
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("checking");
  const [backendError, setBackendError] = useState<string | null>(null);

  const videoRefSource = useRef<HTMLVideoElement>(null);
  const videoRefResult = useRef<HTMLVideoElement>(null);

  // Sync video times for podcast comparison
  useEffect(() => {
    const source = videoRefSource.current;
    const result = videoRefResult.current;
    if (!source || !result) return;

    const handleTimeUpdate = () => {
      if (Math.abs(source.currentTime - result.currentTime) > 0.15) {
        result.currentTime = source.currentTime;
      }
    };

    const handlePlay = () => {
      result.play().catch(() => {});
    };

    const handlePause = () => {
      result.pause();
    };

    source.addEventListener("timeupdate", handleTimeUpdate);
    source.addEventListener("play", handlePlay);
    source.addEventListener("pause", handlePause);

    return () => {
      source.removeEventListener("timeupdate", handleTimeUpdate);
      source.removeEventListener("play", handlePlay);
      source.removeEventListener("pause", handlePause);
    };
  }, [template]);

  const [podcastHorizSrc, setPodcastHorizSrc] = useState("");
  const [podcastShortSrc, setPodcastShortSrc] = useState("");
  const [gamingHorizSrc, setGamingHorizSrc] = useState("");
  const [gamingShortSrc, setGamingShortSrc] = useState("");

  // Convert horizontal and vertical preview videos to Blob URLs to prevent direct downloads/inspection
  useEffect(() => {
    let pHorizUrl = "";
    let pShortUrl = "";
    let gHorizUrl = "";
    let gShortUrl = "";

    fetch("/examples/podcast_horizontal.mp4?v=1")
      .then((res) => res.blob())
      .then((blob) => {
        pHorizUrl = URL.createObjectURL(blob);
        setPodcastHorizSrc(pHorizUrl);
      })
      .catch((err) => console.error("Error loading horizontal podcast video blob:", err));

    fetch("/examples/podcast_short.mp4?v=1")
      .then((res) => res.blob())
      .then((blob) => {
        pShortUrl = URL.createObjectURL(blob);
        setPodcastShortSrc(pShortUrl);
      })
      .catch((err) => console.error("Error loading short podcast video blob:", err));

    fetch("/examples/gaming_horizontal.mp4?v=1")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.blob();
      })
      .then((blob) => {
        gHorizUrl = URL.createObjectURL(blob);
        setGamingHorizSrc(gHorizUrl);
      })
      .catch((err) => {
        console.warn("Gaming horizontal video unavailable:", err.message);
      });

    fetch("/examples/gaming_short.mp4?v=1")
      .then((res) => res.blob())
      .then((blob) => {
        gShortUrl = URL.createObjectURL(blob);
        setGamingShortSrc(gShortUrl);
      })
      .catch((err) => console.error("Error loading short gaming video blob:", err));

    return () => {
      if (pHorizUrl) URL.revokeObjectURL(pHorizUrl);
      if (pShortUrl) URL.revokeObjectURL(pShortUrl);
      if (gHorizUrl) URL.revokeObjectURL(gHorizUrl);
      if (gShortUrl) URL.revokeObjectURL(gShortUrl);
    };
  }, []);


  const [isTauriApp, setIsTauriApp] = useState(false);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const settingsRef = useRef<AppSettings | null>(null);
  useEffect(() => {
    settingsRef.current = settings;
  }, [settings]);
  const [showSetup, setShowSetup] = useState(false);

  // Persist settings to localStorage on change
  useEffect(() => { _lsSet("numClips", numClips); }, [numClips]);
  useEffect(() => { _lsSet("subtitleStyle", subtitleStyle); }, [subtitleStyle]);
  useEffect(() => { _lsSet("faceDetector", faceDetector); }, [faceDetector]);
  useEffect(() => { _lsSet("encoder", encoder); }, [encoder]);
  useEffect(() => { _lsSet("template", template); }, [template]);
  useEffect(() => { _lsSet("subtitleColorPrimary", subtitleColorPrimary); }, [subtitleColorPrimary]);
  useEffect(() => { _lsSet("subtitleColorHighlight", subtitleColorHighlight); }, [subtitleColorHighlight]);

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

  // Active tasks polling
  useEffect(() => {
    const fn = async () => {
      try {
        const res = await fetch(API_URL + '/tasks');
        if (res.ok) { const data = await res.json(); setActiveTasks((data.tasks||[]).filter((t: {status:string}) => t.status === 'processing' || t.status === 'queued')); }
      } catch (e) {
        console.warn("Failed to poll active tasks:", e);
      }
    };
    fn(); const id = setInterval(fn, 10000); return () => clearInterval(id);
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
          setEncoder(res.current);
        }).catch((e) => { console.warn("getAvailableEncoders (poll) failed", e); });
      }
    });
  }, []);

  // Listen for Tauri backend events
  useEffect(() => {
    if (!isTauriApp) return;
    let unlistenReady: (() => void) | undefined;
    let unlistenError: (() => void) | undefined;
    let unlistenCrashed: (() => void) | undefined;

    import("@tauri-apps/api/event").then(({ listen }) => {
      listen<string>("backend-ready", () => {
        setBackendStatus("ready");
        setBackendError(null);
        getAvailableEncoders().then((res) => {
          setEncoder(res.current);
        }).catch((e) => { console.warn("getAvailableEncoders (event) failed", e); });
      }).then((fn) => { unlistenReady = fn; });

      listen<string>("backend-error", (event) => {
        setBackendStatus("unavailable");
        setBackendError(event.payload);
      }).then((fn) => { unlistenError = fn; });

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
                await restartBackend(settingsRef.current?.storage_dir ?? "");
              } catch (e) {
                console.error("restartBackend failed", e);
                toast.error("Gagal merestart backend");
              }
            },
          },
        });
      }).then((fn) => { unlistenCrashed = fn; });
    });

    return () => {
      unlistenReady?.();
      unlistenError?.();
      unlistenCrashed?.();
    };
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
        const backendTasks = (data.tasks || []).map((t: { task_id: string; url: string; created_at: number; status: string }) => ({
          id: t.task_id,
          url: t.url,
          timestamp: t.created_at * 1000,
          status: t.status,
        }));
        const current = localStorage.getItem("cliply_recent_tasks");
        let localTasks: RecentTask[] = [];
        if (current) {
          try {
            localTasks = JSON.parse(current);
          } catch (e) {
            console.warn("Failed to parse local tasks", e);
          }
        }
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

  const isValid = YOUTUBE_RE.test(url.trim());

  // Step 1: Fetch video preview
  const handlePreview = async () => {
    if (!isValid || previewLoading) return;
    setPreviewLoading(true);
    setVideoPreview(null);
    try {
      const res = await fetch(API_URL + '/video-info?url=' + encodeURIComponent(url.trim()));
      if (!res.ok) throw new Error("Gagal mengambil info video");
      const data = await res.json();
      if (!data.title) throw new Error("Video tidak ditemukan atau tidak valid");
      setVideoPreview({ title: data.title, author: data.author || "", thumbnail: data.thumbnail || "" });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Gagal mengambil info video.");
      setVideoPreview(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  // UX: Auto-fetch preview video secara background ketika user menempel URL YouTube yang valid
  useEffect(() => {
    const trimmedUrl = url.trim();
    if (YOUTUBE_RE.test(trimmedUrl)) {
      const timer = setTimeout(() => {
        if (!videoPreview && !previewLoading) {
          void handlePreview();
        }
      }, 300);
      return () => clearTimeout(timer);
    } else {
      setVideoPreview(null);
    }
  }, [url]);

  // Step 2: Submit task to backend
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!videoPreview || submitting || previewLoading) return;

    setSubmitting(true);
    try {
      const opts = {
        num_clips: numClips === "auto" ? 0 : parseInt(numClips, 10),
        aspect_ratio: "9:16",
        language: undefined, // Selalu autodeteksi bahasa
        subtitle_style: subtitleStyle,
        face_detector: faceDetector,
        template,
        encoder,
        sensitivity,
        subtitle_color_primary: subtitleColorPrimary || undefined,
        subtitle_color_highlight: subtitleColorHighlight || undefined,
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
    } catch {
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
              <Link href="/settings" className="p-2 hover:bg-neutral-900 border border-transparent hover:border-neutral-800 rounded-xl transition-all" title="Pengaturan" aria-label="Pengaturan">
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

        {/* Active Tasks Banner */}
        {activeTasks.length > 0 && (
          <div className="mb-4 mx-auto max-w-3xl w-full bg-gradient-to-r from-[var(--accent-violet)]/10 to-[var(--accent-indigo)]/10 border border-[var(--accent-violet)]/30 rounded-2xl p-3 space-y-2 animate-in fade-in slide-in-from-top-4 duration-500">
            {activeTasks.slice(0, 3).map((t) => (
              <Link key={t.task_id} href={`/tasks?id=${t.task_id}`} className="flex items-center gap-3 hover:opacity-80 transition-opacity">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--accent-violet)] opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-[var(--accent-violet)]"></span>
                </span>
                <span className="text-sm font-medium truncate">{t.url?.slice(0, 60)}</span>
                <span className="text-xs text-muted-foreground ml-auto">{Math.round(t.progress)}%</span>
              </Link>
            ))}
            {activeTasks.length > 3 && <p className="text-xs text-muted-foreground">+{activeTasks.length - 3} tugas lagi</p>}
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
                onChange={(e) => { setUrl(e.target.value); if (videoPreview) setVideoPreview(null); }}
                onFocus={() => setUrlFocused(true)}
                onBlur={() => setUrlFocused(false)}
                className="h-12 pl-11 text-sm font-medium border-0 bg-transparent focus-visible:ring-0 focus-visible:ring-offset-0 placeholder:text-muted-foreground/60 w-full shadow-none"
                autoFocus
              />
              <Button
                type="submit"
                disabled={!isValid || submitting || previewLoading || !videoPreview}
                className="h-9 px-5 rounded-xl bg-gradient-violet hover:opacity-90 font-bold text-sm transition-all disabled:opacity-30 disabled:cursor-default shadow-md flex items-center gap-1.5 [&_svg]:size-4"
              >
                {previewLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Memuat Info...</span>
                  </>
                ) : !videoPreview && isValid ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Menunggu Info...</span>
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

          {/* Video Preview Card */}
          {videoPreview && (
            <div className="w-full rounded-2xl glass-panel p-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
              <div className="flex gap-4 items-start">
                {videoPreview.thumbnail && (
                  <div className="relative shrink-0 w-40 aspect-video rounded-xl overflow-hidden bg-muted">
                    <Image
                      src={videoPreview.thumbnail}
                      alt={videoPreview.title}
                      fill
                      className="object-cover"
                      unoptimized
                    />
                  </div>
                )}
                <div className="flex-1 min-w-0 space-y-1">
                  <p className="text-sm font-bold leading-snug line-clamp-2">{videoPreview.title}</p>
                  {videoPreview.author && (
                    <p className="text-xs text-muted-foreground">{videoPreview.author}</p>
                  )}
                  <p className="text-[10px] text-muted-foreground/60 truncate">{url.trim()}</p>
                </div>
                <button
                  type="button"
                  onClick={() => { setVideoPreview(null); }}
                  className="shrink-0 w-7 h-7 rounded-full bg-muted hover:bg-destructive/20 hover:text-destructive text-muted-foreground flex items-center justify-center transition-colors cursor-pointer"
                  aria-label="Batal preview"
                >
                  <span className="text-xs font-bold">✕</span>
                </button>
              </div>
            </div>
          )}

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
                <div className="lg:col-span-6 space-y-5">
                  <div className="flex items-center gap-2">
                    <Settings className="w-4 h-4 text-[var(--accent-violet)]" />
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Parameter Studio</span>
                  </div>

                  {/* Template Selection */}
                  <div className="space-y-3">
                    <Label className="text-xs font-bold text-muted-foreground flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-[var(--accent-violet)]" />
                      Pilih Template Video
                    </Label>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {/* Podcast Card */}
                      <div
                        onClick={() => setTemplate("podcast")}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            setTemplate("podcast");
                          }
                        }}
                        tabIndex={0}
                        role="button"
                        className={`p-4 rounded-xl border-2 transition-all duration-300 cursor-pointer flex flex-col justify-between ${
                          template === "podcast"
                            ? "border-[var(--accent-violet)] bg-[var(--accent-violet)]/5 shadow-md shadow-[var(--accent-violet)]/5"
                            : "border-border hover:border-border/80 hover:bg-muted/30"
                        }`}
                      >
                        <div>
                          <div className="flex items-center justify-between mb-2">
                            <span className="font-bold text-sm">Podcast / Long-to-Short</span>
                            {template === "podcast" && (
                              <div className="w-4 h-4 rounded-full bg-[var(--accent-violet)] text-white flex items-center justify-center">
                                <Check className="w-2.5 h-2.5" />
                              </div>
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground leading-relaxed">
                            Mendeteksi wajah pembicara utama secara dinamis ke rasio 9:16 vertikal. Ideal untuk wawancara, monolog, dan podcast.
                          </p>
                        </div>
                      </div>

                      {/* Gaming ML Card */}
                      <div
                        onClick={() => setTemplate("gaming")}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            setTemplate("gaming");
                          }
                        }}
                        tabIndex={0}
                        role="button"
                        className={`p-4 rounded-xl border-2 transition-all duration-300 cursor-pointer flex flex-col justify-between ${
                          template === "gaming"
                            ? "border-[var(--accent-violet)] bg-[var(--accent-violet)]/5 shadow-md shadow-[var(--accent-violet)]/5"
                            : "border-border hover:border-border/80 hover:bg-muted/30"
                        }`}
                      >
                        <div>
                          <div className="flex items-center justify-between mb-2">
                            <span className="font-bold text-sm">Gaming Mobile Legends</span>
                            {template === "gaming" && (
                              <div className="w-4 h-4 rounded-full bg-[var(--accent-violet)] text-white flex items-center justify-center">
                                <Check className="w-2.5 h-2.5" />
                              </div>
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground leading-relaxed">
                            Membagi layar secara vertikal: bagian atas diisi oleh crop webcam wajah streamer, bagian bawah diisi arena gameplay ML.
                          </p>
                        </div>
                      </div>
                    </div>
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
                        <SelectItem value="1">1 Klip Video</SelectItem>
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
                        <SelectItem value="yolov8-face">YOLOv8-Face (Terbaik)</SelectItem>
                        <SelectItem value="yunet">YuNet (Akurat)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Gaya Subtitle Section */}
                  <div className="space-y-3 pt-2">
                    <div className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-[var(--accent-violet)]" />
                      <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Gaya Subtitle</span>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      {(() => {
                        const allStylesKeys = ["viral-bold", "tiktok", "word-pop", "clean-minimal", "highlight-box", "minimalist", "neon-glow", "classic-popup"] as const;
                        const visibleStyles = showAllStyles ? allStylesKeys : allStylesKeys.slice(0, 4);

                        return visibleStyles.map((styleKey) => {
                          const isActive = subtitleStyle === styleKey;
                          const sDef = STYLE_DEFINITIONS[styleKey];
                          const pStyle = getDynamicPreviewStyles(styleKey, subtitleColorPrimary || undefined, subtitleColorHighlight || undefined);
                          const words = styleKey.replace(/-/g, " ").split(" ");

                          return (
                            <button
                              key={styleKey}
                              type="button"
                              onClick={() => setSubtitleStyle(styleKey)}
                              aria-pressed={isActive}
                              aria-label={`Gaya subtitle ${styleKey.replace(/-/g, " ")}`}
                              className={`px-4 py-4 min-h-[96px] rounded-xl border transition-all text-left flex flex-col justify-between cursor-pointer group shadow-sm ${
                                isActive
                                  ? "bg-gradient-violet border-transparent shadow-md glow-accent"
                                  : "bg-background/40 border-border text-muted-foreground hover:bg-secondary/60"
                              }`}
                            >
                              <div className="flex items-center justify-between w-full">
                                <span className="capitalize text-xs font-bold">{styleKey.replace(/-/g, " ")}</span>
                                {isActive && <Check className="w-3.5 h-3.5" />}
                              </div>

                              {/* Styled animated preview text using the style name itself */}
                              <AnimatedWordPreview words={words} sDef={sDef} pStyle={pStyle} />
                            </button>
                          );
                        });
                      })()}
                    </div>

                    {/* Toggle show all styles */}
                    <button
                      type="button"
                      onClick={() => setShowAllStyles(!showAllStyles)}
                      className="w-full mt-2.5 text-xs font-bold text-[var(--accent-violet)] hover:underline flex items-center justify-center gap-1 py-2 cursor-pointer border border-dashed border-border/60 hover:bg-secondary/40 rounded-xl transition-all"
                    >
                      <span>{showAllStyles ? "Sembunyikan Gaya" : "Tampilkan Semua Gaya Subtitle"}</span>
                      <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-200 ${showAllStyles ? "rotate-180" : ""}`} />
                    </button>

                    {/* Warna Kustom (Collapsible) */}
                    <div className="mt-2">
                      <button
                        type="button"
                        onClick={() => setShowColorPicker(!showColorPicker)}
                        className="w-full flex items-center justify-between px-3 py-2 rounded-xl bg-secondary/60 hover:bg-secondary border border-border/60 text-xs font-bold text-foreground transition-all cursor-pointer"
                      >
                        <span>Warna Kustom</span>
                        <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-200 ${showColorPicker ? "rotate-180" : ""}`} />
                      </button>
                      {showColorPicker && (
                        <div className="mt-2 space-y-3 px-1">
                           {/* Warna Teks */}
                           <div className="flex items-center justify-between">
                             <span className="text-xs text-muted-foreground">Warna Teks</span>
                             <div className="flex items-center gap-2">
                               <span className="text-[10px] font-mono text-muted-foreground/80 w-16 text-right">
                                 {subtitleColorPrimary || "default"}
                               </span>
                               <div className="relative">
                                 <input
                                   type="color"
                                   value={subtitleColorPrimary || "#FFFFFF"}
                                   onChange={(e) => setSubtitleColorPrimary(e.target.value)}
                                   aria-label="Pilih warna teks"
                                   className="w-7 h-7 rounded-md border border-border cursor-pointer bg-transparent [&::-webkit-color-swatch-wrapper]:p-0.5 [&::-webkit-color-swatch]:rounded-sm"
                                 />
                                 {subtitleColorPrimary && (
                                   <button
                                     type="button"
                                     onClick={() => setSubtitleColorPrimary("")}
                                     className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full bg-secondary hover:bg-destructive/20 text-muted-foreground hover:text-destructive text-[8px] flex items-center justify-center transition-colors cursor-pointer border border-border"
                                     title="Hapus warna kustom"
                                     aria-label="Hapus warna teks kustom"
                                   >
                                     ✕
                                   </button>
                                 )}
                               </div>
                             </div>
                           </div>
                           {/* Warna Highlight */}
                           <div className="flex items-center justify-between">
                             <span className="text-xs text-muted-foreground">Warna Highlight</span>
                             <div className="flex items-center gap-2">
                               <span className="text-[10px] font-mono text-muted-foreground/80 w-16 text-right">
                                 {subtitleColorHighlight || "default"}
                               </span>
                               <div className="relative">
                                 <input
                                   type="color"
                                   value={subtitleColorHighlight || "#FFFF00"}
                                   onChange={(e) => setSubtitleColorHighlight(e.target.value)}
                                   aria-label="Pilih warna highlight"
                                   className="w-7 h-7 rounded-md border border-border cursor-pointer bg-transparent [&::-webkit-color-swatch-wrapper]:p-0.5 [&::-webkit-color-swatch]:rounded-sm"
                                 />
                                 {subtitleColorHighlight && (
                                   <button
                                     type="button"
                                     onClick={() => setSubtitleColorHighlight("")}
                                     className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full bg-secondary hover:bg-destructive/20 text-muted-foreground hover:text-destructive text-[8px] flex items-center justify-center transition-colors cursor-pointer border border-border"
                                     title="Hapus warna kustom"
                                     aria-label="Hapus warna highlight kustom"
                                   >
                                     ✕
                                   </button>
                                 )}
                               </div>
                             </div>
                           </div>
                           {/* Reset button */}
                           {(subtitleColorPrimary || subtitleColorHighlight) && (
                             <button
                               type="button"
                               onClick={() => { setSubtitleColorPrimary(""); setSubtitleColorHighlight(""); }}
                               className="w-full text-[10px] font-bold text-muted-foreground hover:text-destructive py-1 transition-colors cursor-pointer"
                             >
                               Reset Warna
                             </button>
                           )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Right Side: Live Preview & Comparison */}
                <div className="lg:col-span-6 flex flex-col items-center justify-start space-y-5 py-4 min-h-[420px]">
                  <div className="text-center w-full">
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground block mb-1">
                      Preview & Perbandingan Template
                    </span>
                    <span className="text-[10px] text-muted-foreground block">
                      Perbandingan sebelum (horizontal) dan sesudah (vertikal)
                    </span>
                  </div>

                  {template === "podcast" || template === "gaming" ? (
                    <div className="w-full max-w-[340px] flex flex-col items-center space-y-5 p-5 rounded-3xl bg-secondary/10 dark:bg-zinc-900/10 border border-border/50 shadow-sm animate-in fade-in duration-300">
                      {/* Top: Original Video Card (16:9) */}
                      <div className="w-full flex flex-col space-y-2">
                        <div className="flex items-center justify-between px-1">
                          <span className="text-[10px] font-bold text-muted-foreground/80 uppercase tracking-wider">Video Asli (16:9)</span>
                          <span className="text-[9px] px-2 py-0.5 rounded-full bg-secondary/60 text-muted-foreground font-semibold">Sumber</span>
                        </div>
                        <div className="relative aspect-video w-full rounded-2xl overflow-hidden bg-black border border-border/80 shadow-md">
                          {/* Transparent overlay shield */}
                          <div className="absolute inset-0 bg-transparent z-10 cursor-default" onContextMenu={(e) => e.preventDefault()} />
                          <video
                            ref={videoRefSource}
                            src={(template === "podcast" ? podcastHorizSrc : gamingHorizSrc) || undefined}
                            autoPlay
                            loop
                            muted
                            playsInline
                            controlsList="nodownload nofullscreen noremoteplayback"
                            disablePictureInPicture
                            onContextMenu={(e) => e.preventDefault()}
                            className="w-full h-full object-cover relative z-0"
                          />
                        </div>
                      </div>

                      {/* Middle: Theme-colored Flow Arrow */}
                      <div className="flex flex-col items-center justify-center text-[var(--accent-violet)] py-1">
                        <span className="text-[8px] font-extrabold uppercase tracking-widest text-[var(--accent-violet)] opacity-70 mb-0.5">
                          {template === "podcast" ? "Auto Reframing" : "Gaming Split-Screen"}
                        </span>
                        <svg className="w-4 h-4 animate-bounce" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                        </svg>
                      </div>

                      {/* Bottom: Vertical Phone Mockup (9:16) */}
                      <div className="w-full flex flex-col space-y-2 items-center">
                        <div className="flex items-center justify-between w-full max-w-[210px] px-1">
                          <span className="text-[10px] font-bold text-[var(--accent-violet)] uppercase tracking-wider">Hasil (9:16)</span>
                          <span className="text-[9px] px-2 py-0.5 rounded-full bg-[var(--accent-violet)]/10 text-[var(--accent-violet)] font-bold">Shorts</span>
                        </div>
                        <div className="relative">
                          {/* Glow */}
                          <div className="absolute inset-0 rounded-[2.2rem] bg-[var(--accent-violet)] opacity-10 blur-2xl scale-110 pointer-events-none" />

                          <div className="relative w-[210px] aspect-[9/16] rounded-[2.2rem] overflow-hidden bg-black border-[4px] border-zinc-800 dark:border-zinc-700/80 shadow-2xl flex flex-col">
                            {/* Notch */}
                            <div className="absolute top-2 left-1/2 -translate-x-1/2 w-16 h-4 rounded-full bg-black z-20 flex items-center justify-center">
                              <div className="w-1.5 h-1.5 rounded-full bg-zinc-700" />
                            </div>

                            {/* Transparent overlay shield */}
                            <div className="absolute inset-0 bg-transparent z-10 cursor-default" onContextMenu={(e) => e.preventDefault()} />

                            <video
                              ref={videoRefResult}
                              src={(template === "podcast" ? podcastShortSrc : gamingShortSrc) || undefined}
                              autoPlay
                              loop
                              muted
                              playsInline
                              controlsList="nodownload nofullscreen noremoteplayback"
                              disablePictureInPicture
                              onContextMenu={(e) => e.preventDefault()}
                              className="absolute inset-0 w-full h-full object-cover z-0"
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : null}
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
                      <div className="w-9 h-9 rounded-xl bg-gradient-violet/15 flex items-center justify-center flex-shrink-0 group-hover:bg-gradient-violet text-[var(--accent-violet)] transition-all">
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

      {/* Example Video Modal Overlay removed since preview is integrated to the side */}
    </div>
  );
}
