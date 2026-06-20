"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Download,
  Loader2,
  CheckCircle,
  AlertCircle,
  Zap,
  Play,
  Scissors,
  FileVideo,
  Sparkles,
  Clock
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
  const color =
    score >= 80
      ? "bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600 dark:text-emerald-400 border border-emerald-100 dark:border-emerald-900/30"
      : score >= 60
        ? "bg-amber-50 dark:bg-amber-950/30 text-amber-600 dark:text-amber-400 border border-amber-100 dark:border-amber-900/30"
        : "bg-rose-50 dark:bg-rose-950/30 text-rose-600 dark:text-rose-400 border border-rose-100 dark:border-rose-900/30";
  return (
    <Badge className={`px-2 py-0.5 rounded-md text-xs font-semibold ${color}`}>
      <Zap className="w-3.5 h-3.5 mr-1 text-amber-500 fill-amber-500 animate-pulse" />
      Score: {score}
    </Badge>
  );
}

function ClipCard({ clip }: { clip: TaskClip }) {
  const href = clip.clip_url
    ? clip.clip_url.startsWith("http")
      ? clip.clip_url
      : `${API_URL}${clip.clip_url.startsWith("/") ? "" : "/"}${clip.clip_url}`
    : "";
  return (
    <div className="group rounded-2xl border border-stone-200/80 dark:border-stone-850 overflow-hidden bg-white dark:bg-stone-900 shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all duration-300 flex flex-col h-full">
      <div className="relative aspect-[9/16] w-full bg-stone-950 flex-shrink-0">
        {href ? (
          <VerticalPlayer src={href} />
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-stone-400 gap-2">
            <Loader2 className="w-8 h-8 animate-spin text-amber-500" />
            <p className="text-xs">Merender video...</p>
          </div>
        )}
      </div>
      <div className="p-5 flex flex-col flex-grow justify-between gap-4">
        <div className="space-y-3">
          <div className="flex items-start justify-between gap-3">
            <h3 className="font-bold text-stone-850 dark:text-stone-100 leading-snug line-clamp-2 text-sm group-hover:text-amber-500 transition-colors">
              {clip.title || "Klip Tanpa Judul"}
            </h3>
          </div>
          
          <div className="flex items-center gap-2">
            <ScoreBadge score={clip.score} />
          </div>

          <div className="flex items-center gap-2 text-xs text-stone-500 dark:text-stone-400 bg-stone-50 dark:bg-stone-950 p-2 rounded-lg border border-stone-100/50 dark:border-stone-850/50">
            <Clock className="w-3.5 h-3.5 text-stone-400" />
            <span className="font-medium">
              {formatClock(clip.start_time)} – {formatClock(clip.end_time)}
            </span>
            <span className="text-stone-300 dark:text-stone-700">·</span>
            <span className="font-semibold text-stone-700 dark:text-stone-300">
              Durasi: {formatClock(clip.end_time - clip.start_time)}
            </span>
          </div>

          {clip.hook_sentence && (
            <div className="bg-amber-50/40 dark:bg-amber-950/10 border-l-2 border-amber-400 p-2.5 rounded-r-lg">
              <span className="text-[10px] uppercase font-bold text-amber-600 dark:text-amber-400 tracking-wider block mb-0.5">Hook Kalimat</span>
              <p className="text-xs text-stone-700 dark:text-stone-300 italic font-medium leading-relaxed">&ldquo;{clip.hook_sentence}&rdquo;</p>
            </div>
          )}

          {clip.virality_reason && (
            <div className="text-xs text-stone-500 dark:text-stone-400 leading-relaxed bg-stone-50/50 dark:bg-stone-950/20 p-2.5 rounded-lg">
              <span className="font-semibold text-stone-700 dark:text-stone-300 block mb-0.5">Analisis Virabilitas:</span>
              {clip.virality_reason}
            </div>
          )}
        </div>

        <div>
          {clip.error ? (
            <Alert variant="destructive" className="py-2 px-3 rounded-xl">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription className="text-xs">Gagal render: {clip.error}</AlertDescription>
            </Alert>
          ) : (
            href && (
              <Button asChild size="sm" className="w-full h-10 rounded-xl bg-stone-900 hover:bg-stone-800 dark:bg-stone-100 dark:hover:bg-stone-200 dark:text-stone-900 font-medium transition-all shadow-sm">
                <a href={href} download={`clip-${clip.title?.toLowerCase().replace(/[^a-z0-9]/g, "-") || "short"}.mp4`}>
                  <Download className="w-4 h-4 mr-2" />
                  Unduh MP4
                </a>
              </Button>
            )
          )}
        </div>
      </div>
    </div>
  );
}

