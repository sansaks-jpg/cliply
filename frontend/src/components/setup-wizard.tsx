"use client";

import { useState } from "react";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Folder, HardDrive, CheckCircle2, ArrowRight, FolderOpen } from "lucide-react";

interface SetupWizardProps {
  defaultStorageDir: string;
  onPickDir: () => Promise<string | null>;
  onComplete: (path: string) => void;
}

export function SetupWizard({
  defaultStorageDir,
  onPickDir,
  onComplete,
}: SetupWizardProps) {
  const [step, setStep] = useState<1 | 2>(1);
  const [selectedDir, setSelectedDir] = useState<string>(defaultStorageDir);
  const [isCustom, setIsCustom] = useState<boolean>(false);
  const [picking, setPicking] = useState<boolean>(false);

  const handlePickCustom = async () => {
    setPicking(true);
    try {
      const path = await onPickDir();
      if (path) {
        setSelectedDir(path);
        setIsCustom(true);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setPicking(false);
    }
  };

  const handleNext = () => {
    if (step === 1) {
      setStep(2);
    } else {
      onComplete(selectedDir);
    }
  };

  return (
    <AlertDialog open={true}>
      <AlertDialogContent className="max-w-md bg-neutral-950 border border-neutral-800 text-neutral-100 p-6 glow-accent-lg rounded-xl">
        <AlertDialogHeader className="hidden">
          <AlertDialogTitle>Setup Cliply</AlertDialogTitle>
          <AlertDialogDescription>Konfigurasi penyimpanan awal Cliply</AlertDialogDescription>
        </AlertDialogHeader>

        {step === 1 ? (
          <div className="flex flex-col items-center text-center space-y-6 py-4 animate-in fade-in duration-300">
            <div className="relative flex items-center justify-center w-20 h-20 rounded-full bg-neutral-900 border border-neutral-800">
              <Folder className="w-10 h-10 text-white" />
              <div className="absolute -top-1 -right-1 flex h-4 w-4">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-4 w-4 bg-emerald-500"></span>
              </div>
            </div>

            <div className="space-y-2">
              <h2 className="text-2xl font-bold tracking-tight text-white">
                Selamat datang di <span className="text-white bg-white/10 px-2 py-0.5 rounded border border-white/15">Cliply</span>
              </h2>
              <p className="text-sm text-neutral-400 max-w-xs mx-auto">
                Pemotong video AI otomatis Anda. Sebelum mulai, mari tentukan di mana video hasil pemrosesan akan disimpan.
              </p>
            </div>

            <Button
              onClick={handleNext}
              className="w-full bg-white hover:bg-neutral-200 text-neutral-950 font-semibold gap-2 transition-all duration-200 py-6"
            >
              Lanjutkan Setup <ArrowRight className="w-4 h-4" />
            </Button>
          </div>
        ) : (
          <div className="flex flex-col space-y-6 py-2 animate-in fade-in duration-300">
            <div className="space-y-1">
              <h3 className="text-lg font-bold text-white">Pilih Lokasi Penyimpanan</h3>
              <p className="text-xs text-neutral-400">
                Semua video mentah, transkrip, dan hasil render klip akan disimpan di folder ini.
              </p>
            </div>

            <div className="space-y-3">
              {/* Option 1: Default */}
              <button
                type="button"
                onClick={() => {
                  setSelectedDir(defaultStorageDir);
                  setIsCustom(false);
                }}
                className={`w-full text-left p-4 rounded-lg border transition-all duration-200 bg-neutral-900/50 hover:bg-neutral-900 ${
                  !isCustom
                    ? "border-white bg-neutral-900"
                    : "border-neutral-800 hover:border-neutral-700"
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <HardDrive className={`w-5 h-5 ${!isCustom ? "text-white" : "text-neutral-400"}`} />
                    <div>
                      <div className="font-semibold text-sm text-white">Lokasi Default (App Data)</div>
                      <div className="text-[10px] text-emerald-400 font-medium">Direkomendasikan</div>
                    </div>
                  </div>
                  {!isCustom && <CheckCircle2 className="w-5 h-5 text-white" />}
                </div>
                <div className="mt-3 font-mono text-[10px] text-neutral-400 break-all bg-neutral-950 p-2 rounded border border-neutral-800">
                  {defaultStorageDir}
                </div>
              </button>

              {/* Option 2: Custom */}
              <button
                type="button"
                onClick={handlePickCustom}
                disabled={picking}
                className={`w-full text-left p-4 rounded-lg border transition-all duration-200 bg-neutral-900/50 hover:bg-neutral-900 ${
                  isCustom
                    ? "border-white bg-neutral-900"
                    : "border-neutral-800 hover:border-neutral-700"
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <FolderOpen className={`w-5 h-5 ${isCustom ? "text-white" : "text-neutral-400"}`} />
                    <div>
                      <div className="font-semibold text-sm text-white">Pilih Folder Sendiri</div>
                      <div className="text-[10px] text-neutral-400">Tentukan lokasi folder kustom</div>
                    </div>
                  </div>
                  {isCustom && <CheckCircle2 className="w-5 h-5 text-white" />}
                </div>
                {isCustom && (
                  <div className="mt-3 font-mono text-[10px] text-neutral-200 break-all bg-neutral-950 p-2 rounded border border-neutral-800">
                    {selectedDir}
                  </div>
                )}
              </button>
            </div>

            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => setStep(1)}
                className="border-neutral-800 text-neutral-300 hover:bg-neutral-900 hover:text-white"
              >
                Kembali
              </Button>
              <Button
                onClick={() => onComplete(selectedDir)}
                disabled={picking}
                className="flex-1 bg-white hover:bg-neutral-200 text-neutral-950 font-semibold"
              >
                Mulai Cliply
              </Button>
            </div>
          </div>
        )}
      </AlertDialogContent>
    </AlertDialog>
  );
}
