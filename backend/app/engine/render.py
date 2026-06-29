"""Smart crop renderer — two-pass interpolation, cut detection, motion-aware face selection.

Submodules:
  - face_detection: multi-model face detector loader & detection
  - camera_segments: scene cut detection & shot type classification
  - smoothing: Kalman-filter smoothing & sample data structures
"""
import logging
import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from ..config import RENDER_CFG, STORAGE_DIR, resolve_encoder
from .face_detection import (
    SensitivityParams,
    _compute_mouth_motion,
    _detect_faces,
    _load_face_detector,
    _to_gray,
    apply_sensitivity,
)
from .camera_segments import _classify_shot, _generate_camera_segments
from .smoothing import (
    SampleFrame,
    _apply_smoothing_non_causal,
    _ease_in_out,
    _lerp,
)
from .utils import sanitize_env

log = logging.getLogger(__name__)

# Prevent console windows flashing on Windows
CREATION_FLAGS = 0
if os.name == "nt":
    CREATION_FLAGS = 0x08000000 # subprocess.CREATE_NO_WINDOW


def _read_bgr_frame(cap) -> Tuple[bool, Optional[np.ndarray]]:
    """Read a frame and guarantee it has 3 channels (BGR), converting from grayscale if necessary."""
    ret, frame = cap.read()
    if not ret or frame is None:
        return False, None
    if len(frame.shape) == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    elif len(frame.shape) == 3 and frame.shape[2] == 1:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    return True, frame


def _ratio(aspect_ratio: str) -> float:
    try:
        w, h = aspect_ratio.split(":")
        return float(w) / float(h)
    except (ValueError, ZeroDivisionError):
        return 9.0 / 16.0


def _cut_subclip(source_path: str, start: float, end: float, out_path: str,
                 encoder_args: str = "libx264 -preset fast -crf 20") -> str:
    duration = end - start
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{start:.3f}",
        "-i", source_path,
        "-t", f"{duration:.3f}",
        "-c:v", *encoder_args.split(),
        "-c:a", "aac", "-b:a", "128k",
        out_path,
    ]
    subprocess.run(cmd, check=True, creationflags=CREATION_FLAGS)
    return out_path


