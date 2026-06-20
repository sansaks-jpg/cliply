"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { Sun, Moon } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // Mencegah mismatch hidrasi antara server & client
  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <Button variant="ghost" size="icon" className="w-9 h-9 rounded-lg opacity-0">
        <span className="sr-only">Toggle theme</span>
      </Button>
    );
  }

  const isDark = resolvedTheme === "dark";

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="relative w-9 h-9 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors group"
      title={isDark ? "Aktifkan Mode Terang" : "Aktifkan Mode Gelap"}
    >
      <div className="relative w-5 h-5 flex items-center justify-center">
        {/* Sun Icon */}
        <Sun className={`w-5 h-5 text-amber-500 absolute transition-all duration-300 transform ${
          isDark ? "rotate-90 scale-0" : "rotate-0 scale-100"
        } group-hover:animate-[spin_4s_linear_infinite]`} />
        
        {/* Moon Icon */}
        <Moon className={`w-5 h-5 text-indigo-400 absolute transition-all duration-300 transform ${
          isDark ? "rotate-0 scale-100" : "-rotate-90 scale-0"
        } group-hover:scale-110`} />
      </div>
      <span className="sr-only">Toggle theme</span>
    </Button>
  );
}
