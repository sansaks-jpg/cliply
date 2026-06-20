"use client";

import { useRef } from "react";

interface VerticalPlayerProps {
  src: string;
  poster?: string;
  className?: string;
}

/** 9:16 vertical video player used in clip cards.
 *
 * Uses native HTML5 video (HLS would be overkill for an MVP serving local mp4s).
 */
export function VerticalPlayer({ src, poster, className = "" }: VerticalPlayerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);

  return (
    <div
      className={`relative bg-black overflow-hidden ${className}`}
      style={{ aspectRatio: "9 / 16" }}
    >
      <video
        ref={videoRef}
        src={src}
        poster={poster}
        controls
        playsInline
        preload="metadata"
        className="absolute inset-0 w-full h-full object-contain"
      />
    </div>
  );
}

export default VerticalPlayer;
