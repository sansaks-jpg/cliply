"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Play, Pause, Volume2, VolumeX } from "lucide-react";

interface VerticalPlayerProps {
  src: string;
  poster?: string;
  className?: string;
}

function formatTime(s: number): string {
  if (!isFinite(s) || s < 0) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

export function VerticalPlayer({ src, poster, className = "" }: VerticalPlayerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const seekRef = useRef<HTMLDivElement | null>(null);

  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(true);
  const [showControls, setShowControls] = useState(true);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [buffered, setBuffered] = useState(0);

  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleHide = useCallback(() => {
    if (hideTimer.current) clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => {
      if (videoRef.current && !videoRef.current.paused) {
        setShowControls(false);
      }
    }, 2500);
  }, []);

  const revealControls = useCallback(() => {
    setShowControls(true);
    scheduleHide();
  }, [scheduleHide]);

  const togglePlay = (e?: React.MouseEvent) => {
    // Don't toggle if click is on seekbar area
    if (e && (e.target as HTMLElement).closest("[data-seekbar]")) return;
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) {
      v.play();
    } else {
      v.pause();
      setShowControls(true);
      if (hideTimer.current) clearTimeout(hideTimer.current);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      togglePlay();
    }
  };

  const toggleMute = (e: React.MouseEvent) => {
    e.stopPropagation();
    const v = videoRef.current;
    if (!v) return;
    v.muted = !v.muted;
    setMuted(v.muted);
  };

  // Seek helpers
  const getSeekPct = useCallback((clientX: number): number => {
    const bar = seekRef.current;
    if (!bar) return 0;
    const rect = bar.getBoundingClientRect();
    return Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
  }, []);

  const seekTo = useCallback((pct: number) => {
    const v = videoRef.current;
    if (!v || !isFinite(v.duration)) return;
    v.currentTime = pct * v.duration;
    setCurrentTime(v.currentTime);
  }, []);

  // Mouse seek on bar
  const handleSeekMouseDown = (e: React.MouseEvent) => {
    e.stopPropagation();
    setDragging(true);
    seekTo(getSeekPct(e.clientX));
  };

  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: MouseEvent) => seekTo(getSeekPct(e.clientX));
    const onUp = () => setDragging(false);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [dragging, seekTo, getSeekPct]);

  // Touch seek
  const handleSeekTouchStart = (e: React.TouchEvent) => {
    e.stopPropagation();
    setDragging(true);
    seekTo(getSeekPct(e.touches[0].clientX));
  };

  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: TouchEvent) => {
      if (e.touches[0]) seekTo(getSeekPct(e.touches[0].clientX));
    };
    const onEnd = () => setDragging(false);
    window.addEventListener("touchmove", onMove, { passive: true });
    window.addEventListener("touchend", onEnd);
    return () => {
      window.removeEventListener("touchmove", onMove);
      window.removeEventListener("touchend", onEnd);
    };
  }, [dragging, seekTo, getSeekPct]);

  // Video event handlers
  const handleTimeUpdate = () => {
    const v = videoRef.current;
    if (!v || dragging) return;
    setCurrentTime(v.currentTime);
    // Update buffered
    if (v.buffered.length > 0) {
      setBuffered(v.buffered.end(v.buffered.length - 1) / v.duration);
    }
  };

  const handleLoadedMetadata = () => {
    const v = videoRef.current;
    if (!v) return;
    setDuration(v.duration);
  };

  const pct = duration > 0 ? currentTime / duration : 0;
  const isAbsolute = className.includes("absolute");

  return (
    <div
      className={`${isAbsolute ? "" : "relative"} bg-black overflow-hidden select-none ${className}`}
      style={isAbsolute ? {} : { aspectRatio: "9 / 16" }}
      onMouseMove={revealControls}
      onTouchStart={revealControls}
    >
      {/* Play/Pause overlay button for accessibility (avoids nesting interactive elements) */}
      <button
        type="button"
        className="absolute inset-0 w-full h-full cursor-pointer focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-inset focus-visible:ring-[var(--accent-violet)] z-5"
        aria-label={playing ? "Jeda video" : "Putar video"}
        onClick={togglePlay}
        onKeyDown={handleKeyDown}
      />

      <video
        ref={videoRef}
        src={src}
        poster={poster}
        playsInline
        preload="metadata"
        muted={muted}
        className="absolute inset-0 w-full h-full object-contain pointer-events-none"
        onEnded={() => { setPlaying(false); setShowControls(true); }}
        onPlay={() => { setPlaying(true); scheduleHide(); }}
        onPause={() => setPlaying(false)}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onProgress={handleTimeUpdate}
      />

      {/* Bottom gradient */}
      <div
        className={`absolute z-10 inset-x-0 bottom-0 h-28 bg-gradient-to-t from-black/80 via-black/30 to-transparent transition-opacity duration-300 pointer-events-none ${showControls || !playing ? "opacity-100" : "opacity-0"}`}
      />

      {/* Center play/pause */}
      <div
        className={`absolute z-10 inset-0 flex items-center justify-center transition-all duration-200 pointer-events-none ${showControls || !playing ? "opacity-100" : "opacity-0"}`}
      >
        <div
          className={`w-12 h-12 rounded-full bg-white/20 backdrop-blur-md border border-white/30 flex items-center justify-center transition-all duration-200 ${!playing ? "scale-110" : "scale-95 opacity-80"}`}
        >
          {playing ? (
            <Pause className="w-5 h-5 text-white fill-white" />
          ) : (
            <Play className="w-5 h-5 text-white fill-white ml-0.5" />
          )}
        </div>
      </div>

      {/* Bottom controls: time + seekbar + mute */}
      <div
        className={`absolute z-10 inset-x-0 bottom-0 px-3 pb-3 pt-2 flex flex-col gap-1.5 transition-opacity duration-300 ${showControls || !playing ? "opacity-100" : "opacity-0"}`}
        data-seekbar="true"
      >
        {/* Time display */}
        <div className="flex items-center justify-between px-0.5">
          <span className="text-[10px] font-bold text-white/80 tabular-nums leading-none">
            {formatTime(currentTime)}
          </span>
          <span className="text-[10px] font-bold text-white/50 tabular-nums leading-none">
            {formatTime(duration)}
          </span>
        </div>

        {/* Seekbar row */}
        <div className="flex items-center gap-2">
          {/* Progress bar */}
          <div
            ref={seekRef}
            data-seekbar="true"
            className="relative flex-1 h-1 rounded-full bg-white/20 cursor-pointer group/bar"
            onMouseDown={handleSeekMouseDown}
            onTouchStart={handleSeekTouchStart}
            onClick={(e) => { e.stopPropagation(); seekTo(getSeekPct(e.clientX)); }}
          >
            {/* Buffered */}
            <div
              className="absolute inset-y-0 left-0 rounded-full bg-white/25 pointer-events-none"
              style={{ width: `${buffered * 100}%` }}
            />
            {/* Played */}
            <div
              className="absolute inset-y-0 left-0 rounded-full bg-white pointer-events-none transition-none"
              style={{ width: `${pct * 100}%` }}
            />
            {/* Thumb */}
            <div
              className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white shadow-md pointer-events-none transition-transform duration-100 group-hover/bar:scale-125"
              style={{ left: `calc(${pct * 100}% - 6px)` }}
            />
          </div>

          {/* Mute button */}
          <button
            type="button"
            data-seekbar="true"
            onClick={toggleMute}
            aria-label={muted ? "Nyalakan suara" : "Matikan suara"}
            title={muted ? "Nyalakan suara" : "Matikan suara"}
            className="w-9 h-9 rounded-full bg-black/40 backdrop-blur-sm flex items-center justify-center hover:bg-black/60 transition-colors flex-shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/50"
          >
            {muted ? (
              <VolumeX className="w-3.5 h-3.5 text-white" aria-hidden="true" />
            ) : (
              <Volume2 className="w-3.5 h-3.5 text-white" aria-hidden="true" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default VerticalPlayer;
