"use client";

import { useRef, useState } from "react";
import { Play, Pause, Volume2, VolumeX } from "lucide-react";

interface VerticalPlayerProps {
  src: string;
  poster?: string;
  className?: string;
}

export function VerticalPlayer({ src, poster, className = "" }: VerticalPlayerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(true);
  const [showOverlay, setShowOverlay] = useState(true);

  const togglePlay = () => {
    if (!videoRef.current) return;
    if (videoRef.current.paused) {
      videoRef.current.play();
      setPlaying(true);
    } else {
      videoRef.current.pause();
      setPlaying(false);
    }
  };

  const toggleMute = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!videoRef.current) return;
    videoRef.current.muted = !videoRef.current.muted;
    setMuted(videoRef.current.muted);
  };

  const handleMouseEnter = () => setShowOverlay(true);
  const handleMouseLeave = () => { if (playing) setShowOverlay(false); };

  return (
    <div
      className={`relative bg-black overflow-hidden group cursor-pointer ${className}`}
      style={{ aspectRatio: "9 / 16" }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={togglePlay}
    >
      <video
        ref={videoRef}
        src={src}
        poster={poster}
        playsInline
        preload="metadata"
        muted={muted}
        className="absolute inset-0 w-full h-full object-contain"
        onEnded={() => setPlaying(false)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
      />

      {/* Gradient overlay at bottom */}
      <div className={`absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-black/60 to-transparent transition-opacity duration-300 ${showOverlay || !playing ? "opacity-100" : "opacity-0"}`} />

      {/* Center play/pause button */}
      <div className={`absolute inset-0 flex items-center justify-center transition-all duration-300 ${showOverlay || !playing ? "opacity-100" : "opacity-0"}`}>
        <div className={`w-14 h-14 rounded-full bg-white/20 backdrop-blur-md flex items-center justify-center transition-all duration-300 ${!playing && "scale-110 bg-white/30"}`}>
          {playing ? (
            <Pause className="w-6 h-6 text-white fill-white" />
          ) : (
            <Play className="w-6 h-6 text-white fill-white ml-0.5" />
          )}
        </div>
      </div>

      {/* Mute button */}
      <button
        onClick={toggleMute}
        className={`absolute top-3 right-3 w-8 h-8 rounded-full bg-black/40 backdrop-blur-sm flex items-center justify-center transition-all duration-200 hover:bg-black/60 ${showOverlay || !playing ? "opacity-100" : "opacity-0"}`}
      >
        {muted ? (
          <VolumeX className="w-4 h-4 text-white" />
        ) : (
          <Volume2 className="w-4 h-4 text-white" />
        )}
      </button>
    </div>
  );
}

export default VerticalPlayer;
