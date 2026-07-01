"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import {
  Youtube,
  Loader2,
  ArrowRight,
  Trash2,
  History,
  Video,
  ExternalLink
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ThemeToggle } from "@/components/theme-toggle";
import { API_URL, deleteTask, waitForBackend, type BackendStatus } from "@/lib/api";
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

export default function Home() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [urlFocused, setUrlFocused] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [activeTasks, setActiveTasks] = useState<Array<{task_id: string; url: string; progress: number; status: string}>>([]);
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("checking");
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const settingsRef = useRef<AppSettings | null>(null);
  useEffect(() => {
    settingsRef.current = settings;
  }, [settings]);
  const [showSetup, setShowSetup] = useState(false);
  const [recentTasks, setRecentTasks] = useState<RecentTask[]>([]);

  useEffect(() => {
    const tauriActive = isTauri();
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

      // Listen to Tauri backend lifecycle events
      import("@tauri-apps/api/event").then(({ listen }) => {
        const unlistenCrashed = listen<number>("backend-crashed", (event) => {
          console.error("[Tauri] Backend crashed with exit code:", event.payload);
          setBackendStatus("unavailable");
          toast.error(`Server backend berhenti tidak terduga (kode: ${event.payload}). Silakan restart aplikasi.`);
        });
        const unlistenError = listen<string>("backend-error", (event) => {
          console.error("[Tauri] Backend error:", event.payload);
          setBackendStatus("unavailable");
          toast.error("Server backend gagal dimulai. Periksa log untuk detail.");
        });
        // Cleanup on unmount
        return () => {
          unlistenCrashed.then((fn) => fn());
          unlistenError.then((fn) => fn());
        };
      }).catch(console.error);
    }
  }, []);

  // Poll active tasks
  useEffect(() => {
    const fn = async () => {
      try {
        const res = await fetch(API_URL + '/tasks');
        if (res.ok) {
          const data = await res.json();
          setActiveTasks((data.tasks||[]).filter((t: {status:string}) => t.status === 'processing' || t.status === 'queued'));
        }
      } catch (e) {
        console.warn("Failed to poll active tasks:", e);
      }
    };
    fn();
    const id = setInterval(fn, 10000);
    return () => clearInterval(id);
  }, []);

  // Load recent tasks from localStorage and sync from backend
  useEffect(() => {
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
        console.warn("Failed to parse local tasks", e);
      }
    }

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
        const currentList = localStorage.getItem("cliply_recent_tasks");
        let localTasks: RecentTask[] = [];
        if (currentList) {
          try { localTasks = JSON.parse(currentList); } catch { {} }
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
        console.warn("Failed to sync tasks:", e);
      }
    };
    syncBackendTasks();
  }, []);

  // Wait for backend to be ready
  useEffect(() => {
    waitForBackend(30_000, 1_000).then((status) => {
      setBackendStatus(status);
    });
  }, []);

  const isValid = YOUTUBE_RE.test(url.trim());

  // Fetch video preview info and redirect to studio workspace
  const handlePreview = useCallback(async () => {
    if (!isValid || previewLoading) return;
    setPreviewLoading(true);
    try {
      const res = await fetch(API_URL + '/video-info?url=' + encodeURIComponent(url.trim()));
      if (!res.ok) throw new Error("Gagal mengambil info video");
      const data = await res.json();
      if (!data.title) throw new Error("Video tidak ditemukan atau tidak valid");
      
      // Redirect ke /customize dengan query parameter url
      router.push(`/customize?url=${encodeURIComponent(url.trim())}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Gagal mengambil info video.");
    } finally {
      setPreviewLoading(false);
    }
  }, [isValid, previewLoading, url, router]);

  // Auto-fetch and redirect on paste
  useEffect(() => {
    const trimmedUrl = url.trim();
    if (YOUTUBE_RE.test(trimmedUrl)) {
      const timer = setTimeout(() => {
        if (!previewLoading) {
          void handlePreview();
        }
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [url, previewLoading, handlePreview]);

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
    <div className="h-screen overflow-y-auto bg-transparent text-foreground transition-colors duration-300 flex flex-col font-sans antialiased overflow-x-hidden relative">
      <div className="fixed inset-0 pointer-events-none -z-10 overflow-hidden">
        <div className="absolute top-[-12%] left-[-8%] w-[44rem] h-[44rem] rounded-full blur-[120px] opacity-25 dark:opacity-40 bg-[radial-gradient(circle_at_center,var(--accent-violet),transparent_70%)] animate-blob" />
        <div className="absolute bottom-[-18%] right-[-10%] w-[40rem] h-[40rem] rounded-full blur-[120px] opacity-20 dark:opacity-35 bg-[radial-gradient(circle_at_center,var(--accent-indigo),transparent_70%)] animate-blob-2" />
      </div>

      {/* Top Header */}
      <header className="border-b border-border/60 sticky top-0 z-30 glass">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Image src="/logo-rectangle.png" alt="cliply" width={110} height={30} priority className="h-9 w-auto" />
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* Main Landing Area */}
      <main className="max-w-4xl w-full mx-auto px-4 sm:px-6 py-8 sm:py-12 flex-grow flex flex-col justify-center gap-10">
        {backendStatus === "unavailable" && (
          <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-4 flex items-start gap-3">
            <div className="w-8 h-8 rounded-lg bg-red-500/20 flex items-center justify-center flex-shrink-0 mt-0.5 font-bold text-red-400">!</div>
            <div className="space-y-1">
              <p className="text-sm font-semibold text-red-400">Backend tidak dapat dihubungi</p>
              <p className="text-xs text-muted-foreground">Server lokal di localhost:8003 tidak merespons. Pastikan backend Python sudah berjalan.</p>
            </div>
          </div>
        )}

        {/* Active Tasks Banner */}
        {activeTasks.length > 0 && (
          <div className="w-full bg-gradient-to-r from-[var(--accent-violet)]/10 to-[var(--accent-indigo)]/10 border border-[var(--accent-violet)]/30 rounded-2xl p-3 space-y-2">
            {activeTasks.slice(0, 3).map((t) => (
              <Link key={t.task_id} href={`/tasks?id=${t.task_id}`} className="flex items-center gap-3 hover:opacity-80 transition-opacity">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--accent-violet)] opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-[var(--accent-violet)]"></span>
                </span>
                <span className="text-xs font-semibold truncate">{t.url?.slice(0, 60)}</span>
                <span className="text-xs text-muted-foreground ml-auto">{Math.round(t.progress)}%</span>
              </Link>
            ))}
          </div>
        )}

        <div className="space-y-12 py-10 flex-grow flex flex-col justify-center w-full animate-in fade-in duration-500">
          <section className="text-center space-y-5">
            <h1
              className="text-4xl sm:text-6xl font-extrabold tracking-tight leading-[1.05]"
              style={{ fontFamily: "var(--font-display)" }}
            >
              Ubah Video Panjang
              <br />
              <span className="text-gradient-violet">Menjadi Shorts Viral</span>
            </h1>
            <p className="text-sm sm:text-base text-muted-foreground max-w-lg mx-auto leading-relaxed">
              Studio terpadu untuk ekstraksi klip viral, pelacakan wajah cerdas (Smart Crop),
              dan penempelan gaya teks karaoke secara otomatis.
            </p>
          </section>

          <div className="w-full space-y-12">
            <div
              className={`relative flex items-center p-1.5 rounded-2xl glass-panel transition-all duration-300 ${
                urlFocused
                  ? "ring-2 ring-[var(--accent-violet)]/40 glow-accent-md scale-[1.005]"
                  : "ring-1 ring-border/40 hover:ring-border/60"
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
                type="button"
                disabled={!isValid || previewLoading}
                onClick={handlePreview}
                className="absolute right-2 h-9 px-5 rounded-xl bg-gradient-violet hover:opacity-90 font-bold text-sm transition-all disabled:opacity-30 disabled:cursor-default shadow-md flex items-center gap-1.5 cursor-pointer"
              >
                {previewLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Memuat...</span>
                  </>
                ) : (
                  <>
                    <span>Lanjutkan</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </Button>
            </div>
            {url.trim() !== "" && !isValid && (
              <p className="text-[10px] text-zinc-500 text-center mt-2 pl-4">
                Format didukung: youtube.com/watch?v=ID, youtu.be/ID, atau youtube.com/shorts/ID
              </p>
            )}

            {/* Riwayat Workspace Proyek */}
            <div className="space-y-4 pt-10 border-t border-border/10">
              <div className="flex items-center gap-2 text-muted-foreground font-bold text-xs uppercase tracking-wider">
                <History className="w-4 h-4 text-[var(--accent-violet)]" />
                <span>Riwayat Workspace Proyek</span>
              </div>

              {recentTasks.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
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
                          className="text-muted-foreground hover:text-red-500 hover:bg-red-500/10 w-9 h-9 rounded-lg opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity cursor-pointer"
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
              ) : (
                <div className="rounded-2xl border border-dashed border-border/60 bg-secondary/5 p-8 text-center space-y-3">
                  <div className="w-10 h-10 rounded-full bg-secondary/60 flex items-center justify-center mx-auto text-muted-foreground/60">
                    <Video className="w-5 h-5" />
                  </div>
                  <div className="space-y-1">
                    <p className="text-sm font-bold">Belum Ada Riwayat Proyek</p>
                    <p className="text-xs text-muted-foreground max-w-sm mx-auto leading-relaxed">
                      Semua klip video yang Anda buat akan muncul di sini untuk memudahkan akses kembali ke workspace.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>

      {showSetup && (
        <SetupWizard
          defaultStorageDir={settings?.storage_dir || ""}
          onComplete={handleSetupComplete}
          onPickDir={handlePickDir}
        />
      )}

      <footer className="border-t border-border/60 py-8 text-center text-xs text-muted-foreground mt-12">
        <p>© {new Date().getFullYear()} cliply</p>
      </footer>
    </div>
  );
}
