"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Application error:", error);
  }, [error]);

  return (
    <div className="h-screen bg-background text-foreground flex flex-col items-center justify-center gap-6 font-sans antialiased p-6">
      <div className="fixed inset-0 pointer-events-none -z-10 overflow-hidden">
        <div className="absolute top-[-12%] left-[-8%] w-[44rem] h-[44rem] rounded-full blur-[120px] opacity-25 dark:opacity-40 bg-[radial-gradient(circle_at_center,rgba(124,58,237,0.5),transparent_70%)] animate-blob" />
      </div>
      <div className="w-16 h-16 rounded-2xl bg-red-500/15 flex items-center justify-center">
        <span className="text-red-400 text-2xl font-bold">!</span>
      </div>
      <div className="text-center space-y-2 max-w-md">
        <h1 className="text-2xl font-extrabold tracking-tight">Terjadi Kesalahan</h1>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Aplikasi mengalami error yang tidak terduga. Silakan coba lagi.
        </p>
        {error.digest && (
          <p className="text-xs text-muted-foreground/60 font-mono">
            Error ID: {error.digest}
          </p>
        )}
      </div>
      <Button
        onClick={reset}
        className="bg-gradient-violet hover:opacity-90 text-white font-bold px-6 py-2 rounded-xl"
      >
        Coba Lagi
      </Button>
    </div>
  );
}