function ProgressView({ task }: { task: Task }) {
  const pct = Math.round(task.progress);
  
  // Custom icons per stage
  const getStageIcon = (stage: string) => {
    switch (stage.toUpperCase()) {
      case "DOWNLOAD":
        return <Download className="w-6 h-6 text-blue-500" />;
      case "TRANSCRIBE":
        return <Scissors className="w-6 h-6 text-purple-500" />;
      case "ANALYZE":
        return <Sparkles className="w-6 h-6 text-amber-500" />;
      default:
        return <Loader2 className="w-6 h-6 text-stone-500 animate-spin" />;
    }
  };

  return (
    <div className="max-w-md mx-auto bg-white dark:bg-stone-900 border border-stone-200/80 dark:border-stone-800/80 rounded-2xl p-8 shadow-lg dark:shadow-stone-950/30 text-center space-y-6 my-8 animate-in fade-in slide-in-from-bottom-6 duration-500">
      <div className="w-14 h-14 mx-auto rounded-full bg-stone-50 dark:bg-stone-950 flex items-center justify-center border border-stone-100 dark:border-stone-850 shadow-inner">
        {getStageIcon(task.stage || "")}
      </div>

      <div className="space-y-2">
        <h3 className="text-lg font-bold text-stone-900 dark:text-white">
          {task.stage ? `Tahap: ${task.stage}` : "Sedang memproses..."}
        </h3>
        <p className="text-sm text-stone-500 dark:text-stone-400">
          {task.message || (task.status === "queued" ? "Mengantre di server..." : "Silakan tunggu sebentar.")}
        </p>
      </div>

      {pct > 0 && (
        <div className="space-y-2 pt-2">
          <div className="h-2 bg-stone-100 dark:bg-stone-950 rounded-full overflow-hidden border border-stone-200/20 dark:border-stone-850/50">
            <div
              className="h-full bg-gradient-to-r from-amber-500 via-rose-500 to-violet-600 dark:from-amber-400 dark:via-rose-400 dark:to-violet-500 transition-all duration-700 ease-out"
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="flex items-center justify-between text-xs text-stone-400 dark:text-stone-500 px-1 font-mono">
            <span>Progress</span>
            <span className="font-bold text-stone-700 dark:text-stone-300">{pct}%</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default function TaskPage() {
  const params = useParams();
  const taskId = (params?.id as string) || "";
  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await getTask(taskId);
      setTask(data);
      setError(null);
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gagal memuat tugas");
      return null;
    }
  }, [taskId]);

  // Initial load.
  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      const data = await refresh();
      if (active) setLoading(false);
    })();
    return () => {
      active = false;
    };
  }, [refresh]);

  // SSE for live progress; reconnects itself via EventSource.
  useEffect(() => {
    if (!taskId) return;
    // Only subscribe if there's something to watch.
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
      } catch {
        /* ignore */
      }
    });

    es.addEventListener("done", () => {
      void refresh();
      es.close();
    });

    es.addEventListener("error", (e) => {
      const me = e as MessageEvent;
      if (typeof me.data === "string" && me.data.length > 0) {
        try {
          const data = JSON.parse(me.data);
          if (data?.error) setError(data.error);
        } catch {
          /* ignore */
        }
      }
      es.close();
    });

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [taskId, task?.status, refresh]);

  // Fallback polling in case SSE is interrupted.
  useEffect(() => {
    if (!task || (task.status !== "queued" && task.status !== "processing")) {
      return;
    }
    const id = setInterval(() => {
      void refresh();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [task?.status, refresh]);

  if (loading) {
    return (
      <div className="min-h-screen bg-stone-50 dark:bg-stone-950 p-6 flex flex-col items-center justify-center">
        <div className="max-w-md w-full space-y-6 text-center">
          <Loader2 className="w-10 h-10 animate-spin text-amber-500 mx-auto" />
          <p className="text-sm text-stone-500 dark:text-stone-400">Memuat data tugas...</p>
        </div>
      </div>
    );
  }

  if (error && !task) {
    return (
      <div className="min-h-screen bg-stone-50 dark:bg-stone-950 p-6 flex items-center justify-center">
        <div className="max-w-md w-full bg-white dark:bg-stone-900 p-6 rounded-2xl border border-stone-200/80 dark:border-stone-800 shadow-xl space-y-4">
          <div className="flex items-center gap-3 text-red-500 dark:text-red-400">
            <AlertCircle className="h-6 w-6 flex-shrink-0" />
            <h3 className="font-bold text-lg">Terjadi Kesalahan</h3>
          </div>
          <p className="text-sm text-stone-600 dark:text-stone-400 leading-relaxed">{error}</p>
          <div className="pt-2">
            <Link href="/" className="w-full block">
              <Button className="w-full bg-stone-900 hover:bg-stone-850 dark:bg-stone-100 dark:hover:bg-stone-200 dark:text-stone-900 rounded-xl h-11">
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

  return (
    <div className="min-h-screen bg-gradient-to-b from-stone-50 via-white to-stone-100/50 dark:from-stone-950 dark:via-stone-900 dark:to-stone-950 text-foreground transition-colors duration-300">
      {/* Top Navbar */}
      <div className="border-b border-stone-200/50 dark:border-stone-850/80 sticky top-0 bg-white/80 dark:bg-stone-900/80 backdrop-blur-md z-10 transition-colors">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link href="/">
            <Button variant="ghost" size="sm" className="rounded-lg hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors">
              <ArrowLeft className="w-4 h-4 mr-2" />
              Klip Baru
            </Button>
          </Link>
          
          <div className="flex items-center gap-3">
            <span className="text-xs text-stone-400 dark:text-stone-500 max-w-[200px] truncate hidden sm:inline-block">
              Task ID: {task.task_id}
            </span>
            <Badge
              variant="outline"
              className={`px-2.5 py-1 rounded-full text-xs font-semibold capitalize transition-all ${
                task.status === "completed"
                  ? "border-emerald-300 text-emerald-700 bg-emerald-50 dark:bg-emerald-950/20 dark:text-emerald-400 dark:border-emerald-900/30"
                  : task.status === "error"
                    ? "border-rose-300 text-rose-700 bg-rose-50 dark:bg-rose-950/20 dark:text-rose-400 dark:border-rose-900/30"
                    : "border-stone-300 text-stone-700 bg-stone-50 dark:bg-stone-950/20 dark:text-stone-400 dark:border-stone-800"
              }`}
            >
              {task.status === "completed" ? (
                <CheckCircle className="w-3.5 h-3.5 mr-1" />
              ) : task.status === "error" ? (
                <AlertCircle className="w-3.5 h-3.5 mr-1" />
              ) : (
                <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
              )}
              {task.status}
            </Badge>
            <ThemeToggle />
          </div>
        </div>
      </div>


      <div className="max-w-6xl mx-auto px-6 py-12">
        {/* Task Info & Original Video Metadata */}
        <div className="bg-white dark:bg-stone-900/40 border border-stone-200/50 dark:border-stone-850 p-6 rounded-2xl shadow-sm space-y-3 mb-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="flex items-center gap-2.5 text-stone-500 dark:text-stone-400 text-xs uppercase tracking-wider font-bold">
            <FileVideo className="w-4 h-4 text-rose-500" />
            <span>Video Asli</span>
          </div>
          <h2 className="text-xl sm:text-2xl font-extrabold text-stone-850 dark:text-stone-100 tracking-tight leading-tight word-break-all">
            {task.url}
          </h2>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-stone-400 dark:text-stone-500 font-medium">
            <span>Rasio target: {task.aspect_ratio}</span>
            <span>·</span>
            <span>Target Klip: {task.num_clips}</span>
            {task.language && (
              <>
                <span>·</span>
                <span>Bahasa: {task.language}</span>
              </>
            )}
          </div>
        </div>

        {/* Error Alert */}
        {task.status === "error" && (
          <Alert variant="destructive" className="mb-8 rounded-2xl shadow-sm border-red-200 dark:border-red-950 bg-red-50/50 dark:bg-red-950/10">
            <AlertCircle className="h-5 w-5" />
            <AlertTitle className="font-bold mb-1">Gagal Memproses Video</AlertTitle>
            <AlertDescription className="text-sm">
              {task.error || "Terjadi kegagalan pemrosesan di server. Silakan coba video YouTube lainnya."}
            </AlertDescription>
          </Alert>
        )}

        {/* Processing State */}
        {(task.status === "queued" || task.status === "processing") && (
          <div className="space-y-8">
            <ProgressView task={task} />
            
            {(task.clips?.length ?? 0) > 0 && (
              <div className="space-y-6 pt-6 border-t border-stone-200/50 dark:border-stone-850">
                <div className="text-center space-y-2">
                  <h2 className="text-2xl font-extrabold tracking-tight">Klip Sedang Dipersiapkan</h2>
                  <p className="text-sm text-stone-500 dark:text-stone-400">
                    {task.clips?.length ?? 0} klip telah selesai dirender · sedang memproses klip lainnya...
                  </p>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8">
                  {(task.clips || []).map((c, i) => (
                    <ClipCard key={`${c.start_time}-${i}`} clip={c} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Completed State */}
        {task.status === "completed" && (
          <div className="space-y-8">
            {(task.clips?.length ?? 0) === 0 ? (
              <Alert className="rounded-2xl border-stone-200 dark:border-stone-800 bg-amber-50/20 dark:bg-amber-950/10">
                <AlertCircle className="h-5 w-5 text-amber-500" />
                <AlertTitle className="font-bold mb-1">Tidak Ada Klip Dihasilkan</AlertTitle>
                <AlertDescription className="text-sm text-stone-600 dark:text-stone-400">
                  Tugas berhasil diselesaikan, tetapi tidak ada segmen viral yang memenuhi kriteria yang berhasil diidentifikasi. Video tersebut mungkin tidak memiliki struktur percakapan atau momen yang cocok untuk dijadikan klip pendek.
                </AlertDescription>
              </Alert>
            ) : (
              <div className="space-y-6">
                <div className="text-center space-y-2 mb-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
                  <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-amber-500 to-rose-500">Klip Viral Siap Diunduh!</h2>
                  <p className="text-sm text-stone-500 dark:text-stone-400">
                    AI berhasil mengekstrak {task.clips?.length ?? 0} klip viral dengan pelacakan wajah cerdas dan subtitle karaoke otomatis.
                  </p>
                </div>
                
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8">
                  {(task.clips || []).map((c, i) => (
                    <ClipCard key={`${c.start_time}-${i}`} clip={c} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

