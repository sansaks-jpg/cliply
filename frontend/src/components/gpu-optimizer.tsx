"use client";

import { useEffect } from "react";

export default function GpuOptimizer() {
  useEffect(() => {
    const handleInactive = () => {
      document.documentElement.classList.add("window-inactive");
    };
    const handleActive = () => {
      document.documentElement.classList.remove("window-inactive");
    };

    const handleVisibility = () => {
      if (document.hidden) {
        handleInactive();
      } else {
        handleActive();
      }
    };

    // Pasang listeners untuk mendeteksi minimize dan perpindahan fokus jendela
    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("blur", handleInactive);
    window.addEventListener("focus", handleActive);

    // Pengecekan awal saat komponen dimuat
    if (document.hidden) {
      handleInactive();
    }

    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("blur", handleInactive);
      window.removeEventListener("focus", handleActive);
    };
  }, []);

  return null;
}
