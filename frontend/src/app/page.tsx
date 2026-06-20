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
import { createTask, deleteTask } from "@/lib/api";

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
  
  // Advanced Options state
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [numClips, setNumClips] = useState("5");
  const [aspectRatio, setAspectRatio] = useState("9:16");
  const [language, setLanguage] = useState("auto");
  const [subtitleStyle, setSubtitleStyle] = useState("viral-bold");

  // Recent tasks state
  const [recentTasks, setRecentTasks] = useState<RecentTask[]>([]);

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

  return (
    <main className="min-h-screen bg-gradient-to-b from-stone-50 via-white to-stone-100/50 dark:from-stone-950 dark:via-stone-900 dark:to-stone-950 text-foreground transition-colors duration-300">
      {/* Top Navbar */}
      <header className="border-b border-stone-200/50 dark:border-stone-855 sticky top-0 bg-white/80 dark:bg-stone-900/80 backdrop-blur-md z-10 transition-colors">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-stone-900 dark:bg-stone-100 flex items-center justify-center">
              <Sparkles className="w-4.5 h-4.5 text-white dark:text-stone-900 animate-pulse" />
            </div>
            <span className="font-extrabold text-lg tracking-tight font-syne text-stone-900 dark:text-white">
              Clip AI
            </span>
          </div>
          <ThemeToggle />
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-12 sm:py-16">
        {/* Header Section */}
        <div className="text-center mb-12 animate-in fade-in slide-in-from-bottom-4 duration-700">
          <div className="inline-flex items-center gap-2 mb-4 px-3 py-1 rounded-full bg-stone-100 dark:bg-stone-800 text-xs font-medium text-stone-600 dark:text-stone-300 border border-stone-200/50 dark:border-stone-700/50 shadow-sm transition-all duration-300 hover:scale-105">
            <Sparkles className="w-3.5 h-3.5 text-amber-500 animate-pulse" />
            <span>AI Viral Short Video Clipper</span>
          </div>
          <h1 className="text-4xl sm:text-6xl font-extrabold text-stone-900 dark:text-white mb-4 tracking-tight leading-none">
            Tempel Link YouTube.
            <br />
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-amber-500 via-rose-500 to-violet-600 dark:from-amber-400 dark:via-rose-400 dark:to-violet-500">
              Hasilkan Video Viral 9:16.
            </span>
          </h1>
          <p className="text-stone-500 dark:text-stone-400 max-w-xl mx-auto text-base sm:text-lg font-light leading-relaxed">
            AI kami akan mengunduh, mentranskripsi, mendeteksi momen paling seru, dan memotong video secara vertikal menggunakan pelacakan wajah cerdas.
          </p>
        </div>

        {/* Input Form & Config Box */}
        <div className="bg-white dark:bg-stone-900/60 backdrop-blur-xl border border-stone-200/80 dark:border-stone-800/80 rounded-2xl p-6 sm:p-8 shadow-xl dark:shadow-stone-950/20 mb-12 animate-in fade-in slide-in-from-bottom-6 duration-700 delay-100">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="relative group">
              <Youtube className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-stone-400 dark:text-stone-500 group-focus-within:text-red-500 transition-colors" />
              <Input
                type="url"
                placeholder="https://www.youtube.com/watch?v=..."
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                className="h-14 pl-12 pr-4 text-base rounded-xl border-stone-200 dark:border-stone-800 bg-stone-50/50 dark:bg-stone-950/30 focus:border-stone-400 dark:focus:border-stone-700 focus:bg-white dark:focus:bg-stone-950 transition-all shadow-inner focus:ring-1 focus:ring-stone-400/20"
                autoFocus
              />
            </div>

            {/* Collapsible Advanced Options */}
            <div className="border-t border-stone-100 dark:border-stone-850 pt-4">
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="flex items-center gap-2 text-sm text-stone-500 dark:text-stone-400 hover:text-stone-800 dark:hover:text-stone-250 transition-colors font-medium"
              >
                <Settings2 className={`w-4 h-4 transition-transform duration-300 ${showAdvanced ? 'rotate-90 text-amber-500' : ''}`} />
                <span>Pengaturan Lanjutan</span>
              </button>

              {showAdvanced && (
                <div className="space-y-4 mt-4 p-4 rounded-xl bg-stone-50 dark:bg-stone-950/50 border border-stone-100 dark:border-stone-850 animate-in fade-in slide-in-from-top-2 duration-300">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
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
                        <SelectTrigger id="aspect-ratio" className="bg-white dark:bg-stone-900 border-stone-200 dark:border-stone-850">
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
                  </div>

                  {/* Subtitle Style Preview Cards */}
                  <div className="space-y-2 pt-2 border-t border-stone-100 dark:border-stone-800">
                    <Label className="text-xs text-stone-500 dark:text-stone-400">Gaya Subtitle</Label>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                      {[
                        {
                          key: "viral-bold",
                          label: "Viral Bold",
                          bg: "from-rose-600/90 to-rose-800/90",
                          textClass: "font-black text-white text-[11px] uppercase tracking-wider",
                          shadow: "drop-shadow-[0_1px_3px_rgba(0,0,0,0.9)]",
                          words: [
                            { t: "THIS", s: false },
                            { t: "IS", s: false },
                            { t: "VIRAL", s: true },
                          ],
                          highlightColor: "text-yellow-300",
                        },
                        {
                          key: "word-pop",
                          label: "Word Pop",
                          bg: "from-amber-700/90 to-orange-900/90",
                          textClass: "font-black text-white text-[13px] uppercase",
                          shadow: "drop-shadow-[0_2px_4px_rgba(0,0,0,0.8)]",
                          words: [
                            { t: "BOOM", s: true },
                          ],
                          highlightColor: "text-white",
                          singleWord: true,
                        },
                        {
                          key: "clean-minimal",
                          label: "Clean Minimal",
                          bg: "from-stone-800/80 to-stone-950/80",
                          textClass: "font-normal text-white/80 text-[10px] lowercase",
                          shadow: "",
                          words: [
                            { t: "clean", s: false },
                            { t: "simple", s: false },
                            { t: "text", s: false },
                          ],
                          highlightColor: "text-white/40",
                        },
                        {
                          key: "highlight-box",
                          label: "Highlight Box",
                          bg: "from-slate-700/90 to-slate-900/90",
                          textClass: "font-black text-white text-[10px] px-1.5 py-0.5",
                          shadow: "",
                          boxStyle: true,
                          words: [
                            { t: "BOX", s: true },
                            { t: "it", s: false },
                          ],
                          highlightColor: "text-white",
                        },
                        {
                          key: "neon-gradient",
                          label: "Neon Gradient",
                          bg: "from-blue-950/90 to-purple-950/90",
                          textClass: "font-black text-[11px] uppercase tracking-wider",
                          shadow: "drop-shadow-[0_0_8px_rgba(255,240,0,0.7)]",
                          words: [
                            { t: "NEON", s: true },
                            { t: "GLOW", s: true },
                          ],
                          highlightColor: "text-yellow-200",
                        },
                        {
                          key: "minimalist",
                          label: "Minimalist",
                          bg: "from-stone-600/70 to-stone-800/70",
                          textClass: "font-normal text-white/70 text-[10px]",
                          shadow: "",
                          words: [
                            { t: "subtle", s: false },
                            { t: "fade", s: false },
                          ],
                          highlightColor: "text-white/30",
                        },
                        {
                          key: "neon-glow",
                          label: "Neon Glow",
                          bg: "from-violet-900/90 to-fuchsia-950/90",
                          textClass: "font-black text-[11px] tracking-wide",
                          shadow: "drop-shadow-[0_0_6px_rgba(0,255,255,0.6)]",
                          words: [
                            { t: "NEON", s: true },
                            { t: "glow", s: false },
                            { t: "fx", s: false },
                          ],
                          highlightColor: "text-cyan-300",
                        },
                        {
                          key: "classic-popup",
                          label: "Classic Pop-up",
                          bg: "from-slate-600/90 to-slate-800/90",
                          textClass: "font-bold text-white text-[11px]",
                          shadow: "drop-shadow-[0_1px_2px_rgba(0,0,0,0.7)]",
                          words: [
                            { t: "pop", s: true },
                            { t: "up", s: false },
                            { t: "style", s: false },
                          ],
                          highlightColor: "text-yellow-300",
                        },
                      ].map((style) => (
                        <button
                          key={style.key}
                          type="button"
                          onClick={() => setSubtitleStyle(style.key)}
                          className={`relative group rounded-xl overflow-hidden border-2 transition-all duration-200 cursor-pointer ${
                            subtitleStyle === style.key
                              ? "border-amber-500 ring-2 ring-amber-500/30 scale-[1.02]"
                              : "border-stone-200 dark:border-stone-700 hover:border-stone-400 dark:hover:border-stone-500"
                          }`}
                        >
                          {/* Preview mockup */}
                          <div className={`aspect-[9/14] bg-gradient-to-b ${style.bg} flex flex-col justify-between p-2`}>
                            {/* Top: fake video content */}
                            <div className="flex-1 flex items-center justify-center opacity-30">
                              <svg className="w-6 h-6 text-white/40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <polygon points="5,3 19,12 5,21" />
                              </svg>
                            </div>
                            {/* Bottom: subtitle preview */}
                            <div className={`text-center leading-tight ${style.shadow}`}>
                              {style.boxStyle ? (
                                /* highlight-box: green border simulating box */
                                <span className={style.textClass} style={{ boxShadow: "inset 0 0 0 3px #76E600", backgroundColor: "rgba(118,230,0,0.15)" }}>
                                  {style.words.map((w, i) => (
                                    <span key={i} className={w.s ? style.highlightColor : "text-stone-300"}>
                                      {w.t}{i < style.words.length - 1 ? " " : ""}
                                    </span>
                                  ))}
                                </span>
                              ) : style.singleWord ? (
                                /* word-pop: single centered word */
                                <span className={`${style.textClass} ${style.highlightColor}`}>
                                  {style.words[0].t}
                                </span>
                              ) : (
                                <span className={style.textClass}>
                                  {style.words.map((w, i) => (
                                    <span key={i} className={w.s ? style.highlightColor : ""}>
                                      {w.t}{i < style.words.length - 1 ? " " : ""}
                                    </span>
                                  ))}
                                </span>
                              )}
                            </div>
                          </div>
                          {/* Label */}
                          <div className={`px-2 py-1.5 text-[10px] font-semibold text-center transition-colors ${
                            subtitleStyle === style.key
                              ? "bg-amber-50 dark:bg-amber-950/50 text-amber-700 dark:text-amber-300"
                              : "bg-white dark:bg-stone-900 text-stone-600 dark:text-stone-400"
                          }`}>
                            {style.label}
                          </div>
                          {/* Checkmark */}
                          {subtitleStyle === style.key && (
                            <div className="absolute top-1.5 right-1.5 w-5 h-5 rounded-full bg-amber-500 flex items-center justify-center shadow-md">
                              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                              </svg>
                            </div>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>

            <Button
              type="submit"
              size="lg"
              className="w-full h-12 text-base rounded-xl font-medium bg-stone-900 hover:bg-stone-800 dark:bg-stone-100 dark:hover:bg-stone-200 dark:text-stone-900 text-white transition-all shadow-md active:scale-[0.99] disabled:opacity-50"
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
            <div className="flex items-center gap-2 text-stone-700 dark:text-stone-300 font-semibold border-b border-stone-200/50 dark:border-stone-800 pb-2">
              <History className="w-4 h-4 text-stone-400" />
              <h2>Riwayat Pembuatan Klip Anda</h2>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {recentTasks.map((t) => (
                <div
                  key={t.id}
                  onClick={() => router.push(`/tasks/${t.id}`)}
                  className="flex items-center justify-between p-4 rounded-xl border border-stone-205 dark:border-stone-800/80 bg-white/50 dark:bg-stone-900/30 hover:bg-white dark:hover:bg-stone-900 hover:shadow-md cursor-pointer transition-all group duration-300"
                >
                  <div className="flex items-center gap-3 overflow-hidden">
                    <div className="w-10 h-10 rounded-lg bg-red-50 dark:bg-red-950/20 flex items-center justify-center border border-red-100 dark:border-red-900/30 flex-shrink-0 group-hover:scale-105 transition-transform">
                      <Video className="w-5 h-5 text-red-500 dark:text-red-400" />
                    </div>
                    <div className="overflow-hidden">
                      <p className="text-sm font-medium text-stone-850 dark:text-stone-200 truncate pr-2">
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
                    className="text-stone-400 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/20 w-8 h-8 rounded-lg"
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

