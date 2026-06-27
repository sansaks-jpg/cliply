"use client";

import { useCallback, useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Loader2,
  CheckCircle,
  AlertCircle,
  Zap,
  Sparkles,
  Clock,
  Terminal,
  ChevronRight,
  Smartphone,
  TrendingUp,
  DownloadCloud,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { API_URL, getTask, type Task, type TaskClip } from "@/lib/api";
import { VerticalPlayer } from "@/components/vertical-player";
import { ThemeToggle } from "@/components/theme-toggle";

const POLL_INTERVAL_MS = 5000;

function formatClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function ScoreBadge({ score }: { score: number }) {
  const tier =
    score >= 80
      ? "bg-gradient-violet text-white border-transparent shadow-md glow-accent"
      : score >= 60
        ? "bg-[var(--accent-violet)]/15 text-[var(--accent-violet)] border border-[var(--accent-violet)]/30"
        : "bg-secondary text-muted-foreground border border-border/60";
  return (
    <Badge className={`px-2 py-0.5 rounded-lg text-xs font-bold shadow-none flex items-center gap-1 ${tier}`}>
      <Zap className="w-3 h-3 fill-current" />
      <span>{score}</span>
    </Badge>
  );
}

function ProgressView({ task }: { task: Task }) {
  const pct = Math.round(task.progress);

  const stages = [
    { key: "download", label: "Download & Cache", minPct: 0, maxPct: 15 },
    { key: "transcribe", label: "Transkripsi AI", minPct: 15, maxPct: 35 },
    { key: "highlights", label: "Analisis Virabilitas", minPct: 35, maxPct: 50 },
    { key: "smart_crop", label: "Smart Face Crop", minPct: 50, maxPct: 65 },
    { key: "render", label: "Render & Subtitle", minPct: 65, maxPct: 90 },
    { key: "finalize", label: "Finalisasi", minPct: 90, maxPct: 100 }
  ];

  return (
    <div className="glass-panel rounded-2xl p-6 space-y-6 animate-in fade-in slide-in-from-bottom-3 duration-500">

      <div className="flex items-center justify-between pb-4 border-b border-border/40">
        <div className="space-y-1 text-left">
          <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
            <Sparkles className="w-3.5 h-3.5 text-[var(--accent-violet)]" />
            Status Alur Kerja
          </h3>
          <p className="text-sm text-foreground/80 font-medium">
            {task.message || "Menyiapkan antrean pemrosesan..."}
          </p>
        </div>
        <div>
          <span className="text-2xl font-black text-gradient-violet font-mono">{pct}%</span>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {stages.map((st, i) => {
          const isDone = pct > st.maxPct;
          const isActive = pct >= st.minPct && pct < st.maxPct;

          return (
            <div
              key={st.key}
              className={`p-3.5 rounded-xl border flex items-center justify-between transition-all duration-300 ${
                isActive
                  ? "glass-panel border-[var(--accent-violet)]/40 glow-accent"
                  : isDone
                    ? "bg-secondary/40 border-border/40 text-muted-foreground"
                    : "bg-transparent border-border/30 text-muted-foreground/50"
              }`}
            >
              <div className="flex items-center gap-3 overflow-hidden">
                <div className={`w-6 h-6 rounded-lg flex items-center justify-center text-xs font-bold transition-all ${
                  isActive
                    ? "bg-gradient-violet text-white"
                    : isDone
                      ? "bg-[var(--accent-violet)]/15 text-[var(--accent-violet)]"
                      : "bg-secondary text-muted-foreground/50"
                }`}>
                  {isDone ? "✓" : i + 1}
                </div>
                <span className="text-sm font-bold truncate">{st.label}</span>
              </div>
              {isActive && (
                <Loader2 className="w-4 h-4 animate-spin text-[var(--accent-violet)]" />
              )}
            </div>
          );
        })}
      </div>

      <div className="space-y-2 pt-2">
        <div className="h-2.5 bg-secondary/60 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-violet transition-all duration-500 ease-out rounded-full glow-accent"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
    </div>
  );
}

function TaskPageContent() {
  const searchParams = useSearchParams();
  const taskId = searchParams.get("id") || "";
  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const [logs, setLogs] = useState<string[]>([]);
  const [showLogs, setShowLogs] = useState(true);
  const logEndRef = useRef<HTMLDivElement | null>(null);

  // Active clip selection inside completion screen
  const [activeClipIdx, setActiveClipIdx] = useState<number>(0);

  const addLog = useCallback((stage: string, message: string) => {
    const cleanMsg = message.trim();
    if (!cleanMsg) return;
    const timestamp = new Date().toLocaleTimeString("id-ID", { hour12: false });
    const newLog = `[${timestamp}] [${stage.toUpperCase()}] ${cleanMsg}`;

    setLogs((prev) => {
      if (prev.length > 0) {
        const lastLog = prev[prev.length - 1];
        if (lastLog.includes(cleanMsg)) {
          return prev;
        }
      }
      const next = [...prev, newLog];
      if (taskId) {
        localStorage.setItem(`clip_logs_${taskId}`, JSON.stringify(next));
      }
      return next;
    });
  }, [taskId]);

  // Load saved logs
  useEffect(() => {
    if (!taskId) return;
    const saved = localStorage.getItem(`clip_logs_${taskId}`);
    if (saved) {
      try {
        setLogs(JSON.parse(saved));
      } catch {
        /* ignore */
      }
    } else {
      setLogs([]);
    }
  }, [taskId]);

  // Auto-scroll logs
  useEffect(() => {
    if (showLogs && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, showLogs]);

  const refresh = useCallback(async () => {
    try {
      const data = await getTask(taskId);
      setTask(data);
      setError(null);
      return data;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      if (msg.includes("404")) {
        setError("Tugas tidak ditemukan. Mungkin sudah dihapus.");
      } else {
        setError(msg || "Gagal memuat tugas");
      }
      return null;
    }
  }, [taskId]);

  // Initial load
  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      await refresh();
      if (active) setLoading(false);
    })();
    return () => {
      active = false;
    };
  }, [refresh]);

  // SSE for live progress
  useEffect(() => {
    if (!taskId) return;
    if (task && task.status !== "queued" && task.status !== "processing") {
      return;
    }

    const es = new EventSource(`${API_URL}/tasks/${taskId}/progress`);
    esRef.current = es;

    es.addEventListener("progress", (e) => {
      try {
        const data = JSON.parse((e as MessageEvent).data);
        setTask((prev) =>
          prev
            ? {
                ...prev,
                progress: data.pct ?? prev.progress,
                stage: data.stage ?? prev.stage,
                message: data.message ?? prev.message,
                status: "processing",
              }
            : prev,
        );
        addLog(data.stage || "progress", data.message || "");
      } catch {
        /* ignore malformed */
      }
    });

    es.addEventListener("clip_ready", (e) => {
      try {
        const clip = JSON.parse((e as MessageEvent).data) as TaskClip;
        setTask((prev) =>
          prev
            ? {
                ...prev,
                clips: (prev.clips || []).some(
                  (c) =>
                    c.start_time === clip.start_time &&
                    c.end_time === clip.end_time,
                )
                  ? prev.clips
                  : [...(prev.clips || []), clip],
              }
            : prev,
        );
        addLog("render", `Klip siap: "${clip.title || "Klip"}" (Score: ${clip.score})`);
      } catch {
        /* ignore */
      }
    });

    es.addEventListener("done", () => {
      addLog("done", "Semua proses selesai! Mengambil klip hasil...");
      void refresh();
      es.close();
    });

    es.addEventListener("error", (e) => {
      const me = e as MessageEvent;
      let errorMsg = "Terjadi kegagalan pemrosesan";
      if (typeof me.data === "string" && me.data.length > 0) {
        try {
          const data = JSON.parse(me.data);
          if (data?.error) {
            errorMsg = data.error;
            setError(data.error);
          }
        } catch {
          /* ignore */
        }
      }
      addLog("error", errorMsg);
      es.close();
    });

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [taskId, task?.status, refresh]);

  // Fallback polling
  useEffect(() => {
    if (!task || (task.status !== "queued" && task.status !== "processing")) {
      return;
    }
    const id = setInterval(() => {
      void refresh();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [task?.status, refresh]);

  // Initialize first log message
  useEffect(() => {
    if (task && logs.length === 0 && (task.status === "queued" || task.status === "processing")) {
      addLog(task.stage || "queued", task.message || "Tugas ditambahkan ke antrean...");
    }
  }, [task, logs.length, addLog]);

  if (loading) {
    return (
      <div className="h-screen bg-background p-6 flex flex-col items-center justify-center">
        <div className="max-w-md w-full space-y-6 text-center">
          <Loader2 className="w-8 h-8 animate-spin text-[var(--accent-violet)] mx-auto" />
          <p className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Memuat data workspace...</p>
        </div>
      </div>
    );
  }

  if (error && !task) {
    return (
      <div className="h-screen bg-background p-6 flex items-center justify-center">
        <div className="max-w-md w-full glass-panel p-6 rounded-2xl space-y-4">
          <div className="flex items-center gap-3 text-red-500">
            <AlertCircle className="h-5 w-5 flex-shrink-0" />
            <h3 className="font-bold text-base">Terjadi Kesalahan</h3>
          </div>
          <p className="text-sm text-muted-foreground leading-relaxed font-medium">{error}</p>
          <div className="pt-2">
            <Link href="/" className="w-full block">
              <Button className="w-full bg-gradient-violet hover:opacity-90 rounded-xl h-10 cursor-pointer font-bold shadow-none text-sm">
                <ArrowLeft className="w-4 h-4 mr-2" />
                Kembali ke Beranda
              </Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (!task) return null;

  // Active clip references
  const activeClip: TaskClip | undefined = task.clips?.[activeClipIdx];
  const activeClipHref = activeClip?.clip_url
    ? activeClip.clip_url.startsWith("http")
      ? activeClip.clip_url
      : `${API_URL}${activeClip.clip_url.startsWith("/") ? "" : "/"}${activeClip.clip_url}`
    : "";

  const isCompleted = task.status === "completed";

  return (
    <div className={`h-screen overflow-y-auto bg-background text-foreground transition-colors duration-300 relative overflow-x-hidden flex flex-col ${isCompleted ? "lg:h-screen lg:overflow-hidden" : ""}`}>

      {/* Ambient blobs */}
      <div className="fixed inset-0 pointer-events-none -z-10 overflow-hidden">
        <div className="absolute top-[-12%] left-[-8%] w-[40rem] h-[40rem] rounded-full blur-[120px] opacity-25 dark:opacity-35 bg-[radial-gradient(circle_at_center,var(--accent-violet),transparent_70%)] animate-blob" />
        <div className="absolute bottom-[-18%] right-[-10%] w-[36rem] h-[36rem] rounded-full blur-[120px] opacity-20 dark:opacity-30 bg-[radial-gradient(circle_at_center,var(--accent-indigo),transparent_70%)] animate-blob-2 animation-delay-2000" />
      </div>

      {/* Top Header */}
      <header className="border-b border-border/60 z-20 glass flex-shrink-0">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <Link href="/">
            <Button variant="ghost" size="sm" className="rounded-xl hover:bg-secondary/60 gap-2 h-8 text-sm font-bold cursor-pointer transition-colors border border-border/60">
              <ArrowLeft className="w-4 h-4" />
              <span className="hidden sm:inline">Workspace Baru</span>
            </Button>
          </Link>

          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground font-bold uppercase tracking-wider hidden sm:inline-block">
              {task.task_id.slice(0, 8)}...
            </span>
            <Badge
              variant="outline"
              className={`px-2 py-0.5 rounded-lg text-xs font-bold uppercase tracking-wider shadow-none border ${
                task.status === "completed"
                  ? "border-[var(--accent-violet)]/30 text-[var(--accent-violet)] bg-[var(--accent-violet)]/10"
                  : task.status === "error"
                    ? "border-red-500/30 text-red-500 bg-red-500/10"
                    : "border-border bg-secondary/40 text-muted-foreground"
              }`}
            >
              {task.status === "completed" ? (
                <CheckCircle className="w-3 h-3 mr-1" />
              ) : task.status === "error" ? (
                <AlertCircle className="w-3 h-3 mr-1" />
              ) : (
                <span className="relative flex h-1.5 w-1.5 mr-1.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--accent-violet)] opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-[var(--accent-violet)]"></span>
                </span>
              )}
              {task.status}
            </Badge>
            {(task.status === "queued" || task.status === "processing") && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowLogs(!showLogs)}
                className="rounded-xl text-xs gap-1.5 border-border hover:bg-secondary/60 h-8 font-bold transition-all cursor-pointer"
              >
                <Terminal className="w-3.5 h-3.5 text-[var(--accent-violet)]" />
                <span className="hidden sm:inline">{showLogs ? "Sembunyikan" : "Log"}</span>
              </Button>
            )}
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      {isCompleted ? (
        /* ── COMPLETED: Fixed Viewport Studio ── */
        <div className="flex-grow w-full flex flex-col lg:flex-row lg:overflow-hidden max-w-7xl mx-auto">

          {/* LEFT PANEL: Video besar + download + AI analysis — semua terlihat tanpa scroll */}
          <div className="w-full lg:w-[380px] xl:w-[420px] flex-shrink-0 border-b lg:border-b-0 lg:border-r border-border/40 flex flex-col overflow-hidden p-4 gap-3">

            {/* Label bar */}
            <div className="flex-shrink-0 flex items-center justify-between text-xs font-bold text-muted-foreground uppercase tracking-wider">
              <span className="flex items-center gap-1.5">
                <Smartphone className="w-3.5 h-3.5 text-[var(--accent-violet)]" />
                <span>Shorts 9:16</span>
              </span>
              <span>Klip {activeClipIdx + 1}/{task.clips?.length ?? 0}</span>
            </div>

            {/* Phone frame — flex-1 agar mengisi sisa ruang, aspect ratio dijaga via CSS */}
            <div className="flex-1 min-h-0 flex items-center justify-center relative">
              <div className="absolute inset-0 rounded-[2rem] bg-[var(--accent-violet)] opacity-15 blur-3xl scale-105 pointer-events-none" />
              {/* Wrapper: tinggi 100% container, lebar auto dengan aspect 9:16 */}
              <div
                className="relative h-full mx-auto rounded-[2rem] overflow-hidden bg-black border-[3px] border-zinc-800 dark:border-zinc-700/80 shadow-2xl"
                style={{ aspectRatio: "9/16", maxHeight: "100%" }}
              >
                {/* Notch */}
                <div className="absolute top-2.5 left-1/2 -translate-x-1/2 w-16 h-4 rounded-full bg-black/80 backdrop-blur-sm z-20 flex items-center justify-center">
                  <div className="w-1.5 h-1.5 rounded-full bg-zinc-700" />
                </div>

                {activeClipHref ? (
                  <VerticalPlayer src={activeClipHref} className="absolute inset-0 w-full h-full" />
                ) : (
                  <div className="absolute inset-0 flex items-center justify-center text-muted-foreground">
                    <Loader2 className="w-6 h-6 animate-spin" />
                  </div>
                )}
              </div>
            </div>

            {/* Download button — selalu kelihatan */}
            <div className="flex-shrink-0">
              {activeClip && (
                activeClip.error ? (
                  <Alert variant="destructive" className="py-2 px-3 rounded-xl">
                    <AlertCircle className="h-3.5 w-3.5" />
                    <AlertDescription className="text-xs font-semibold">Gagal render: {activeClip.error}</AlertDescription>
                  </Alert>
                ) : (
                  activeClipHref && (
                    <Button asChild size="sm" className="w-full h-9 rounded-xl bg-gradient-violet hover:opacity-90 text-white font-bold text-sm transition-all cursor-pointer shadow-md glow-accent flex items-center justify-center gap-2">
                      <a href={activeClipHref} download={`clip-${activeClip.title?.toLowerCase().replace(/[^a-z0-9]/g, "-") || "short"}.mp4`}>
                        <DownloadCloud className="w-4 h-4" />
                        <span>Unduh Shorts</span>
                      </a>
                    </Button>
                  )
                )
              )}
            </div>

            {/* AI Analysis — compact, selalu visible, no scroll */}
            {activeClip && (activeClip.hook_sentence || activeClip.virality_reason) && (
              <div className="flex-shrink-0 rounded-xl border border-border/50 bg-secondary/20 p-3 space-y-2">
                <div className="flex items-center gap-1.5">
                  <TrendingUp className="w-3 h-3 text-[var(--accent-violet)]" />
                  <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Analisis AI</span>
                </div>
                {activeClip.hook_sentence && (
                  <p className="text-xs text-foreground/80 italic leading-snug line-clamp-2 bg-secondary/40 px-2 py-1.5 rounded-lg border border-border/40">
                    &ldquo;{activeClip.hook_sentence}&rdquo;
                  </p>
                )}
                {activeClip.virality_reason && (
                  <p className="text-[11px] text-muted-foreground leading-snug line-clamp-3">
                    {activeClip.virality_reason}
                  </p>
                )}
              </div>
            )}
          </div>

          {/* RIGHT PANEL: Clip Selector + AI Analysis */}
          <div className="flex-grow lg:h-full lg:overflow-y-auto flex flex-col">

            {/* Header info */}
            <div className="px-5 py-3 border-b border-border/40 flex-shrink-0">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Sumber</span>
                <span className="text-border text-xs">|</span>
                <span className="text-xs text-foreground/70 truncate max-w-[260px] font-semibold">{task.url}</span>
              </div>
              <h2 className="text-lg font-bold tracking-tight" style={{ fontFamily: "var(--font-display)" }}>
                {task.clips.length} Klip Terdeteksi
              </h2>
            </div>

            {/* Clip list */}
            <div className="flex-grow overflow-y-auto p-4 space-y-2">
              {(task.clips || []).map((clip, idx) => {
                const isActive = idx === activeClipIdx;
                return (
                  <div
                    key={idx}
                    onClick={() => setActiveClipIdx(idx)}
                    className={`p-3 rounded-xl border transition-all duration-200 cursor-pointer ${
                      isActive
                        ? "glass-panel border-[var(--accent-violet)]/40 glow-accent"
                        : "glass-panel border-transparent hover:border-[var(--accent-violet)]/20"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      {/* Index badge */}
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center font-bold text-xs flex-shrink-0 transition-all ${
                        isActive
                          ? "bg-gradient-violet text-white"
                          : "bg-secondary text-muted-foreground"
                      }`}>
                        {idx + 1}
                      </div>

                      {/* Info */}
                      <div className="flex-grow overflow-hidden min-w-0">
                        <p className={`text-sm font-bold truncate ${isActive ? "text-foreground" : "text-foreground/80"}`}>
                          {clip.title || "Klip Tanpa Judul"}
                        </p>
                        <div className="flex items-center gap-2 mt-1">
                          <ScoreBadge score={clip.score} />
                          <span className="text-xs text-muted-foreground flex items-center gap-1 font-semibold">
                            <Clock className="w-2.5 h-2.5" />
                            {formatClock(clip.start_time)}–{formatClock(clip.end_time)}
                          </span>
                          <span className="text-xs text-muted-foreground/60">
                            ({formatClock(clip.end_time - clip.start_time)})
                          </span>
                        </div>
                      </div>

                      <ChevronRight className={`w-3.5 h-3.5 flex-shrink-0 transition-transform ${
                        isActive ? "text-[var(--accent-violet)] translate-x-0.5" : "text-muted-foreground/40"
                      }`} />
                    </div>
                  </div>
                );
              })}
            </div>

          </div>
        </div>
      ) : (
        /* ── PROCESSING / QUEUED ── */
        <div className="max-w-5xl mx-auto px-6 py-10 space-y-8 flex-grow w-full">

          <div className="space-y-8 animate-in fade-in duration-500">
            <div className={`grid grid-cols-1 ${showLogs ? "lg:grid-cols-12" : "grid-cols-1"} gap-6 items-start`}>
              <div className={showLogs ? "lg:col-span-7" : "w-full"}>
                <ProgressView task={task} />
              </div>

              {showLogs && (
                <div className="lg:col-span-5 bg-zinc-950 text-zinc-300 border border-zinc-800 rounded-2xl p-4 font-mono text-xs flex flex-col h-[320px] lg:h-[340px]">
                  <div className="flex items-center justify-between border-b border-zinc-800 pb-3 mb-3">
                    <div className="flex items-center gap-2">
                      <span className="relative flex h-1.5 w-1.5">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--accent-violet)] opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-[var(--accent-violet)]"></span>
                      </span>
                      <span className="text-xs uppercase font-bold tracking-wider text-zinc-400">Konsol Log Realtime</span>
                    </div>
                    <button
                      onClick={() => {
                        setLogs([]);
                        if (taskId) localStorage.removeItem(`clip_logs_${taskId}`);
                      }}
                      className="text-xs uppercase font-bold text-zinc-500 hover:text-zinc-200 transition-colors cursor-pointer"
                    >
                      Bersihkan
                    </button>
                  </div>

                  <div className="flex-grow overflow-y-auto space-y-1.5 pr-2 scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent">
                    {logs.length === 0 ? (
                      <div className="h-full flex items-center justify-center text-zinc-600 italic text-xs gap-2">
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        Menghubungkan ke log stream...
                      </div>
                    ) : (
                      logs.map((logStr, idx) => {
                        const match = logStr.match(/^\[(.*?)\]\s*\[(.*?)\]\s*(.*)$/);
                        if (match) {
                          const [, time, stage, msg] = match;
                          let stageColor = "text-zinc-500";
                          const st = stage.toUpperCase();
                          if (st === "DOWNLOAD") stageColor = "text-zinc-400 font-semibold";
                          else if (st === "TRANSCRIBE") stageColor = "text-zinc-400 font-semibold";
                          else if (st === "ANALYZE") stageColor = "text-zinc-300 font-semibold";
                          else if (st === "SUBTITLES") stageColor = "text-[var(--accent-violet)] font-semibold";
                          else if (st === "RENDER") stageColor = "text-[var(--accent-violet)] font-semibold";
                          else if (st === "DONE") stageColor = "text-white font-bold";
                          else if (st === "ERROR") stageColor = "text-red-400 font-bold";

                          return (
                            <div key={idx} className="border-b border-zinc-900 pb-1 text-left">
                              <span className="text-zinc-600 mr-2 select-none">[{time}]</span>
                              <span className={`${stageColor} mr-2`}>[{stage}]</span>
                              <span className="text-zinc-300 break-words font-normal">{msg}</span>
                            </div>
                          );
                        }
                        return (
                          <div key={idx} className="text-zinc-400 break-words text-left">
                            {logStr}
                          </div>
                        );
                      })
                    )}
                    <div ref={logEndRef} />
                  </div>
                </div>
              )}
            </div>

            {/* Live Streaming Rendered Clips during processing */}
            {(task.clips?.length ?? 0) > 0 && (
              <div className="space-y-4 pt-6 border-t border-border/40">
                <div className="text-left space-y-0.5">
                  <h3 className="text-base font-bold tracking-tight">Klip Selesai Dirender</h3>
                  <p className="text-xs text-muted-foreground">
                    {task.clips?.length ?? 0} klip siap · sisa masih diproduksi...
                  </p>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                  {task.clips.map((clip, i) => {
                    const clipUrl = clip.clip_url
                      ? clip.clip_url.startsWith("http")
                        ? clip.clip_url
                        : `${API_URL}${clip.clip_url.startsWith("/") ? "" : "/"}${clip.clip_url}`
                      : "";
                    return (
                      <div key={i} className="rounded-xl glass-panel overflow-hidden flex flex-col hover:glow-accent transition-all duration-300">
                        <div className="aspect-[9/16] w-full bg-black relative">
                          {clipUrl ? (
                            <VerticalPlayer src={clipUrl} />
                          ) : (
                            <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground gap-2">
                              <Loader2 className="w-4 h-4 animate-spin" />
                              <p className="text-[10px] font-bold uppercase tracking-wider">Render...</p>
                            </div>
                          )}
                        </div>
                        <div className="p-2.5 border-t border-border/40 space-y-1.5">
                          <p className="font-bold text-xs line-clamp-1">{clip.title || "Klip Tanpa Judul"}</p>
                          <ScoreBadge score={clip.score} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

        </div>
      )}
    </div>
  );
}

export default function TaskPage() {
  return (
    <Suspense fallback={
      <div className="h-screen bg-background p-6 flex flex-col items-center justify-center">
        <div className="max-w-md w-full space-y-6 text-center">
          <Loader2 className="w-8 h-8 animate-spin text-[var(--accent-violet)] mx-auto" />
          <p className="text-sm font-bold uppercase tracking-wider text-muted-foreground">Memuat Halaman Tugas...</p>
        </div>
      </div>
    }>
      <TaskPageContent />
    </Suspense>
  );
}
