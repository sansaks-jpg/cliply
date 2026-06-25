"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  isTauri,
  getSettings,
  setStorageDir,
  saveAppSettings,
  pickStorageDir,
  openStorageDir,
  restartBackend,
  relaunchApp,
  type AppSettings,
} from "@/lib/tauri";
import { waitForBackend, getAvailableModels, type BackendStatus } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ArrowLeft,
  FolderOpen,
  ExternalLink,
  AlertTriangle,
  RefreshCw,
  Server,
  Settings as SettingsIcon,
  Sparkles,
  Key,
  Globe,
  Save,
  ArrowUpCircle,
  Download,
} from "lucide-react";
import { toast } from "sonner";

interface TauriUpdateEvent {
  event: string;
  data?: Record<string, unknown>;
}

interface TauriUpdate {
  version: string;
  date?: string;
  downloadAndInstall: (onEvent?: (event: TauriUpdateEvent) => void, options?: Record<string, unknown>) => Promise<void>;
}

export default function SettingsPage() {
  const [tauriActive, setTauriActive] = useState<boolean | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("checking");
  const [restarting, setRestarting] = useState<boolean>(false);

  // States untuk update
  const [checkingUpdate, setCheckingUpdate] = useState<boolean>(false);
  const [updateAvailable, setUpdateAvailable] = useState<TauriUpdate | null>(null);
  const [appVersion, setAppVersion] = useState<string>("0.1.2");

  const handleCheckUpdate = async () => {
    if (!tauriActive) {
      toast.info("Fitur pembaruan hanya tersedia di dalam aplikasi desktop Cliply.");
      return;
    }
    if (checkingUpdate || restarting) return;
    setCheckingUpdate(true);
    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const updateResult = await check();
      
      if (updateResult) {
        setUpdateAvailable(updateResult);
        toast.success(`Pembaruan versi v${updateResult.version} ditemukan!`);
      } else {
        toast.info("Aplikasi Anda sudah versi terbaru.");
      }
    } catch (err) {
      console.error("Gagal memeriksa pembaruan:", err);
      toast.error("Gagal memeriksa pembaruan. Pastikan Anda terhubung ke internet.");
    } finally {
      setCheckingUpdate(false);
    }
  };

  const handleInstallUpdate = async () => {
    if (!tauriActive) return;
    if (!updateAvailable || restarting) return;
    setRestarting(true);
    toast.info("Mengunduh dan memasang pembaruan...");
    try {
      let downloaded = 0;
      let contentLength = 0;
      await updateAvailable.downloadAndInstall((event: TauriUpdateEvent) => {
        switch (event.event) {
          case 'Started':
            contentLength = (event.data?.contentLength as number) || 0;
            toast.info(`Unduhan dimulai: ${contentLength} byte.`);
            break;
          case 'Progress':
            downloaded += (event.data?.chunkLength as number) || 0;
            break;
          case 'Finished':
            toast.success("Unduhan selesai. Memasang pembaruan...");
            break;
        }
      });
      
      toast.success("Pembaruan berhasil dipasang! Menjalankan ulang aplikasi...");
      setTimeout(async () => {
        await relaunchApp();
      }, 2000);
    } catch (err) {
      console.error(err);
      toast.error("Gagal mengunduh atau memasang pembaruan.");
      setRestarting(false);
    }
  };

  // States untuk form API
  const [llmProvider, setLlmProvider] = useState<string>("openai");
  const [geminiApiKey, setGeminiApiKey] = useState<string>("");
  const [groqApiKey, setGroqApiKey] = useState<string>("");
  const [openaiApiKey, setOpenaiApiKey] = useState<string>("");
  const [openaiBaseUrl, setOpenaiBaseUrl] = useState<string>("");
  const [openaiModel, setOpenaiModel] = useState<string>("gpt-4o-mini");
  const [availableModels, setAvailableModels] = useState<string[]>(["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]);
  const [loadingModels, setLoadingModels] = useState<boolean>(false);

  const loadModels = async (baseUrl: string, apiKey: string) => {
    if (!baseUrl) {
      setAvailableModels(["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]);
      return;
    }
    setLoadingModels(true);
    try {
      const models = await getAvailableModels(baseUrl, apiKey);
      setAvailableModels(models);
      if (models.length > 0 && !models.includes(openaiModel)) {
        const mimoModel = models.find((m: string) => m.toLowerCase().includes("mimo"));
        setOpenaiModel(mimoModel || models[0]);
      }
    } catch (err) {
      console.warn("Failed to fetch models from custom base URL proxy:", err);
      toast.error(err instanceof Error ? `Gagal mengambil daftar model: ${err.message}` : "Gagal mengambil daftar model.");
      if (baseUrl.includes("localhost") || baseUrl.includes("127.0.0.1")) {
        setAvailableModels(["mimo/mimo-v2.5-pro", "gpt-4o-mini", "gpt-4o"]);
      }
    } finally {
      setLoadingModels(false);
    }
  };

  useEffect(() => {
    const active = isTauri();
    setTauriActive(active);

    if (active) {
      getSettings().then((s) => {
        if (s) {
          setSettings(s);
          setLlmProvider(s.llm_provider || "openai");
          setGeminiApiKey(s.gemini_api_key || "");
          setGroqApiKey(s.groq_api_key || "");
          setOpenaiApiKey(s.openai_api_key || "");
          setOpenaiBaseUrl(s.openai_base_url || "");
          const modelVal = s.openai_model || "gpt-4o-mini";
          setOpenaiModel(modelVal);
          loadModels(s.openai_base_url || "", s.openai_api_key || "");
        }
      });
      import("@tauri-apps/api/app").then(({ getVersion }) => {
        getVersion().then(setAppVersion).catch(console.error);
      }).catch(console.error);
      checkBackend();
    }
  }, []);

  const checkBackend = () => {
    setBackendStatus("checking");
    waitForBackend(5000, 500).then((status) => {
      setBackendStatus(status);
    });
  };

  const handlePickDir = async () => {
    if (restarting) return;
    try {
      const selected = await pickStorageDir();
      if (!selected) return;

      setRestarting(true);
      toast.info("Mengubah folder penyimpanan dan menyalakan ulang backend...");
      
      // 1. Simpan path baru
      const updated = { ...settings!, storage_dir: selected };
      await saveAppSettings(updated);
      setSettings(updated);

      // 2. Restart backend
      await restartBackend(selected);

      // 3. Tunggu backend siap
      const status = await waitForBackend(15000, 1000);
      setBackendStatus(status);

      if (status === "ready") {
        toast.success("Folder penyimpanan berhasil diubah!");
      } else {
        toast.error("Gagal menyambungkan ke backend setelah restart.");
      }
    } catch (err) {
      console.error(err);
      toast.error("Terjadi kesalahan saat mengubah folder.");
    } finally {
      setRestarting(false);
    }
  };

  const handleSaveApiSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!settings || restarting) return;

    setRestarting(true);
    toast.info("Menyimpan konfigurasi AI dan menyalakan ulang backend...");
    try {
      const updated = {
        ...settings,
        llm_provider: llmProvider,
        gemini_api_key: geminiApiKey.trim(),
        groq_api_key: groqApiKey.trim(),
        openai_api_key: openaiApiKey.trim(),
        openai_base_url: openaiBaseUrl.trim(),
        openai_model: openaiModel.trim(),
      };

      // 1. Simpan ke settings.json
      await saveAppSettings(updated);
      setSettings(updated);

      // 2. Restart backend agar memuat Env baru
      await restartBackend(settings.storage_dir);

      // 3. Cek koneksi backend
      const status = await waitForBackend(15000, 1000);
      setBackendStatus(status);

      if (status === "ready") {
        toast.success("Kunci API berhasil disimpan & diterapkan!");
      } else {
        toast.error("Backend gagal dinyalakan ulang dengan benar.");
      }
    } catch (err) {
      console.error(err);
      toast.error("Gagal menyimpan kunci API.");
    } finally {
      setRestarting(false);
    }
  };

  const handleOpenExplorer = async () => {
    if (!settings?.storage_dir) return;
    try {
      await openStorageDir(settings.storage_dir);
    } catch (err) {
      toast.error("Gagal membuka folder di explorer.");
    }
  };

  if (tauriActive === null) {
    return (
      <div className="h-screen bg-black text-neutral-100 flex flex-col items-center justify-center p-4">
        <div className="flex items-center gap-3 text-neutral-400">
          <RefreshCw className="w-5 h-5 animate-spin" />
          <span className="text-sm">Memuat pengaturan...</span>
        </div>
      </div>
    );
  }

  if (!tauriActive) {
    return (
      <div className="h-screen bg-black text-neutral-100 flex flex-col items-center justify-center p-4">
        <div className="max-w-md w-full bg-neutral-900 border border-neutral-800 rounded-xl p-6 text-center space-y-4">
          <SettingsIcon className="w-12 h-12 text-neutral-500 mx-auto" />
          <h2 className="text-xl font-bold text-white">Pengaturan Desktop</h2>
          <p className="text-sm text-neutral-400">
            Halaman pengaturan ini hanya tersedia ketika Cliply dijalankan dalam aplikasi desktop.
          </p>
          <div className="pt-2">
            <Link href="/">
              <Button className="bg-white hover:bg-neutral-200 text-neutral-950 font-medium">
                Kembali ke Beranda
              </Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen overflow-y-auto bg-black text-neutral-100 p-6 md:p-12">
      <div className="max-w-3xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between pb-6 border-b border-neutral-800">
          <div className="flex items-center gap-4">
            <Link href="/" className="p-2 hover:bg-neutral-900 rounded-lg transition-colors border border-transparent hover:border-neutral-800">
              <ArrowLeft className="w-5 h-5 text-neutral-300" />
            </Link>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-white">Pengaturan</h1>
              <p className="text-xs text-neutral-400">Konfigurasi folder penyimpanan dan kunci API AI</p>
            </div>
          </div>

          <div className="flex items-center gap-2 px-3 py-1.5 bg-neutral-900 border border-neutral-800 rounded-full text-xs font-medium">
            <Server className={`w-3.5 h-3.5 ${backendStatus === "ready" ? "text-emerald-500" : "text-rose-500"}`} />
            <span>Backend: {backendStatus === "ready" ? "Ready" : "Offline"}</span>
            <div className={`w-2 h-2 rounded-full ${backendStatus === "ready" ? "bg-emerald-500 animate-pulse" : "bg-rose-500"}`} />
          </div>
        </div>

        {/* 1. Storage Settings */}
        <div className="bg-neutral-900/50 border border-neutral-800 rounded-xl p-6 space-y-6 backdrop-blur-md">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold text-white">Lokasi Penyimpanan</h2>
            <p className="text-xs text-neutral-400">
              Ubah lokasi penyimpanan video mentah, transkrip, cache pemrosesan, dan hasil render klip.
            </p>
          </div>

          <div className="font-mono text-xs text-neutral-300 break-all bg-neutral-950 p-4 rounded-lg border border-neutral-800">
            {settings?.storage_dir || "Loading..."}
          </div>

          <div className="flex flex-wrap gap-3">
            <Button
              onClick={handlePickDir}
              disabled={restarting}
              className="bg-white hover:bg-neutral-200 text-neutral-950 font-medium gap-2"
            >
              <FolderOpen className="w-4 h-4" />
              {restarting ? "Menghubungkan Ulang..." : "Ubah Lokasi"}
            </Button>
            <Button
              variant="outline"
              onClick={handleOpenExplorer}
              disabled={!settings?.storage_dir}
              className="border-neutral-800 text-neutral-300 hover:bg-neutral-900 hover:text-white gap-2"
            >
              <ExternalLink className="w-4 h-4" />
              Buka di Explorer
            </Button>
            {backendStatus !== "ready" && (
              <Button
                variant="ghost"
                onClick={checkBackend}
                className="text-neutral-400 hover:text-white gap-2"
              >
                <RefreshCw className="w-4 h-4" />
                Cek Ulang Koneksi
              </Button>
            )}
          </div>
        </div>

        {/* 1.5. App Update Settings */}
        <div className="bg-neutral-900/50 border border-neutral-800 rounded-xl p-6 space-y-6 backdrop-blur-md">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold text-white">Pembaruan Aplikasi</h2>
            <p className="text-xs text-neutral-400">
              Periksa dan pasang versi terbaru Cliply yang dirilis di GitHub Releases.
            </p>
          </div>

          {updateAvailable ? (
            <div className="p-4 bg-emerald-500/5 border border-emerald-500/10 rounded-lg flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="space-y-1">
                <div className="text-sm font-bold text-emerald-400 flex items-center gap-1.5">
                  <ArrowUpCircle className="w-4 h-4" />
                  Versi Baru v{updateAvailable.version} Tersedia!
                </div>
                <p className="text-xs text-neutral-400 leading-relaxed">
                  Rilis tanggal {updateAvailable.date || "baru-baru ini"}. Klik tombol di samping untuk memasang.
                </p>
              </div>
              <Button
                onClick={handleInstallUpdate}
                disabled={restarting}
                className="bg-emerald-500 hover:bg-emerald-600 text-neutral-950 font-bold gap-2 self-start md:self-auto rounded-xl"
              >
                <Download className="w-4 h-4" />
                Unduh & Pasang
              </Button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              <Button
                onClick={handleCheckUpdate}
                disabled={checkingUpdate || restarting}
                className="bg-white hover:bg-neutral-200 text-neutral-950 font-semibold gap-2 rounded-xl"
              >
                <RefreshCw className={`w-4 h-4 ${checkingUpdate ? "animate-spin" : ""}`} />
                {checkingUpdate ? "Memeriksa..." : "Periksa Pembaruan"}
              </Button>
              <span className="text-xs text-neutral-500 font-mono">
                Versi Saat Ini: v{appVersion}
              </span>
            </div>
          )}
        </div>

        {/* 2. AI Key Settings */}
        <form onSubmit={handleSaveApiSettings} className="bg-neutral-900/50 border border-neutral-800 rounded-xl p-6 space-y-6 backdrop-blur-md">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold text-white">Model AI & Kunci API</h2>
            <p className="text-xs text-neutral-400">
              Masukkan kunci API untuk penyedia kecerdasan buatan (Gemini & OpenAI) untuk memproses video.
            </p>
          </div>

          <div className="space-y-4">
            {/* LLM Provider Selection */}
            <div className="space-y-2">
              <Label htmlFor="provider" className="text-xs font-bold text-muted-foreground flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5" />
                AI Highlight Provider
              </Label>
              <Select value={llmProvider} onValueChange={setLlmProvider}>
                <SelectTrigger id="provider" className="bg-background/40 border-border rounded-xl h-10 text-sm font-semibold shadow-none">
                  <SelectValue placeholder="Pilih Provider" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="openai">OpenAI (GPT-4o / Mimo Local)</SelectItem>
                  <SelectItem value="gemini">Google Gemini</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Gemini API Key */}
            <div className="space-y-2">
              <Label htmlFor="gemini-key" className="text-xs font-bold text-muted-foreground flex items-center gap-1.5">
                <Key className="w-3.5 h-3.5" />
                Google Gemini API Key
              </Label>
              <Input
                id="gemini-key"
                type="password"
                placeholder="AIzaSy..."
                value={geminiApiKey}
                onChange={(e) => setGeminiApiKey(e.target.value)}
                className="h-10 text-sm border-border bg-background/20 rounded-xl focus-visible:ring-1 focus-visible:ring-white/20"
              />
              <p className="text-[10px] text-neutral-400">
                Wajib digunakan untuk proses transkripsi suara & identifikasi nama pembicara (*diarization*).
              </p>
            </div>

            {/* Groq API Key */}
            <div className="space-y-2">
              <Label htmlFor="groq-key" className="text-xs font-bold text-muted-foreground flex items-center gap-1.5">
                <Key className="w-3.5 h-3.5" />
                Groq API Key
              </Label>
              <Input
                id="groq-key"
                type="password"
                placeholder="gsk_..."
                value={groqApiKey}
                onChange={(e) => setGroqApiKey(e.target.value)}
                className="h-10 text-sm border-border bg-background/20 rounded-xl focus-visible:ring-1 focus-visible:ring-white/20"
              />
              <p className="text-[10px] text-neutral-400">
                Opsional — digunakan untuk transkripsi suara (Whisper). Kosongkan jika pakai Gemini untuk transkripsi.
              </p>
            </div>

            {/* OpenAI API Key */}
            <div className="space-y-2">
              <Label htmlFor="openai-key" className="text-xs font-bold text-muted-foreground flex items-center gap-1.5">
                <Key className="w-3.5 h-3.5" />
                OpenAI API Key
              </Label>
              <Input
                id="openai-key"
                type="password"
                placeholder="sk-proj-..."
                value={openaiApiKey}
                onChange={(e) => setOpenaiApiKey(e.target.value)}
                className="h-10 text-sm border-border bg-background/20 rounded-xl focus-visible:ring-1 focus-visible:ring-white/20"
              />
              <p className="text-[10px] text-neutral-400">
                Wajib jika menggunakan Provider OpenAI. Masukkan API Key Anda, atau kosongkan jika menggunakan model lokal.
              </p>
            </div>

            {/* OpenAI Base URL Override */}
            <div className="space-y-2">
              <Label htmlFor="openai-url" className="text-xs font-bold text-muted-foreground flex items-center gap-1.5">
                <Globe className="w-3.5 h-3.5" />
                OpenAI Base URL Override (Opsional)
              </Label>
              <Input
                id="openai-url"
                type="text"
                placeholder="http://localhost:20128/v1"
                value={openaiBaseUrl}
                onChange={(e) => setOpenaiBaseUrl(e.target.value)}
                className="h-10 text-sm font-mono border-border bg-background/20 rounded-xl focus-visible:ring-1 focus-visible:ring-white/20"
              />
              <p className="text-[10px] text-neutral-400">
                Kosongkan untuk menggunakan server OpenAI resmi, atau arahkan ke API model lokal (misal: `http://localhost:20128/v1`).
              </p>
            </div>

            {/* OpenAI Model Selection & Custom Input */}
            <div className="space-y-2">
              <Label htmlFor="openai-model" className="text-xs font-bold text-muted-foreground flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5" />
                OpenAI Model
              </Label>
              <div className="flex gap-2">
                <div className="flex-grow">
                  <Select value={availableModels.includes(openaiModel) ? openaiModel : "custom"} onValueChange={(val) => {
                    if (val !== "custom") {
                      setOpenaiModel(val);
                    }
                  }}>
                    <SelectTrigger id="openai-model" className="bg-background/40 border-border rounded-xl h-10 text-sm font-semibold shadow-none">
                      <SelectValue placeholder="Pilih Model" />
                    </SelectTrigger>
                    <SelectContent>
                      {availableModels.map((m) => (
                        <SelectItem key={m} value={m}>{m}</SelectItem>
                      ))}
                      <SelectItem value="custom">Kustom (Tulis di Bawah)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => loadModels(openaiBaseUrl, openaiApiKey)}
                  disabled={loadingModels}
                  className="border-neutral-800 text-neutral-300 hover:bg-neutral-900 rounded-xl h-10 px-3 flex-shrink-0"
                  title="Muat Ulang Model"
                  aria-label="Muat Ulang Model"
                >
                  <RefreshCw className={`w-4 h-4 ${loadingModels ? "animate-spin" : ""}`} />
                </Button>
              </div>
              <Input
                type="text"
                placeholder="Masukkan nama model secara manual"
                value={openaiModel}
                onChange={(e) => setOpenaiModel(e.target.value)}
                className="h-10 text-sm border-border bg-background/20 rounded-xl focus-visible:ring-1 focus-visible:ring-white/20 mt-2"
              />
              <p className="text-[10px] text-neutral-400">
                Pilih model yang terdeteksi di atas, atau ketik nama model secara manual pada kolom teks.
              </p>
            </div>
          </div>

          <div className="pt-2">
            <Button
              type="submit"
              disabled={restarting}
              className="bg-white hover:bg-neutral-200 text-neutral-950 font-bold gap-2 rounded-xl"
            >
              <Save className="w-4 h-4" />
              Simpan & Terapkan
            </Button>
          </div>
        </form>

        {/* Warning Notification Box */}
        <div className="p-4 bg-amber-500/5 border border-amber-500/10 rounded-xl flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="text-xs font-semibold text-amber-500">Penyelarasan Server Otomatis</div>
            <p className="text-[11px] text-neutral-400 leading-relaxed">
              Setiap kali Anda menekan tombol **&quot;Simpan &amp; Terapkan&quot;** atau mengubah folder penyimpanan, server backend lokal akan dimatikan lalu dinyalakan ulang dengan variabel lingkungan (*environment variables*) baru berisi API Key yang Anda masukkan. Hal ini memastikan perubahan langsung aktif tanpa perlu membuka ulang aplikasi.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