def _letterbox(frame: np.ndarray, crop_w: int, crop_h: int) -> np.ndarray:
    """Center the horizontal frame in a 9:16 canvas with a zoomed-in blurred background.

    The background is the original frame scaled to FILL the crop dimensions
    (zoomed/cropped to cover the entire 9:16 area), then heavily blurred.
    """
    h, w = frame.shape[:2]

    # Foreground: scale frame to fit inside crop (preserve aspect ratio)
    scale = min(crop_w / w, crop_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    # Background: scale frame to FILL crop (zoomed, may crop edges)
    bg_scale = max(crop_w / w, crop_h / h)
    bg_w, bg_h = int(w * bg_scale), int(h * bg_scale)
    # Downscale first for fast blur, then upscale
    small_bg = cv2.resize(frame, (crop_w // 4, crop_h // 4), interpolation=cv2.INTER_AREA)
    small_bg = cv2.GaussianBlur(small_bg, (51, 51), 0)
    bg = cv2.resize(small_bg, (crop_w, crop_h), interpolation=cv2.INTER_LINEAR)

    # Center foreground on blurred background
    x_off = (crop_w - new_w) // 2
    y_off = (crop_h - new_h) // 2
    bg[y_off:y_off + new_h, x_off:x_off + new_w] = resized
    return bg


# ── Pass 1: Analysis at SAMPLE_FPS ───────────────────────────────

def _analyze_video(
    in_path: str,
    detector,
    crop_w: int,
    crop_h: int,
    src_w: int,
    src_h: int,
    camera_segments: List[Dict[str, Any]],
    clip_start_offset: float = 0.0,
    face_detector: str = "yunet",
    sp: Optional[SensitivityParams] = None,
    template: str = "podcast",
) -> List[SampleFrame]:
    """Pass 1: Analyze video using ground-truth camera segments to guide crop decisions.
    Applies strict behavior per segment type (master vs individual closeups) to eliminate noise.
    """
    if sp is None:
        sp = apply_sensitivity(50, face_detector)

    cap = cv2.VideoCapture(in_path)
    if not cap.isOpened():
        return []

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        if template == "gaming":
            sample_interval = max(1, int(fps * 2.0))  # 1 deteksi setiap 2 detik (0.5 FPS)
        else:
            sample_interval = max(1, int(fps / 5.0))  # 5 FPS deteksi (untuk podcast)

        # Collect all segment start frames to ensure they are sampled exactly.
        # This prevents lag/jitter at camera cuts because the first frame of a segment
        # will be evaluated at the exact frame where the camera transition occurs.
        cut_frame_indices = set()
        if camera_segments:
            for seg in camera_segments:
                start_t = seg.get("start", 0.0)
                if start_t > 0:
                    cut_frame_indices.add(int(round(start_t * fps)))

        frame_idx = 0
        sampled_frames = []

        # Tiled Corner Inference params for gaming template
        locked_corner = None
        corner_defs = [
            ("top_right", 0.65, 1.0, 0.0, 0.45),
            ("top_left", 0.0, 0.35, 0.0, 0.45),
            ("bottom_right", 0.65, 1.0, 0.55, 1.0),
            ("bottom_left", 0.0, 0.35, 0.55, 1.0)
        ]
        corner_hits = {"top_right": 0, "top_left": 0, "bottom_right": 0, "bottom_left": 0}
        gaming_samples_scanned = 0

        while True:
            ret, frame = _read_bgr_frame(cap)
            if not ret or frame is None:
                break

            if frame_idx % sample_interval == 0 or frame_idx in cut_frame_indices:
                t = frame_idx / fps
                
                if template == "gaming":
                    faces = []
                    # Scan all 4 corners to detect faces
                    for corner_name, x_s_pct, x_e_pct, y_s_pct, y_e_pct in corner_defs:
                        x1 = int(src_w * x_s_pct)
                        x2 = int(src_w * x_e_pct)
                        y1 = int(src_h * y_s_pct)
                        y2 = int(src_h * y_e_pct)
                        corner_crop = frame[y1:y2, x1:x2]
                        if corner_crop.size > 0:
                            # Lower confidence threshold (e.g. 0.35) for better sensitivity in small webcam windows
                            conf_thresh = min(0.35, sp.confidence_threshold)
                            corner_faces = _detect_faces(detector, face_detector, corner_crop, conf_thresh)
                            if corner_faces:
                                corner_hits[corner_name] += len(corner_faces)
                                for face in corner_faces:
                                    cx_local, cy_local, conf, _, bbox_local = face
                                    cx_global = cx_local + x1
                                    cy_global = cy_local + y1
                                    bx1_l, by1_l, bx2_l, by2_l = bbox_local
                                    bbox_global = (bx1_l + x1, by1_l + y1, bx2_l + x1, by2_l + y1)
                                    face_h_ratio_global = (by2_l - by1_l) / src_h
                                    faces.append((cx_global, cy_global, conf, face_h_ratio_global, bbox_global))
                else:
                    faces = _detect_faces(detector, face_detector, frame, sp.confidence_threshold)

                sampled_frames.append({
                    "frame_idx": frame_idx,
                    "time": t,
                    "faces": faces
                })
            frame_idx += 1
    finally:
        cap.release()

    if not sampled_frames:
        return []

    # Map segments to absolute timeline of the subclip
    if not camera_segments:
        total_duration = frame_idx / fps
        camera_segments = [{"start": 0.0, "end": total_duration, "type": "master"}]

    if template == "gaming":
        # Find the best corner with the highest detections across the whole video
        best_corner = max(corner_hits, key=corner_hits.get)
        if corner_hits[best_corner] >= 1: # even 1 detection is enough to confirm
            locked_corner = best_corner
        else:
            locked_corner = "top_right"
        log.info(f"[GAMING DETECT] Locked webcam corner to: {locked_corner} with total {corner_hits[locked_corner]} hits across the video")
        
        # Filter all sampled frames' faces to only include faces within the locked corner
        x_s_pct, x_e_pct, y_s_pct, y_e_pct = next(
            (x_s, x_e, y_s, y_e) for name, x_s, x_e, y_s, y_e in corner_defs if name == locked_corner
        )
        x1 = int(src_w * x_s_pct)
        x2 = int(src_w * x_e_pct)
        y1 = int(src_h * y_s_pct)
        y2 = int(src_h * y_e_pct)
        
        for f in sampled_frames:
            f["faces"] = [
                face for face in f["faces"]
                if x1 <= face[0] <= x2 and y1 <= face[1] <= y2
            ]

    # Classify each segment based on face detection density (to identify group shots)
    for seg in camera_segments:
        seg_start = seg.get("start", 0.0)
        seg_end = seg.get("end", 999999.0)

        seg_frames = [f for f in sampled_frames if seg_start <= f["time"] + clip_start_offset <= seg_end]
        if not seg_frames:
            seg["is_group"] = (seg.get("type") == "master")
            continue

        # Count frames with 2+ faces
        frames_with_multiple = sum(1 for f in seg_frames if len(f["faces"]) >= 2)
        pct_multiple = frames_with_multiple / len(seg_frames)

        # If at least 15% of frames have 2+ faces (and at least 1 frame), it's a group shot
        if template == "gaming":
            seg["is_group"] = False
        elif (pct_multiple >= 0.15 and frames_with_multiple >= 1) or seg.get("type") == "master":
            seg["is_group"] = True
        else:
            seg["is_group"] = False

    samples = []

    # Process each camera segment for tracking and smoothing
    for seg_idx, seg in enumerate(camera_segments):
        seg_start = seg.get("start", 0.0)
        seg_end = seg.get("end", 999999.0)

        seg_frames = [f for f in sampled_frames if seg_start <= f["time"] + clip_start_offset <= seg_end]
        if not seg_frames:
            continue

        is_group = seg["is_group"]
        is_first_frame_of_seg = True
        curr_cam_cx = src_w // 2

        # Cache for face tracking continuity inside this segment
        last_face_cx = None
        last_face_cy = None
        last_face_ratio = 0.22

        for f in seg_frames:
            t = f["time"]
            f_idx = f["frame_idx"]
            faces = f["faces"]

            if is_group:
                # Group/master shot: horizontal + blur (wide_cut)
                target_cx = src_w // 2
                target_cy = src_h // 2
                face_ratio = 0.0
                shot_type = "wide_cut"
            else:
                # Single person shot: track face smoothly
                if len(faces) > 0:
                    if last_face_cx is not None:
                        # Select face closest to last tracked face to prevent switching targets
                        best_face = min(faces, key=lambda face: np.hypot(face[0] - last_face_cx, face[1] - last_face_cy))
                    else:
                        best_face = max(faces, key=lambda face: face[3]) # by face_h

                    face_cx, face_cy, conf, face_ratio, bbox = best_face
                    last_face_cx = face_cx
                    last_face_cy = face_cy
                    last_face_ratio = face_ratio
                else:
                    if last_face_cx is not None:
                        face_cx = last_face_cx
                        face_cy = last_face_cy
                        face_ratio = last_face_ratio
                    else:
                        face_cx = int(seg.get("avg_cx", src_w // 2))
                        face_cy = src_h // 2
                        face_ratio = 0.0 if template == "gaming" else 0.22

                # Apply Deadzone + EMA smoothing (No Kalman drift)
                if template == "gaming":
                    target_cx = face_cx
                    target_cy = face_cy
                    shot_type = "closeup"
                else:
                    if is_first_frame_of_seg:
                        curr_cam_cx = face_cx
                        is_first_frame_of_seg = False
                        target_cx = face_cx
                    else:
                        deadzone = int(crop_w * 0.08) # 8% deadzone
                        diff_x = face_cx - curr_cam_cx

                        if abs(diff_x) < deadzone:
                            target_cx = curr_cam_cx # Stay still
                        else:
                            target_cx = face_cx # Move target

                        # Smooth follow pan using EMA (alpha = 0.10)
                        curr_cam_cx = int(0.10 * target_cx + 0.90 * curr_cam_cx)

                    # Keep crop box within video boundaries
                    curr_cam_cx = max(crop_w // 2, min(src_w - crop_w // 2, curr_cam_cx))
                    target_cx = curr_cam_cx
                    target_cy = src_h // 2  # Keep vertical center stable
                    shot_type = _classify_shot(face_ratio)

                    # Force crop instead of letterbox for single person shots
                    if shot_type == "wide_cut":
                        shot_type = "closeup"

            samples.append(SampleFrame(
                time=t,
                frame_idx=f_idx,
                raw_cx=target_cx,
                raw_cy=target_cy,
                face_ratio=face_ratio,
                shot_type=shot_type,
                is_cut=(f_idx == seg_frames[0]["frame_idx"] and seg_idx > 0),
                num_faces=len(faces),
                is_group_reaction=is_group,
            ))

    return samples


# ── Pass 2: Render at full framerate with interpolation ──────────

def _render_frames(in_path: str, out_path: str, samples: List[SampleFrame],
                   smoothed: List[Tuple[int, int, float, str, bool]],
                   crop_w: int, crop_h: int, template: str = "podcast") -> str:
    """Pass 2: Render video with interpolated crop positions."""
    silent_path = out_path + ".silent.mp4"

    if not samples:
        log.warning("Samples kosong, langsung mengembalikan video fallback.")
        import shutil
        try:
            shutil.copy2(in_path, silent_path)
            return silent_path
        except Exception as e:
            log.error("Failed to copy fallback video: %s", e)
            return in_path

    cap = cv2.VideoCapture(in_path)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1

        # Precompute stable webcam position for gaming template using density clustering
        webcam_cx, webcam_cy = src_w // 2, src_h // 2
        webcam_face_ratio = 0.15  # Fallback jika wajah tidak terdeteksi (15% tinggi layar)
        if template == "gaming" and samples:
            valid_faces = [s for s in samples if s.face_ratio > 0.0]
            if valid_faces:
                # Find the coordinate cluster with the highest density (most detections within radius R)
                # to isolate the fixed webcam area from dynamic gameplay faces
                radius = int(src_w * 0.15)
                best_center_x, best_center_y = valid_faces[0].raw_cx, valid_faces[0].raw_cy
                max_cluster_size = 0

                # Vectorized density clustering — O(N) vs O(N²) nested loop
                face_cx = np.array([s.raw_cx for s in valid_faces])
                face_cy = np.array([s.raw_cy for s in valid_faces])
                for i, candidate in enumerate(valid_faces):
                    cx, cy = candidate.raw_cx, candidate.raw_cy
                    cluster_size = int(np.sum(
                        (np.abs(face_cx - cx) <= radius) & (np.abs(face_cy - cy) <= radius)
                    ))
                    if cluster_size > max_cluster_size:
                        max_cluster_size = cluster_size
                        best_center_x, best_center_y = cx, cy

                # Average coordinates only for faces within the chosen webcam cluster
                cluster_faces = [
                    s for s in valid_faces
                    if abs(s.raw_cx - best_center_x) <= radius and abs(s.raw_cy - best_center_y) <= radius
                ]
                if cluster_faces:
                    webcam_cx = int(sum(s.raw_cx for s in cluster_faces) / len(cluster_faces))
                    webcam_cy = int(sum(s.raw_cy for s in cluster_faces) / len(cluster_faces))
                    webcam_face_ratio = sum(s.face_ratio for s in cluster_faces) / len(cluster_faces)
                else:
                    webcam_cx, webcam_cy = best_center_x, best_center_y
                    webcam_face_ratio = sum(s.face_ratio for s in valid_faces) / len(valid_faces)
            else:
                webcam_cx = int(src_w * 0.85)
                webcam_cy = int(src_h * 0.20)

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(silent_path, cv2.CAP_FFMPEG, fourcc, fps, (crop_w, crop_h))
        if not writer.isOpened():
            raise RuntimeError(f"Could not open VideoWriter for path: {silent_path}")
        try:
            n_samples = len(samples)
            frame_idx = 0

            # Amortized O(1) bracket pointer
            sample_pointer = 0

            # Pre-allocate gaming padding arrays (constant dimensions, avoids per-frame alloc)
            _gaming_top_pad = np.zeros((int(crop_h * 0.08) // 2 * 2, crop_w, 3), dtype=np.uint8) if template == "gaming" else None
            _gaming_bottom_pad = np.zeros((int(crop_h * 0.12) // 2 * 2, crop_w, 3), dtype=np.uint8) if template == "gaming" else None

            while True:
                ret, frame = _read_bgr_frame(cap)
                if not ret or frame is None:
                    break

                t = frame_idx / fps

                while sample_pointer < n_samples - 1 and samples[sample_pointer + 1].time <= t:
                    sample_pointer += 1

                if t >= samples[-1].time:
                    prev_idx = next_idx = n_samples - 1
                else:
                    prev_idx = sample_pointer
                    next_idx = min(sample_pointer + 1, n_samples - 1)

                prev_s = samples[prev_idx]
                next_s = samples[next_idx]
                prev_smooth = smoothed[prev_idx]
                next_smooth = smoothed[next_idx]

                # Interpolation
                if prev_idx == next_idx:
                    cx, cy, face_ratio, shot_type = prev_smooth[0], prev_smooth[1], prev_smooth[2], prev_smooth[3]
                elif next_smooth[4]:  # next sample is a cut
                    if t < next_s.time:
                        cx, cy, face_ratio, shot_type = prev_smooth[0], prev_smooth[1], prev_smooth[2], prev_smooth[3]
                    else:
                        cx, cy, face_ratio, shot_type = next_smooth[0], next_smooth[1], next_smooth[2], next_smooth[3]
                else:
                    dt = next_s.time - prev_s.time
                    alpha = (t - prev_s.time) / dt if dt > 0 else 0.0

                    cx = int(_lerp(prev_smooth[0], next_smooth[0], alpha))
                    cy = int(_lerp(prev_smooth[1], next_smooth[1], alpha))
                    face_ratio = _lerp(prev_smooth[2], next_smooth[2], alpha)
                    shot_type = prev_smooth[3] if alpha < 0.5 else next_smooth[3]

                # Render
                if template == "gaming":
                    # 1. Definisikan Margin Atas (8%) & Bawah (12%) - Pastikan genap
                    top_margin = int(crop_h * 0.08)
                    top_margin = max(0, top_margin - (top_margin % 2))
                    bottom_margin = int(crop_h * 0.12)
                    bottom_margin = max(0, bottom_margin - (bottom_margin % 2))
                    content_h = crop_h - top_margin - bottom_margin

                    # 2. Definisikan tinggi webcam (35% dari sisa tinggi) & gameplay (65%) - Pastikan genap
                    webcam_h_out = int(content_h * 0.35)
                    webcam_h_out = max(2, webcam_h_out - (webcam_h_out % 2))
                    gameplay_h_out = content_h - webcam_h_out

                    # 3. Proses Crop & Resize Webcam secara dinamis berbasis ukuran wajah
                    target_ar_webcam = crop_w / webcam_h_out
                    
                    avg_face_h = webcam_face_ratio * src_h
                    webcam_crop_h = int(avg_face_h * 2.5) # Zoom lebih dekat (pengali 2.5)
                    
                    # Batasi ukuran crop webcam agar tidak terlalu ekstrem
                    min_webcam_crop_h = int(src_h * 0.20)
                    max_webcam_crop_h = int(src_h * 0.45)
                    webcam_crop_h = max(min_webcam_crop_h, min(max_webcam_crop_h, webcam_crop_h))
                    
                    webcam_crop_w = int(webcam_crop_h * target_ar_webcam)
                    if webcam_crop_w > src_w:
                        webcam_crop_w = src_w
                        webcam_crop_h = int(webcam_crop_w / target_ar_webcam)

                    wx0 = max(0, min(src_w - webcam_crop_w, webcam_cx - webcam_crop_w // 2))
                    wy0 = max(0, min(src_h - webcam_crop_h, webcam_cy - webcam_crop_h // 2))
                    webcam_cropped = frame[wy0:wy0 + webcam_crop_h, wx0:wx0 + webcam_crop_w]

                    if webcam_cropped is None or webcam_cropped.size == 0:
                        webcam_resized = cv2.resize(frame, (crop_w, webcam_h_out), interpolation=cv2.INTER_LANCZOS4)
                    else:
                        webcam_resized = cv2.resize(webcam_cropped, (crop_w, webcam_h_out), interpolation=cv2.INTER_LANCZOS4)

                    # 4. Proses Crop & Resize Gameplay
                    target_ar_gameplay = crop_w / gameplay_h_out
                    gameplay_crop_h = src_h
                    gameplay_crop_w = int(gameplay_crop_h * target_ar_gameplay)
                    if gameplay_crop_w > src_w:
                        gameplay_crop_w = src_w
                        gameplay_crop_h = int(gameplay_crop_w / target_ar_gameplay)

                    gx0 = (src_w - gameplay_crop_w) // 2
                    gy0 = (src_h - gameplay_crop_h) // 2
                    gameplay_cropped = frame[gy0:gy0 + gameplay_crop_h, gx0:gx0 + gameplay_crop_w]

                    if gameplay_cropped is None or gameplay_cropped.size == 0:
                        gameplay_resized = cv2.resize(frame, (crop_w, gameplay_h_out), interpolation=cv2.INTER_LANCZOS4)
                    else:
                        gameplay_resized = cv2.resize(gameplay_cropped, (crop_w, gameplay_h_out), interpolation=cv2.INTER_LANCZOS4)

                    # 5. Gabungkan dengan margin hitam atas/bawah (pre-allocated sebelum loop)
                    cropped = np.vstack([_gaming_top_pad, webcam_resized, gameplay_resized, _gaming_bottom_pad])
                elif shot_type == "wide_cut":
                    cropped = _letterbox(frame, crop_w, crop_h)
                else:
                    w_z = crop_w
                    h_z = crop_h

                    x0 = max(0, min(src_w - w_z, cx - w_z // 2))
                    y0 = max(0, min(src_h - h_z, cy - h_z // 2))
                    cropped = frame[y0:y0 + h_z, x0:x0 + w_z]

                    if cropped is None or cropped.size == 0 or cropped.shape[0] == 0 or cropped.shape[1] == 0:
                        log.warning("Cropped frame kosong pada frame_idx %d. Fallback ke letterbox.", frame_idx)
                        cropped = _letterbox(frame, crop_w, crop_h)
                    else:
                        if w_z != crop_w or h_z != crop_h or cropped.shape[1] != crop_w or cropped.shape[0] != crop_h:
                            cropped = cv2.resize(cropped, (crop_w, crop_h), interpolation=cv2.INTER_LANCZOS4)

                if cropped.shape[1] != crop_w or cropped.shape[0] != crop_h:
                    cropped = cv2.resize(cropped, (crop_w, crop_h), interpolation=cv2.INTER_LANCZOS4)

                cropped = np.ascontiguousarray(cropped)

                try:
                    writer.write(cropped)
                except Exception as e:
                    log.error(
                        "OpenCV write crash pada frame_idx=%d. "
                        "cropped.shape=%s, cropped.dtype=%s, crop_w=%d, crop_h=%d, error=%s",
                        frame_idx, cropped.shape if cropped is not None else None,
                        cropped.dtype if cropped is not None else None,
                        crop_w, crop_h, e
                    )
                    raise e
                frame_idx += 1
        finally:
            writer.release()
    finally:
        cap.release()

    return silent_path


# ── Main Entry Point ─────────────────────────────────────────────

def _render_master_letterbox(in_path: str, out_path: str, aspect_ratio: str) -> str:
    """Render full video frame letterboxed (scaled and blurred background) without any crop/pan."""
    target_ratio = _ratio(aspect_ratio)
    cap = cv2.VideoCapture(in_path)
    if not cap.isOpened():
        raise RuntimeError(f"could not open {in_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    if target_ratio < src_w / src_h:
        crop_h = src_h
        crop_w = int(crop_h * target_ratio)
    else:
        crop_w = src_w
        crop_h = int(crop_w / target_ratio)
    crop_w = max(2, crop_w - (crop_w % 2))
    crop_h = max(2, crop_h - (crop_h % 2))

    silent_path = out_path + ".silent.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(silent_path, cv2.CAP_FFMPEG, fourcc, fps, (crop_w, crop_h))
    if not writer.isOpened():
        raise RuntimeError(f"Could not open VideoWriter for path: {silent_path}")

    while True:
        ret, frame = _read_bgr_frame(cap)
        if not ret or frame is None:
            break
        cropped = _letterbox(frame, crop_w, crop_h)
        writer.write(cropped)

    cap.release()
    writer.release()

    return silent_path


def _ffmpeg_escape_path(path: str) -> str:
    """Escape a file path for use inside an ffmpeg filter string."""
    return path.replace("\\", "/").replace(":", "\\:").replace("'", r"\'").replace(",", "\\,")


def _mux_with_subtitles(
    silent_path: str,
    audio_source: str,
    out_path: str,
    subtitle_path: Optional[str] = None,
    fonts_dir: Optional[str] = None,
    encoder_args: str = "libx264 -preset fast -crf 20",
) -> None:
    """Single ffmpeg call: re-encode video with optional ASS burn-in + audio mux."""
    vf_parts: List[str] = []
    if subtitle_path:
        escaped = _ffmpeg_escape_path(os.path.abspath(subtitle_path))
        ass_filter = f"ass='{escaped}'"
        if fonts_dir:
            ass_filter += f":fontsdir='{_ffmpeg_escape_path(os.path.abspath(fonts_dir))}'"
        vf_parts.append(ass_filter)

    cmd = ["ffmpeg", "-y", "-loglevel", "error"]

    if vf_parts:
        cmd += ["-i", silent_path]
        cmd += ["-i", audio_source]
        cmd += ["-vf", ",".join(vf_parts)]
        cmd += ["-c:v", *encoder_args.split(), "-c:a", "aac", "-b:a", "128k",
                "-map", "0:v:0", "-map", "1:a:0?",
                "-shortest", out_path]
    else:
        cmd += ["-i", silent_path]
        cmd += ["-i", audio_source]
        cmd += ["-c:v", *encoder_args.split(), "-c:a", "aac", "-b:a", "128k",
                "-map", "0:v:0", "-map", "1:a:0?",
                "-shortest", out_path]

    subprocess.run(cmd, check=True, creationflags=CREATION_FLAGS)


def _reframe_vertical(
    in_path: str,
    out_path: str,
    aspect_ratio: str,
    is_master: bool = False,
    subtitle_path: Optional[str] = None,
    fonts_dir: Optional[str] = None,
    face_detector: str = "yunet",
    encoder_args: str = "libx264 -preset fast -crf 20",
    sp: Optional[SensitivityParams] = None,
    template: str = "podcast",
) -> str:
    """Two-pass smart crop using ground-truth camera segments and non-causal smoothing."""
    if is_master:
        silent_path = _render_master_letterbox(in_path, out_path, aspect_ratio)
    else:
        target_ratio = _ratio(aspect_ratio)

        detector = _load_face_detector(face_detector)
        try:
            cap = cv2.VideoCapture(in_path)
            if not cap.isOpened():
                raise RuntimeError(f"could not open {in_path}")

            src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()

            if target_ratio < src_w / src_h:
                crop_h = src_h
                crop_w = int(crop_h * target_ratio)
            else:
                crop_w = src_w
                crop_h = int(crop_w / target_ratio)
            crop_w = max(2, crop_w - (crop_w % 2))
            crop_h = max(2, crop_h - (crop_h % 2))

            camera_segments = _generate_camera_segments(in_path, detector, face_detector)

            samples = _analyze_video(in_path, detector, crop_w, crop_h, src_w, src_h, camera_segments, clip_start_offset=0.0, face_detector=face_detector, sp=sp, template=template)

            if not samples:
                log.warning("Samples kosong setelah _analyze_video. Fallback ke master letterbox.")
                silent_path = _render_master_letterbox(in_path, out_path, aspect_ratio)
            else:
                smoothed = _apply_smoothing_non_causal(samples, src_w, src_h)
                silent_path = _render_frames(in_path, out_path, samples, smoothed, crop_w, crop_h, template=template)
        finally:
            if hasattr(detector, "close"):
                try:
                    detector.close()
                except Exception:
                    pass

    try:
        _mux_with_subtitles(silent_path, in_path, out_path, subtitle_path, fonts_dir, encoder_args)
    finally:
        if os.path.exists(silent_path):
            try:
                os.remove(silent_path)
            except Exception as e:
                log.warning("Gagal menghapus silent video temporary file %s: %s", silent_path, e)
    return out_path


def _update_render_progress(task_id: str, current: int, total: int, msg: str, stage: str = "RENDER"):
    try:
        import asyncio
        from ..state import store
        pct = 62.0 + (float(current) / float(total)) * 28.0

        loop = getattr(store, "loop", None)

        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(
                store.set_progress(task_id, pct, stage, msg), loop
            )
        else:
            log.info("[render progress] Task %s: %.1f%% - %s", task_id, pct, msg)
            try:
                if not getattr(store, "_use_redis", False) and task_id in store._mem_tasks:
                    r = store._mem_tasks[task_id]
                    r.progress = float(pct)
                    r.stage = stage
                    r.message = msg
                    r.status = "processing"
            except Exception:
                pass
    except Exception as e:
        log.error("Failed to update render progress: %s", e)


def render_clips(
    source_path: str,
    highlights: List[Dict],
    task_id: str,
    aspect_ratio: str = "9:16",
    subtitle_path: Optional[str] = None,
    fonts_dir: Optional[str] = None,
    subtitle_style: Optional[str] = None,
    face_detector: str = "yunet",
    subtitle_font: Optional[str] = None,
    subtitle_color_primary: Optional[str] = None,
    subtitle_color_highlight: Optional[str] = None,
    encoder: str = "auto",
    sensitivity: int = 50,
    template: str = "podcast",
) -> List[Dict]:
    sanitize_env()
    sp = apply_sensitivity(sensitivity, face_detector)
    encoder_args = resolve_encoder(encoder)
    clips_dir = str(STORAGE_DIR / task_id / "clips")
    os.makedirs(clips_dir, exist_ok=True)
    results = []

    import json
    transcript_segments = []
    json_path = STORAGE_DIR / task_id / "transcript.json"
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                transcript_segments = json.load(f).get("segments", [])
        except Exception as e:
            log.error("Failed to load transcript.json for clip rendering: %s", e)

    for i, h in enumerate(highlights, 1):
        _update_render_progress(task_id, i - 1, len(highlights), f"Smart crop klip {i}/{len(highlights)}…", "SMART_CROP")
        out_path = os.path.join(clips_dir, f"short_{i:02d}.mp4")
        cut_path = out_path + ".cut.mp4"
        clip_ass_path = os.path.join(clips_dir, f"short_{i:02d}.ass")

        try:
            h_start = float(h["start_time"])
            h_end = float(h["end_time"])

            clip_segments = []
            for seg in transcript_segments:
                s_start = float(seg.get("start", seg.get("start_time", 0.0)))
                s_end = float(seg.get("end", seg.get("end_time", 0.0)))

                if s_end > h_start and s_start < h_end:
                    clamped_start = max(s_start, h_start)
                    clamped_end = min(s_end, h_end)

                    seg_copy = dict(seg)
                    seg_copy["start"] = clamped_start - h_start
                    seg_copy["end"] = clamped_end - h_start
                    seg_copy["start_time"] = clamped_start - h_start
                    seg_copy["end_time"] = clamped_end - h_start
                    clip_segments.append(seg_copy)

            resolved_subtitle_path = subtitle_path
            if clip_segments and subtitle_path:
                from .subtitles import generate_ass, STYLES, DEFAULT_STYLE
                style_key = subtitle_style
                if not style_key:
                    style_key = DEFAULT_STYLE
                    if os.path.exists(subtitle_path):
                        try:
                            from ..state import store
                            task_record = getattr(store, '_mem_tasks', {}).get(task_id)
                            if task_record and hasattr(task_record, "subtitle_style"):
                                style_key = task_record.subtitle_style
                            elif task_record and isinstance(task_record, dict) and "subtitle_style" in task_record:
                                style_key = task_record["subtitle_style"]
                            elif task_record and hasattr(task_record, "to_dict"):
                                style_key = task_record.to_dict().get("subtitle_style", DEFAULT_STYLE)
                        except Exception:
                            pass

                resolved_subtitle_path = generate_ass(
                    clip_segments,
                    style_key,
                    clip_ass_path,
                    play_res_x=1080,
                    play_res_y=1920,
                    fonts_dir=fonts_dir,
                    subtitle_font=subtitle_font,
                    subtitle_color_primary=subtitle_color_primary,
                    subtitle_color_highlight=subtitle_color_highlight,
                )

            _update_render_progress(task_id, i - 1, len(highlights), f"Encoding klip {i}/{len(highlights)}…", "RENDER")
            _cut_subclip(source_path, h_start, h_end, cut_path, encoder_args)
            _reframe_vertical(
                cut_path, out_path, aspect_ratio,
                subtitle_path=resolved_subtitle_path,
                fonts_dir=fonts_dir,
                face_detector=face_detector,
                encoder_args=encoder_args,
                sp=sp,
                template=template,
            )
            results.append({**h, "clip_url": f"/clips/{task_id}/short_{i:02d}.mp4"})
        except Exception as e:
            # Raise exception immediately to bubble up render failure and prevent fake 'completed' status
            logger.error(f"Render failed for clip {i}: {e}")
            raise RuntimeError(f"Klip {i} ({h.get('title', 'clip')}) gagal dirender: {e}") from e
        finally:
            if os.path.exists(cut_path):
                os.remove(cut_path)
            if clip_ass_path and os.path.exists(clip_ass_path):
                try:
                    os.remove(clip_ass_path)
                except Exception:
                    pass
    _update_render_progress(task_id, len(highlights), len(highlights), "Semua klip selesai dirender")
    return results
