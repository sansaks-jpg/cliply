"use client";

import React, { useState, useEffect, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Image from "next/image";
import {
  Youtube,
  Loader2,
  ArrowRight,
  ArrowLeft,
  Sliders,
  Sparkles,
  Film,
  Check,
  ChevronDown,
  Layers,
  Settings
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ThemeToggle } from "@/components/theme-toggle";
import { API_URL, createTask, waitForBackend, type BackendStatus } from "@/lib/api";
import Link from "next/link";

const YOUTUBE_RE =
  /^(https?:\/\/)?(www\.)?(youtube\.com\/(watch\?v=|shorts\/|embed\/|live\/)|youtu\.be\/).+/i;

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
    <div className="w-full py-1.5 px-2 rounded-lg bg-black/95 flex items-center justify-center min-h-[32px] border border-zinc-800/80 shadow-inner overflow-hidden select-none mt-1">
      <div className="flex flex-wrap justify-center gap-1">
        {words.map((w, i) => {
          const isActiveWord = i === (wordProgressIndex % totalW);
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
          } else {
            color = isPastWord ? pStyle.highlightColor : pStyle.primaryColor;
            opacity = isPastWord ? 1 : 0.55;
          }

          return (
            <span
              key={i}
              className="transition-all duration-200 inline-block font-black preview-word text-[10px]"
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

function CustomizeWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const url = searchParams.get("url") || "";

  // Check URL validity
  useEffect(() => {
    if (!url || !YOUTUBE_RE.test(url)) {
      toast.error("Tautan YouTube tidak valid atau kosong!");
      router.push("/");
    }
  }, [url, router]);

  // localStorage helpers
  const _lsGet = (key: string, fallback: string) => {
    if (typeof window === "undefined") return fallback;
    return localStorage.getItem(`cliply_${key}`) || fallback;
  };
  const _lsSet = (key: string, value: string) => {
    if (typeof window !== "undefined") localStorage.setItem(`cliply_${key}`, value);
  };

  const [targetClips, setTargetClips] = useState(() => _lsGet("targetClips", "auto"));
  const [splitParts, setSplitParts] = useState(() => _lsGet("splitParts", "5"));
  const [subtitleStyle, setSubtitleStyle] = useState(() => _lsGet("subtitleStyle", "viral-bold"));
  const [faceDetector, setFaceDetector] = useState(() => {
    const val = _lsGet("faceDetector", "yolov8-face");
    return (val === "yolov8-face" || val === "yunet") ? val : "yolov8-face";
  });
  const [subtitleColorPrimary, setSubtitleColorPrimary] = useState(() => _lsGet("subtitleColorPrimary", ""));
  const [subtitleColorHighlight, setSubtitleColorHighlight] = useState(() => _lsGet("subtitleColorHighlight", ""));
  const [showColorPicker, setShowColorPicker] = useState(false);
  const [encoder] = useState(() => _lsGet("encoder", "auto"));
  const [template, setTemplate] = useState(() => _lsGet("template", "podcast"));
  const [aspectRatio, setAspectRatio] = useState(() => _lsGet("aspectRatio", "4:3"));
  const [sensitivity] = useState(50);
  
  const [videoPreview, setVideoPreview] = useState<{title: string; author: string; thumbnail: string} | null>(null);
  const [previewLoading, setPreviewLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const [backendStatus, setBackendStatus] = useState<BackendStatus>("checking");

  // Tab management for Left Panel (layout / subtitle / advanced)
  const [activeTab, setActiveTab] = useState<"layout" | "subtitle" | "advanced" >("layout");

  const handleTabClick = (tab: "layout" | "subtitle" | "advanced") => {
    if (template === "split" && tab !== "layout") {
      toast.info(`Kamu memilih template Split Video (No-AI). Fitur ${tab === "subtitle" ? "Subtitle & Gaya" : "Setelan Lanjutan"} dinonaktifkan.`);
      return;
    }
    setActiveTab(tab);
  };

  // Auto fallback active tab if split is selected
  useEffect(() => {
    if (template === "split" && activeTab !== "layout") {
      setActiveTab("layout");
    }
  }, [template, activeTab]);

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

  // Convert horizontal and vertical preview videos to Blob URLs
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

    fetch("/examples/gaming_horizontal.mp4?v=1", { cache: "reload" })
      .then((res) => {
        if (!res.ok && res.status !== 304) throw new Error(`HTTP ${res.status}`);
        if (res.status === 304 || !res.body) return null;
        return res.blob();
      })
      .then((blob) => {
        if (blob) {
          gHorizUrl = URL.createObjectURL(blob);
          setGamingHorizSrc(gHorizUrl);
        }
      })
      .catch((err) => console.warn("Gaming horizontal video unavailable:", err.message));

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

  // Fetch video info from backend on load
  useEffect(() => {
    if (!url) return;
    setPreviewLoading(true);
    fetch(API_URL + '/video-info?url=' + encodeURIComponent(url.trim()))
      .then((res) => {
        if (!res.ok) throw new Error("Gagal mengambil info video");
        return res.json();
      })
      .then((data) => {
        if (!data.title) throw new Error("Video tidak ditemukan atau tidak valid");
        setVideoPreview({ title: data.title, author: data.author || "", thumbnail: data.thumbnail || "" });
      })
      .catch((err) => {
        toast.error(err instanceof Error ? err.message : "Gagal memuat info video.");
        router.push("/");
      })
      .finally(() => {
        setPreviewLoading(false);
      });
  }, [url, router]);

  // Persist settings to localStorage on change
  useEffect(() => { _lsSet("targetClips", targetClips); }, [targetClips]);
  useEffect(() => { _lsSet("splitParts", splitParts); }, [splitParts]);
  useEffect(() => { _lsSet("subtitleStyle", subtitleStyle); }, [subtitleStyle]);
  useEffect(() => { _lsSet("faceDetector", faceDetector); }, [faceDetector]);
  useEffect(() => { _lsSet("encoder", encoder); }, [encoder]);
  useEffect(() => { _lsSet("template", template); }, [template]);
  useEffect(() => { _lsSet("aspectRatio", aspectRatio); }, [aspectRatio]);
  useEffect(() => { _lsSet("subtitleColorPrimary", subtitleColorPrimary); }, [subtitleColorPrimary]);
  useEffect(() => { _lsSet("subtitleColorHighlight", subtitleColorHighlight); }, [subtitleColorHighlight]);

  // Wait for backend to be ready
  useEffect(() => {
    waitForBackend(15_000, 1_000).then((status) => {
      setBackendStatus(status);
    });
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!videoPreview || submitting || previewLoading) return;

    setSubmitting(true);
    try {
      const opts = {
        num_clips: (template === "split" ? splitParts : targetClips) === "auto" 
          ? 0 
          : parseInt(template === "split" ? splitParts : targetClips, 10),
        aspect_ratio: template === "split" ? aspectRatio : "9:16",
        language: undefined,
        subtitle_style: subtitleStyle,
        face_detector: faceDetector,
        template,
        encoder,
        sensitivity,
        subtitle_color_primary: subtitleColorPrimary || undefined,
        subtitle_color_highlight: subtitleColorHighlight || undefined,
      };

      const { task_id } = await createTask(url.trim(), opts);

      // Save into recent tasks
      const legacy = localStorage.getItem("cliply_recent_tasks");
      let currentList: Array<{ id: string; url: string; timestamp: number }> = [];
      if (legacy) {
        try { currentList = JSON.parse(legacy); } catch { {} }
      }
      const updated = [{ id: task_id, url: url.trim(), timestamp: Date.now() }, ...currentList.filter((t: { id: string }) => t.id !== task_id)].slice(0, 20);
      localStorage.setItem("cliply_recent_tasks", JSON.stringify(updated));

      toast.success("Tugas klip berhasil dimulai!");
      router.push(`/tasks?id=${task_id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Gagal memulai tugas.");
    } finally {
      setSubmitting(false);
    }
  };

  if (previewLoading) {
    return (
      <div className="h-screen bg-background text-foreground flex flex-col items-center justify-center gap-6 font-sans antialiased">
        <div className="fixed inset-0 pointer-events-none -z-10 overflow-hidden">
          <div className="absolute top-[-12%] left-[-8%] w-[44rem] h-[44rem] rounded-full blur-[120px] opacity-25 dark:opacity-40 bg-[radial-gradient(circle_at_center,var(--accent-violet),transparent_70%)] animate-blob" />
        </div>
        <Loader2 className="w-10 h-10 text-[var(--accent-violet)] animate-spin" />
        <div className="text-center space-y-2">
          <p className="text-lg font-semibold">Mengambil informasi video YouTube...</p>
          <p className="text-sm text-muted-foreground">Ini membutuhkan waktu beberapa detik.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen overflow-hidden bg-transparent text-foreground transition-colors duration-300 flex flex-col font-sans antialiased relative">
      {/* Ambient violet glow blobs */}
      <div className="fixed inset-0 pointer-events-none -z-10 overflow-hidden">
        <div className="absolute top-[-12%] left-[-8%] w-[44rem] h-[44rem] rounded-full blur-[120px] opacity-25 dark:opacity-40 bg-[radial-gradient(circle_at_center,var(--accent-violet),transparent_70%)] animate-blob" />
        <div className="absolute bottom-[-18%] right-[-10%] w-[40rem] h-[40rem] rounded-full blur-[120px] opacity-20 dark:opacity-35 bg-[radial-gradient(circle_at_center,var(--accent-indigo),transparent_70%)] animate-blob-2" />
      </div>

      {/* Top Header */}
      <header className="border-b border-border/60 z-30 glass shrink-0">
        <div className="max-w-[1450px] mx-auto px-6 py-3 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-3">
            <Image src="/logo-rectangle.png" alt="cliply" width={110} height={30} priority className="h-9 w-auto" />
          </Link>
          <div className="flex items-center gap-3">
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* Main Workspace Container (Viewport-Fit: No global scroll) */}
      <main className="max-w-[1450px] w-full mx-auto px-4 sm:px-6 py-3 flex-grow flex flex-col min-h-0 overflow-hidden">
        
        {/* URL / Back Header */}
        <div className="flex items-center justify-between pb-2 border-b border-border/40 shrink-0">
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => router.push("/")}
              className="p-2 h-8 w-8 hover:bg-secondary rounded-lg border border-border/40 cursor-pointer"
              title="Kembali ke Beranda"
            >
              <ArrowLeft className="w-4 h-4 text-muted-foreground" />
            </Button>
            <div>
              <h2 className="text-sm font-extrabold tracking-tight">Studio Editor & Parameter</h2>
            </div>
          </div>
        </div>

        {backendStatus === "unavailable" && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-2.5 flex items-start gap-2 shrink-0 mt-2">
            <div className="w-5 h-5 rounded-lg bg-red-500/20 flex items-center justify-center flex-shrink-0 font-bold text-red-400 text-[10px]">!</div>
            <div className="space-y-0.5">
              <p className="text-[11px] font-semibold text-red-400">Backend tidak dapat dihubungi</p>
              <p className="text-[9px] text-muted-foreground">Server lokal di localhost:8003 tidak merespons. Pastikan backend Python sudah berjalan.</p>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="w-full flex-grow flex flex-col min-h-0 mt-3">
          {/* Layout 2-Panel Universal (Kiri: Setelan Studio, Kanan: Preview & Render) */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 flex-grow min-h-0 items-stretch overflow-hidden">
            
            {/* Panel Kiri: Pengaturan Studio (lg:col-span-5) - No scrollbar needed thanks to Tabs */}
            <div className="lg:col-span-5 rounded-2xl glass-panel p-5 border border-border/40 flex flex-col min-h-0 max-h-full">
              
              {/* Header Panel Kiri */}
              <div className="flex items-center justify-between pb-3 border-b border-border/40 shrink-0">
                <div className="flex items-center gap-2">
        <div className="w-5 h-5 rounded-lg bg-[var(--accent-violet)]/10 text-[var(--accent-violet)] flex items-center justify-center font-bold text-[10px]">1</div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Pengaturan Studio</span>
                </div>
              </div>

              {/* Tab Switcher (Layout & Klip / Subtitle / Advanced) */}
              <div className="grid grid-cols-3 gap-1.5 p-1 bg-secondary/35 rounded-xl border border-border/40 mt-3 shrink-0 relative overflow-hidden">
                <div 
                  className="absolute top-1 bottom-1 w-[calc(33.333%-6px)] bg-background shadow-sm rounded-lg transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]"
                  style={{
                    left: "4px",
                    transform: `translateX(${
                      activeTab === "layout" 
                        ? "0" 
                        : activeTab === "subtitle" 
                          ? "calc(100% + 6px)" 
                          : "calc(200% + 12px)"
                    })`
                  }}
                />
                <button
                  type="button"
                  onClick={() => handleTabClick("layout")}
                  className={`relative z-10 py-1.5 px-2 rounded-lg text-[10px] font-bold transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
                    activeTab === "layout"
                      ? "text-[var(--accent-violet)]"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <Layers className="w-3 h-3" />
                  <span>Template & Klip</span>
                </button>

                {template === "split" ? (
                  <div
                    onClick={() => handleTabClick("subtitle")}
                    className="relative z-10 cursor-not-allowed flex items-center justify-center py-1.5 px-2 opacity-30 select-none w-full"
                    title="Kamu memilih template Split Video (No-AI). Fitur subtitle dinonaktifkan."
                  >
                    <button
                      type="button"
                      className="pointer-events-none flex items-center justify-center gap-1.5 text-[10px] font-bold text-muted-foreground w-full h-full"
                    >
                      <Sparkles className="w-3 h-3" />
                      <span>Subtitle & Gaya</span>
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => handleTabClick("subtitle")}
                    className={`relative z-10 py-1.5 px-2 rounded-lg text-[10px] font-bold transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
                      activeTab === "subtitle"
                        ? "text-[var(--accent-violet)]"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <Sparkles className="w-3 h-3" />
                    <span>Subtitle & Gaya</span>
                  </button>
                )}

                {template === "split" ? (
                  <div
                    onClick={() => handleTabClick("advanced")}
                    className="relative z-10 cursor-not-allowed flex items-center justify-center py-1.5 px-2 opacity-30 select-none w-full"
                    title="Kamu memilih template Split Video (No-AI). Fitur lanjutan dinonaktifkan."
                  >
                    <button
                      type="button"
                      className="pointer-events-none flex items-center justify-center gap-1.5 text-[10px] font-bold text-muted-foreground w-full h-full"
                    >
                      <Settings className="w-3 h-3" />
                      <span>Setelan Lanjutan</span>
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => handleTabClick("advanced")}
                    className={`relative z-10 py-1.5 px-2 rounded-lg text-[10px] font-bold transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
                      activeTab === "advanced"
                        ? "text-[var(--accent-violet)]"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <Settings className="w-3 h-3" />
                    <span>Setelan Lanjutan</span>
                  </button>
                )}
              </div>

              {/* Tab Contents Area (flex-grow) */}
              <div className="flex-grow py-4 min-h-0 overflow-y-auto">
                
                {/* TAB 1: TEMPLATE & KLIP - Selalu tampil untuk template split */}
                {(template === "split" || activeTab === "layout") && (
                  <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300 ease-out">
                    
                    {/* Template Selection */}
                    <div className="space-y-1.5">
                      <Label className="text-xs font-bold text-muted-foreground">Pilih Template Video</Label>
                      <div className="flex flex-col gap-2.5">
                        {/* Podcast Card */}
                        <div
                          onClick={() => setTemplate("podcast")}
                          className={`relative rounded-xl border-2 cursor-pointer flex flex-col p-3 transition-all duration-305 ease-out overflow-hidden ${
                            template === "podcast"
                              ? "border-[var(--accent-violet)] bg-[var(--accent-violet)]/5 shadow-md scale-100 opacity-100"
                              : "border-border/60 hover:border-border hover:bg-secondary/20 opacity-60 scale-[0.98]"
                          }`}
                        >
                          <div className="flex items-center justify-between w-full">
                            <span className="font-bold text-[11px]">Podcast / Speaker Active</span>
                            <div className={`transition-all duration-300 flex items-center justify-center rounded-full p-0.5 ${template === "podcast" ? "bg-[var(--accent-violet)] text-background" : "border border-muted-foreground/30 opacity-40"}`}>
                              <Check className={`w-3 h-3 transition-all duration-300 ${template === "podcast" ? "scale-100 opacity-100" : "scale-50 opacity-0"}`} />
                            </div>
                          </div>
                          <div className={`grid transition-all duration-300 ease-in-out ${template === "podcast" ? "grid-rows-[1fr] opacity-100 mt-2" : "grid-rows-[0fr] opacity-0"}`}>
                            <div className="overflow-hidden">
                              <p className="text-[10px] text-muted-foreground leading-relaxed">
                                Mendeteksi wajah pembicara utama secara dinamis ke rasio 9:16 vertikal. Ideal untuk wawancara.
                              </p>
                            </div>
                          </div>
                        </div>

                        {/* Gaming Card */}
                        <div
                          onClick={() => setTemplate("gaming")}
                          className={`relative rounded-xl border-2 cursor-pointer flex flex-col p-3 transition-all duration-305 ease-out overflow-hidden ${
                            template === "gaming"
                              ? "border-[var(--accent-violet)] bg-[var(--accent-violet)]/5 shadow-md scale-100 opacity-100"
                              : "border-border/60 hover:border-border hover:bg-secondary/20 opacity-60 scale-[0.98]"
                          }`}
                        >
                          <div className="flex items-center justify-between w-full">
                            <span className="font-bold text-[11px]">Gaming ML</span>
                            <div className={`transition-all duration-300 flex items-center justify-center rounded-full p-0.5 ${template === "gaming" ? "bg-[var(--accent-violet)] text-background" : "border border-muted-foreground/30 opacity-40"}`}>
                              <Check className={`w-3 h-3 transition-all duration-300 ${template === "gaming" ? "scale-100 opacity-100" : "scale-50 opacity-0"}`} />
                            </div>
                          </div>
                          <div className={`grid transition-all duration-300 ease-in-out ${template === "gaming" ? "grid-rows-[1fr] opacity-100 mt-2" : "grid-rows-[0fr] opacity-0"}`}>
                            <div className="overflow-hidden">
                              <p className="text-[10px] text-muted-foreground leading-relaxed">
                                Membagi layar: crop wajah streamer di atas dan gameplay Mobile Legends di bawah.
                              </p>
                            </div>
                          </div>
                        </div>

                        {/* Split Card */}
                        <div
                          onClick={() => setTemplate("split")}
                          className={`relative rounded-xl border-2 cursor-pointer flex flex-col p-3 transition-all duration-305 ease-out overflow-hidden ${
                            template === "split"
                              ? "border-[var(--accent-violet)] bg-[var(--accent-violet)]/5 shadow-md scale-100 opacity-100"
                              : "border-border/60 hover:border-border hover:bg-secondary/20 opacity-60 scale-[0.98]"
                          }`}
                        >
                          <div className="flex items-center justify-between w-full">
                            <span className="font-bold text-[11px]">Split Video / No-AI</span>
                            <div className={`transition-all duration-300 flex items-center justify-center rounded-full p-0.5 ${template === "split" ? "bg-[var(--accent-violet)] text-background" : "border border-muted-foreground/30 opacity-40"}`}>
                              <Check className={`w-3 h-3 transition-all duration-300 ${template === "split" ? "scale-100 opacity-100" : "scale-50 opacity-0"}`} />
                            </div>
                          </div>
                          <div className={`grid transition-all duration-300 ease-in-out ${template === "split" ? "grid-rows-[1fr] opacity-100 mt-2" : "grid-rows-[0fr] opacity-0"}`}>
                            <div className="overflow-hidden">
                              <p className="text-[10px] text-muted-foreground leading-relaxed">
                                Membagi video panjang secara merata tanpa AI. Cocok untuk gameplay panjang (Minecraft).
                              </p>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Format Potong Video (Split Only) */}
                    {template === "split" && (
                      <div className="space-y-1.5 animate-in fade-in duration-200">
                        <Label htmlFor="aspect-ratio" className="text-xs font-bold text-muted-foreground flex items-center gap-1.5">
                          <Sliders className="w-3.5 h-3.5 text-[var(--accent-violet)]" />
                          Format Potong Video
                        </Label>
                        <Select value={aspectRatio} onValueChange={setAspectRatio}>
                          <SelectTrigger id="aspect-ratio" className="bg-background/40 border-border rounded-xl h-9 text-xs font-semibold shadow-none">
                            <SelectValue placeholder="Pilih Format" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="4:3">Shorts (4:3 Zoom)</SelectItem>
                            <SelectItem value="16:9">Horizontal (16:9)</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    )}

                    {/* Target Klip / Part */}
                    <div className="space-y-1.5">
                      <Label htmlFor="num-clips" className="text-xs font-bold text-muted-foreground flex items-center gap-1.5">
                        <Film className="w-3.5 h-3.5 text-[var(--accent-violet)]" />
                        {template === "split" ? "Jumlah Bagian (Part)" : "Target Klip"}
                      </Label>
                      <Select 
                        value={template === "split" ? splitParts : targetClips} 
                        onValueChange={template === "split" ? setSplitParts : setTargetClips}
                      >
                        <SelectTrigger id="num-clips" className="bg-background/40 border-border rounded-xl h-9 text-xs font-semibold shadow-none">
                          <SelectValue placeholder={template === "split" ? "Pilih Jumlah Bagian" : "Pilih Target Klip"} />
                        </SelectTrigger>
                        <SelectContent>
                          {template === "split" ? (
                            <>
                              <SelectItem value="2">2 Bagian (Part)</SelectItem>
                              <SelectItem value="3">3 Bagian (Part)</SelectItem>
                              <SelectItem value="4">4 Bagian (Part)</SelectItem>
                              <SelectItem value="5">5 Bagian (Part)</SelectItem>
                              <SelectItem value="8">8 Bagian (Part)</SelectItem>
                              <SelectItem value="10">10 Bagian (Part)</SelectItem>
                            </>
                          ) : (
                            <>
                              <SelectItem value="auto">Auto (Rekomendasi AI)</SelectItem>
                              <SelectItem value="1">1 Klip</SelectItem>
                              <SelectItem value="3">3 Klip</SelectItem>
                              <SelectItem value="5">5 Klip</SelectItem>
                              <SelectItem value="7">7 Klip</SelectItem>
                              <SelectItem value="10">10 Klip</SelectItem>
                            </>
                          )}
                        </SelectContent>
                      </Select>
                    </div>

                  </div>
                )}

                {/* TAB 2: SUBTITLE & GAYA - Hanya render jika BUKAN split */}
                {template !== "split" && activeTab === "subtitle" && (
                  <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300 ease-out">
                    
                    {/* Grid card pilihan gaya subtitle */}
                    {showColorPicker ? (
                      <div className="space-y-1.5 animate-in fade-in duration-200">
                        <Label className="text-xs font-bold text-muted-foreground flex items-center gap-1.5">
                          <Sparkles className="w-3.5 h-3.5 text-[var(--accent-violet)]" />
                          Gaya Subtitle Terpilih
                        </Label>
                        <div 
                          onClick={() => setShowColorPicker(false)}
                          className="cursor-pointer"
                          title="Klik untuk mengubah gaya subtitle"
                        >
                          {(() => {
                            const styleKey = subtitleStyle;
                            const sDef = STYLE_DEFINITIONS[styleKey];
                            const pStyle = getDynamicPreviewStyles(styleKey, subtitleColorPrimary || undefined, subtitleColorHighlight || undefined);
                            const textShadow = makeTextShadow(Math.min(sDef.outlineWidth, 1.5), sDef.outlineColor);

                            return (
                              <div
                                className="rounded-xl p-2.5 text-left flex flex-col justify-between relative h-20 overflow-hidden bg-secondary/85 text-foreground shadow-sm ring-1.5 ring-primary/25 scale-[1.01] hover:bg-secondary/95 transition-all"
                              >
                                <div className="flex items-center justify-between w-full">
                                  <span className="text-[9px] font-bold tracking-tight text-muted-foreground uppercase">
                                    {styleKey.replace(/-/g, " ")}
                                  </span>
                                  <span className="text-[9px] font-bold text-[var(--accent-violet)] hover:underline">
                                    Ubah Gaya
                                  </span>
                                </div>

                                <div className="w-full flex items-center justify-center bg-black/90 rounded-lg py-1 px-2 min-h-[30px] border border-zinc-800/50 shadow-inner overflow-hidden select-none mt-1">
                                  <span
                                    style={{
                                      fontFamily: pStyle.fontFamily,
                                      color: pStyle.highlightColor,
                                      textShadow: textShadow,
                                      textTransform: sDef.caseTransform,
                                      fontWeight: sDef.bold ? "900" : "400",
                                      fontSize: "10px",
                                      letterSpacing: sDef.caseTransform === "uppercase" ? "0.02em" : "normal",
                                      lineHeight: "1.1",
                                      backgroundColor: sDef.animation === "box" ? pStyle.boxBgColor : "transparent",
                                      boxShadow: sDef.animation === "box" ? `0 0 0 1px ${pStyle.boxColor}` : "none",
                                      padding: sDef.animation === "box" ? "1px 4px" : "0px",
                                      borderRadius: sDef.animation === "box" ? "2px" : "0px",
                                    }}
                                  >
                                    {styleKey === "clean-minimal" ? "gaya" : styleKey === "minimalist" ? "Simpel" : "VIRAL"}
                                  </span>
                                </div>
                              </div>
                            );
                          })()}
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-2 animate-in fade-in duration-200">
                        <Label className="text-xs font-bold text-muted-foreground flex items-center gap-1.5">
                          <Sparkles className="w-3.5 h-3.5 text-[var(--accent-violet)]" />
                          Pilih Gaya Subtitle
                        </Label>
                        <div className="grid grid-cols-2 gap-2 pr-1">
                          {(() => {
                            const allStylesKeys = ["viral-bold", "tiktok", "word-pop", "clean-minimal", "highlight-box", "neon-gradient", "minimalist", "neon-glow", "classic-popup"] as const;
                            return allStylesKeys.map((styleKey) => {
                              const isActive = subtitleStyle === styleKey;
                              const sDef = STYLE_DEFINITIONS[styleKey];
                              const pStyle = getDynamicPreviewStyles(styleKey, subtitleColorPrimary || undefined, subtitleColorHighlight || undefined);
                              const textShadow = makeTextShadow(Math.min(sDef.outlineWidth, 1.5), sDef.outlineColor);

                              return (
                                <button
                                  key={styleKey}
                                  type="button"
                                  onClick={() => {
                                    setSubtitleStyle(styleKey);
                                    setShowColorPicker(false);
                                  }}
                                  className={`rounded-xl p-2.5 text-left flex flex-col justify-between cursor-pointer w-full transition-all duration-300 ease-out relative h-20 overflow-hidden ${
                                    isActive
                                      ? "bg-secondary/85 text-foreground shadow-sm ring-1.5 ring-primary/25 scale-[1.02] z-10"
                                      : "bg-secondary/20 text-muted-foreground hover:bg-secondary/45 hover:scale-[1.01]"
                                  }`}
                                >
                                  <div className="flex items-center justify-between w-full">
                                    <span className="text-[9px] font-bold tracking-tight text-muted-foreground truncate uppercase">
                                      {styleKey.replace(/-/g, " ")}
                                    </span>
                                    <div className={`transition-all duration-200 flex items-center justify-center rounded-full p-0.5 ${isActive ? "bg-[var(--accent-violet)] text-background" : "border border-muted-foreground/30 opacity-40"}`}>
                                      <Check className={`w-2.5 h-2.5 transition-all duration-200 ${isActive ? "scale-100 opacity-100" : "scale-50 opacity-0"}`} />
                                    </div>
                                  </div>

                                  <div className="w-full flex items-center justify-center bg-black/90 rounded-lg py-1 px-2 min-h-[30px] border border-zinc-800/50 shadow-inner overflow-hidden select-none mt-1">
                                    <span
                                      style={{
                                        fontFamily: pStyle.fontFamily,
                                        color: pStyle.highlightColor,
                                        textShadow: textShadow,
                                        textTransform: sDef.caseTransform,
                                        fontWeight: sDef.bold ? "900" : "400",
                                        fontSize: "10px",
                                        letterSpacing: sDef.caseTransform === "uppercase" ? "0.02em" : "normal",
                                        lineHeight: "1.1",
                                        backgroundColor: sDef.animation === "box" ? pStyle.boxBgColor : "transparent",
                                        boxShadow: sDef.animation === "box" ? `0 0 0 1px ${pStyle.boxColor}` : "none",
                                        padding: sDef.animation === "box" ? "1px 4px" : "0px",
                                        borderRadius: sDef.animation === "box" ? "2px" : "0px",
                                      }}
                                    >
                                      {styleKey === "clean-minimal" ? "gaya" : styleKey === "minimalist" ? "Simpel" : "VIRAL"}
                                    </span>
                                  </div>
                                </button>
                              );
                            });
                          })()}
                        </div>
                      </div>
                    )}

                    {/* Kustomisasi Warna */}
                    <div className="space-y-2 pt-2 border-t border-border/20">
                      <button
                        type="button"
                        onClick={() => setShowColorPicker(!showColorPicker)}
                        className="w-full flex items-center justify-between px-3 py-2 rounded-xl bg-secondary/40 hover:bg-secondary/60 border border-border/40 text-[10px] font-bold text-foreground transition-all cursor-pointer"
                      >
                        <span>Kustomisasi Warna Subtitle</span>
                        <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-300 ${showColorPicker ? "rotate-180" : ""}`} />
                      </button>
                      
                      <div className={`grid transition-all duration-300 ease-in-out ${showColorPicker ? "grid-rows-[1fr] opacity-100 mt-1" : "grid-rows-[0fr] opacity-0"}`}>
                        <div className="overflow-hidden">
                          <div className="space-y-2 p-3 rounded-xl border border-border/45 bg-secondary/15">
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] text-muted-foreground">Warna Teks</span>
                              <div className="flex items-center gap-2">
                                <span className="text-[9px] font-mono text-muted-foreground/80">{subtitleColorPrimary || "default"}</span>
                                <input
                                  type="color"
                                  value={subtitleColorPrimary || "#FFFFFF"}
                                  onChange={(e) => setSubtitleColorPrimary(e.target.value)}
                                  className="w-5 h-5 rounded-md border border-border cursor-pointer bg-transparent"
                                />
                              </div>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] text-muted-foreground">Warna Highlight</span>
                              <div className="flex items-center gap-2">
                                <span className="text-[9px] font-mono text-muted-foreground/80">{subtitleColorHighlight || "default"}</span>
                                <input
                                  type="color"
                                  value={subtitleColorHighlight || "#FFFF00"}
                                  onChange={(e) => setSubtitleColorHighlight(e.target.value)}
                                  className="w-5 h-5 rounded-md border border-border cursor-pointer bg-transparent"
                                />
                              </div>
                            </div>
                            {(subtitleColorPrimary || subtitleColorHighlight) && (
                              <button
                                type="button"
                                onClick={() => { setSubtitleColorPrimary(""); setSubtitleColorHighlight(""); }}
                                className="w-full text-[9px] font-bold text-muted-foreground hover:text-destructive py-0.5 transition-colors cursor-pointer"
                              >
                                Reset Warna
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>

                  </div>
                )}

                {/* TAB 3: ADVANCED SETTINGS - Hanya render jika BUKAN split */}
                {template !== "split" && activeTab === "advanced" && (
                  <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300 ease-out">
                    
                    {/* Face Tracker */}
                    <div className="space-y-1.5">
                      <Label htmlFor="face-detector" className="text-xs font-bold text-muted-foreground">Face Tracker AI</Label>
                      <Select value={faceDetector} onValueChange={setFaceDetector}>
                        <SelectTrigger id="face-detector" className="bg-background/40 border-border rounded-xl h-9 text-xs font-semibold shadow-none">
                          <SelectValue placeholder="Detektor Wajah" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="yolov8-face">YOLOv8-Face (Terbaik & Sangat Akurat)</SelectItem>
                          <SelectItem value="yunet">YuNet (Aurat Cepat)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                  </div>
                )}

              </div>

              {/* Action Button (Kiri) */}
              <div className="pt-3 border-t border-border/40 shrink-0">
                <Button
                  type="submit"
                  disabled={submitting}
                  className="w-full h-11 rounded-2xl bg-gradient-violet hover:opacity-90 font-bold text-sm transition-all disabled:opacity-30 disabled:cursor-default shadow-md hover:scale-[1.005] flex items-center justify-center gap-2 cursor-pointer"
                >
                  {submitting ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Sedang Memproses...</span>
                    </>
                  ) : (
                    <>
                      <span>Mulai Proses Reframing</span>
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </Button>
              </div>

            </div>

            {/* Panel Kanan: Preview Perbandingan & Render (lg:col-span-7) */}
            <div className="lg:col-span-7 rounded-2xl glass-panel p-5 border border-border/40 flex flex-col justify-between overflow-hidden min-h-0 max-h-full">
              <div className="space-y-4 flex-grow flex flex-col min-h-0">
                
                <div className="flex items-center gap-2 pb-2 border-b border-border/40 shrink-0">
                  <div className="w-5 h-5 rounded-lg bg-[var(--accent-violet)]/10 text-[var(--accent-violet)] flex items-center justify-center font-bold text-[10px]">2</div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Perbandingan & Render</span>
                </div>

                {/* YouTube Video Info Card (Sekarang memuat Info Video dan link badge di dalamnya!) */}
                <div className="flex gap-4 items-center bg-secondary/35 p-3 rounded-xl border border-border/40 shrink-0">
                  {videoPreview && videoPreview.thumbnail && (
                    <div className="relative shrink-0 w-24 aspect-video rounded-lg overflow-hidden bg-muted border border-border/60">
                      <Image src={videoPreview.thumbnail} alt={videoPreview.title} fill className="object-cover" unoptimized />
                    </div>
                  )}
                  {videoPreview && (
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-bold leading-snug line-clamp-1">{videoPreview.title}</p>
                      <p className="text-[10px] text-muted-foreground truncate">{videoPreview.author || "YouTube Video"}</p>
                      {/* Tautan URL YouTube disatukan di sini */}
                      <div className="flex items-center gap-1.5 mt-1.5 text-[9px] font-mono text-[var(--accent-violet)] truncate bg-[var(--accent-violet)]/10 px-2 py-0.5 rounded-md w-fit max-w-full">
                        <Youtube className="w-3 h-3 text-red-500 flex-shrink-0" />
                        <span className="truncate">{url}</span>
                      </div>
                    </div>
                  )}
                </div>

                {/* Wide Video Comparison Container (flex-grow flex-shrink min-h-0) */}
                <div className="flex-grow min-h-0 flex items-center justify-center bg-secondary/10 rounded-2xl border border-border/20 p-4">
                  <div className="grid grid-cols-1 sm:grid-cols-12 gap-5 w-full items-center justify-center">
                    {/* Left: Original Video (span 6) */}
                    <div className="sm:col-span-6 space-y-1.5 text-center">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block">Video Asli (16:9)</span>
                      <div className="relative aspect-video rounded-xl overflow-hidden bg-black border border-border/60 shadow-lg">
                        <video
                          ref={videoRefSource}
                          src={(template === "podcast" || template === "split" ? podcastHorizSrc : gamingHorizSrc) || undefined}
                          autoPlay
                          loop
                          muted
                          playsInline
                          controlsList="nodownload nofullscreen noremoteplayback"
                          disablePictureInPicture
                          onContextMenu={(e) => e.preventDefault()}
                          className="w-full h-full object-cover"
                        />
                      </div>
                    </div>

                    {/* Right: Mockup HP Vertikal 9:16 (span 6, diperbesar visualnya ke w-[150px]) */}
                    <div className="sm:col-span-6 space-y-1.5 text-center flex flex-col items-center">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block">Hasil Reframing</span>
                      <div className="relative">
                        <div className="absolute inset-0 bg-[var(--accent-violet)] opacity-15 blur-2xl scale-110 pointer-events-none rounded-[1.8rem] animate-glow-pulse" />
                        
                        <div className="relative w-[150px] aspect-[9/16] rounded-[1.8rem] overflow-hidden bg-black border-[3.5px] border-zinc-800 dark:border-zinc-850/80 shadow-2xl flex flex-col ring-1 ring-zinc-700/30">
                          <div className="absolute top-1.5 left-1/2 -translate-x-1/2 w-8 h-2.5 rounded-full bg-black z-20" />
                          
                          {template === "split" ? (
                            <video
                              ref={videoRefResult}
                              src={podcastHorizSrc || undefined}
                              autoPlay
                              loop
                              muted
                              playsInline
                              className={`absolute left-0 right-0 top-1/2 -translate-y-1/2 w-full object-cover z-0 ${
                                aspectRatio === "4:3" ? "aspect-[4/3]" : "aspect-video"
                              }`}
                            />
                          ) : (
                            <video
                              ref={videoRefResult}
                              src={(template === "podcast" ? podcastShortSrc : gamingShortSrc) || undefined}
                              autoPlay
                              loop
                              muted
                              playsInline
                              className="absolute inset-0 w-full h-full object-cover z-0"
                            />
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Subtitle Preview Terpusat di Panel Kanan */}
                {template !== "split" && (
                  <div className="w-full space-y-1 bg-secondary/15 p-2 rounded-xl border border-border/40 shrink-0">
                    <span className="text-[8px] font-bold text-muted-foreground/80 uppercase tracking-wider block text-center">
                      Simulasi Teks Subtitle Karaoke
                    </span>
                    <AnimatedWordPreview
                      words={STYLE_DEFINITIONS[subtitleStyle].words}
                      sDef={STYLE_DEFINITIONS[subtitleStyle]}
                      pStyle={getDynamicPreviewStyles(subtitleStyle, subtitleColorPrimary || undefined, subtitleColorHighlight || undefined)}
                    />
                  </div>
                )}
              </div>
            </div>

          </div>
        </form>
      </main>

      <footer className="border-t border-border/60 py-3 text-center text-[10px] text-muted-foreground shrink-0 mt-auto">
        <p>© {new Date().getFullYear()} cliply</p>
      </footer>
    </div>
  );
}

export default function CustomizePage() {
  return (
    <Suspense fallback={
      <div className="h-screen bg-background text-foreground flex flex-col items-center justify-center gap-4">
        <div className="w-10 h-10 border-4 border-[var(--accent-violet)] border-t-transparent rounded-full animate-spin" />
        <p className="text-sm text-muted-foreground font-semibold">Memuat Workspace...</p>
      </div>
    }>
      <CustomizeWorkspace />
    </Suspense>
  );
}
