"""Smart crop renderer — two-pass interpolation, cut detection, motion-aware face selection.

Fix 1: Two-pass interpolation (sample 2FPS → EMA → lerp render with easing)
Fix 2: Cut detection (histogram correlation) + EMA reset on cuts
Fix 3: Smart face selection (motion energy mouth + group_reaction for 3+ faces)
"""
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from ..config import STORAGE_DIR

# ── tuning knobs ──────────────────────────────────────────────────
SAMPLE_FPS = 4
EMA_FACTOR = 0.15
CONFIDENCE_THRESHOLD = 0.5
CLOSEUP_THRESHOLD = 0.30
MEDIUM_THRESHOLD = 0.15
LETTERBOX_BLUR = 61
CUT_THRESHOLD = 0.98          # histogram correlation below this = cut
MOTION_WEIGHT = 0.6          # weight for motion_score in face priority
SIZE_WEIGHT = 0.4            # weight for size_score in face priority
GROUP_REACTION_MIN_FACES = 3 # min faces for group_reaction state
GROUP_REACTION_MOTION_THRESH = 0.3  # min motion for group reaction

# Hysteresis & Grace Period parameters
MIN_HOLD_SAMPLES = 3         # ~1.5s minimum hold for speaker focus
SWITCH_MARGIN = 0.15         # margin required to switch active speaker
MIN_SHOT_HOLD_SAMPLES = 3    # ~1.5s minimum hold for shot type classification
MAX_MISSED_SAMPLES = 4       # ~2s grace period for face tracking dropout

# model paths
_DIR = os.path.dirname(os.path.abspath(__file__))
_PROTOTXT = os.path.join(_DIR, "..", "..", "models", "deploy.prototxt")
_MODEL = os.path.join(_DIR, "..", "..", "models", "res10_300x300_ssd_iter_140000.caffemodel")


def _to_gray(frame: np.ndarray) -> np.ndarray:
    """Safely convert a BGR frame to grayscale, or return as-is if already grayscale."""
    if len(frame.shape) == 2:
        return frame
    if len(frame.shape) == 3 and frame.shape[2] == 1:
        return frame[:, :, 0]
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


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


@dataclass
class SampleFrame:
    """One analysis sample at SAMPLE_FPS."""
    time: float
    frame_idx: int
    raw_cx: int
    raw_cy: int
    face_ratio: float
    shot_type: str
    is_cut: bool = False
    num_faces: int = 0
    is_group_reaction: bool = False


def _ratio(aspect_ratio: str) -> float:
    try:
        w, h = aspect_ratio.split(":")
        return float(w) / float(h)
    except (ValueError, ZeroDivisionError):
        return 9.0 / 16.0


def _cut_subclip(source_path: str, start: float, end: float, out_path: str) -> str:
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", source_path,
        "-ss", f"{start:.3f}",
        "-to", f"{end:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        out_path,
    ]
    subprocess.run(cmd, check=True)
    return out_path


def _letterbox(frame: np.ndarray, crop_w: int, crop_h: int) -> np.ndarray:
    h, w = frame.shape[:2]
    scale = min(crop_w / w, crop_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(frame, (new_w, new_h))
    bg = cv2.resize(frame, (crop_w, crop_h))
    bg = cv2.GaussianBlur(bg, (LETTERBOX_BLUR, LETTERBOX_BLUR), 0)
    x_off = (crop_w - new_w) // 2
    y_off = (crop_h - new_h) // 2
    bg[y_off:y_off + new_h, x_off:x_off + new_w] = resized
    return bg


def _detect_faces_dnn(net, frame, conf_threshold: float = 0.5) -> List[Tuple[int, int, float, float, Tuple[int, int, int, int]]]:
    """Detect faces. Returns [(cx, cy, confidence, face_h_ratio, (x1,y1,x2,y2)), ...]."""
    h, w = frame.shape[:2]
    blob = cv2.dnn.blobFromImage(frame, 1.0, (300, 300), (104, 177, 123))
    net.setInput(blob)
    detections = net.forward()
    faces = []
    for i in range(detections.shape[2]):
        conf = detections[0, 0, i, 2]
        if conf < conf_threshold:
            continue
        box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
        x1, y1, x2, y2 = box.astype(int)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        face_h = (y2 - y1) / h
        faces.append((cx, cy, float(conf), float(face_h), (x1, y1, x2, y2)))
    return faces


def _compute_mouth_motion(frame_curr: np.ndarray, frame_prev: Optional[np.ndarray], 
                          bbox: Tuple[int, int, int, int]) -> float:
    """Compute motion energy in mouth region (lower 40% of face bbox)."""
    if frame_prev is None:
        return 0.0
    
    x1, y1, x2, y2 = bbox
    h = y2 - y1
    mouth_y1 = y1 + int(h * 0.6)  # lower 40%
    mouth_y2 = y2
    mouth_x1 = x1
    mouth_x2 = x2
    
    # clamp
    fh, fw = frame_curr.shape[:2]
    mouth_y1 = max(0, min(mouth_y1, fh - 1))
    mouth_y2 = max(0, min(mouth_y2, fh))
    mouth_x1 = max(0, min(mouth_x1, fw - 1))
    mouth_x2 = max(0, min(mouth_x2, fw))
    
    if mouth_y2 <= mouth_y1 or mouth_x2 <= mouth_x1:
        return 0.0
    
    region_curr = _to_gray(frame_curr[mouth_y1:mouth_y2, mouth_x1:mouth_x2])
    region_prev = _to_gray(frame_prev[mouth_y1:mouth_y2, mouth_x1:mouth_x2])
    
    diff = cv2.absdiff(region_curr, region_prev)
    return float(np.mean(diff)) / 255.0  # normalize 0-1


def _is_cut(hist_prev: np.ndarray, hist_curr: np.ndarray, threshold: float = CUT_THRESHOLD) -> bool:
    """Detect scene cut via histogram correlation."""
    corr = cv2.compareHist(hist_prev, hist_curr, cv2.HISTCMP_CORREL)
    return corr < threshold


def _compute_histogram(frame: np.ndarray) -> np.ndarray:
    """Compute normalized BGR histogram for cut detection."""
    hist = cv2.calcHist([frame], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
    cv2.normalize(hist, hist)
    return hist


def _classify_shot(face_ratio: float) -> str:
    if face_ratio > CLOSEUP_THRESHOLD:
        return "closeup"
    if face_ratio > MEDIUM_THRESHOLD:
        return "medium"
    return "wide_cut"


def _ease_in_out(t: float) -> float:
    """Ease-in-out interpolation (smooth start/end)."""
    return t * t * (3.0 - 2.0 * t)


def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation."""
    return a + (b - a) * t


# ── Pass 1: Analysis at SAMPLE_FPS ───────────────────────────────

def _analyze_video(
    in_path: str,
    net,
    crop_w: int,
    crop_h: int,
    src_w: int,
    src_h: int,
    camera_segments: List[Dict[str, Any]],
    clip_start_offset: float = 0.0
) -> List[SampleFrame]:
    """Pass 1: Analyze video using ground-truth camera segments to guide crop decisions.
    Applies strict behavior per segment type (master vs individual closeups) to eliminate noise.
    """
    cap = cv2.VideoCapture(in_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    sample_interval = max(1, int(fps / SAMPLE_FPS))
    
    samples: List[SampleFrame] = []
    prev_frame_gray = None
    frame_idx = 0
    
    # State tracking
    tracked_faces = {}  # tid -> (cx, cy, face_h)
    next_face_id = 0
    
    last_shot_type = "closeup"
    last_valid_cx = src_w // 2
    last_valid_cy = src_h // 2
    last_valid_ratio = 0.22  # default medium-ish ratio
    
    last_sample_frame_idx = -999
    
    while True:
        ret, frame = _read_bgr_frame(cap)
        if not ret or frame is None:
            break
        
        t = frame_idx / fps
        t_source = t + clip_start_offset
        
        # 1. Tentukan segmen kamera aktif berdasarkan waktu video sumber (t_source)
        active_seg = None
        for seg in camera_segments:
            if seg["start"] <= t_source <= seg["end"]:
                active_seg = seg
                break
                
        is_master_segment = True
        if active_seg is not None:
            is_master_segment = (active_seg["type"] == "master")
            
        # 2. Pemicu snap reset (is_cut): Terjadi saat berpindah jenis segmen kamera
        is_cut = False
        if len(samples) > 0:
            prev_t_source = samples[-1].time + clip_start_offset
            prev_seg = None
            for seg in camera_segments:
                if seg["start"] <= prev_t_source <= seg["end"]:
                    prev_seg = seg
                    break
            if prev_seg != active_seg:
                is_cut = True
                
        # 3. Ambil sampel jika berada di batas segmen (agar snap instan pas),
        # ATAU jika sudah melewati interval sampling reguler
        should_sample = is_cut or (frame_idx - last_sample_frame_idx >= sample_interval)
        
        if should_sample:
            last_sample_frame_idx = frame_idx
            
            if is_cut:
                # Reset pelacakan wajah pada transisi kamera baru
                tracked_faces.clear()
                
            if is_master_segment:
                # ── BEHAVIOR SEGMEN MASTER ────────────────────────────────
                # Paksa shot_type = "wide_cut" (letterbox blur penuh), letakkan di tengah.
                # Kita tidak mendeteksi wajah di segmen master untuk performa tinggi & zero noise.
                target_cx = src_w // 2
                target_cy = src_h // 2
                face_ratio = 0.0
                shot_type_to_use = "wide_cut"
                num_faces_detected = 2  # dummy count for master
            else:
                # ── BEHAVIOR SEGMEN INDIVIDU ──────────────────────────────
                # Paksa mode crop-track (closeup/medium).
                faces = _detect_faces_dnn(net, frame, CONFIDENCE_THRESHOLD)
                num_faces_detected = len(faces)
                
                if num_faces_detected > 0:
                    # Cocokkan wajah dengan tracked_faces (ambil terdekat untuk speaker utama)
                    current_faces = []
                    for cx, cy, conf, face_h, bbox in faces:
                        matched_id = None
                        min_dist = 120.0
                        
                        for tid, (tcx, tcy, _) in list(tracked_faces.items()):
                            dist = np.hypot(cx - tcx, cy - tcy)
                            if dist < min_dist:
                                min_dist = dist
                                matched_id = tid
                        
                        if matched_id is not None:
                            tracked_faces[matched_id] = (cx, cy, face_h)
                        else:
                            matched_id = next_face_id
                            tracked_faces[matched_id] = (cx, cy, face_h)
                            next_face_id += 1
                            
                        current_faces.append({
                            "id": matched_id,
                            "cx": cx,
                            "cy": cy,
                            "face_h": face_h,
                            "bbox": bbox
                        })
                    
                    # Bersihkan tracker lama
                    detected_ids = {f["id"] for f in current_faces}
                    for tid in list(tracked_faces.keys()):
                        if tid not in detected_ids:
                            del tracked_faces[tid]
                            
                    # Tentukan wajah utama (jika ada wajah tambahan lewat, abaikan)
                    # Kita pilih wajah terdekat ke pusat tracking atau yang memiliki ukuran terbesar
                    main_face = max(current_faces, key=lambda f: f["face_h"])
                    
                    target_cx = main_face["cx"]
                    target_cy = main_face["cy"]
                    face_ratio = main_face["face_h"]
                    shot_type_to_use = _classify_shot(face_ratio)
                    if shot_type_to_use == "wide_cut":
                        shot_type_to_use = "closeup" # Paksa crop di segmen individu
                        
                    last_valid_cx = target_cx
                    last_valid_cy = target_cy
                    last_valid_ratio = face_ratio
                    last_shot_type = shot_type_to_use
                else:
                    # Wajah hilang sementara (oklusi/nengok) -> TAHAN POSISI TERAKHIR secara mutlak.
                    # Jangan pernah melakukan fallback ke wide_cut / center!
                    target_cx = last_valid_cx
                    target_cy = last_valid_cy
                    face_ratio = last_valid_ratio
                    shot_type_to_use = last_shot_type
                    
            samples.append(SampleFrame(
                time=t,
                frame_idx=frame_idx,
                raw_cx=target_cx,
                raw_cy=target_cy,
                face_ratio=face_ratio,
                shot_type=shot_type_to_use,
                is_cut=is_cut,
                num_faces=num_faces_detected,
                is_group_reaction=False,
            ))
            
            if not is_master_segment:
                prev_frame_gray = _to_gray(frame)
                
        frame_idx += 1
        
    cap.release()
    return samples


def _apply_smoothing_non_causal(samples: List[SampleFrame], src_w: int, src_h: int) -> List[Tuple[int, int, str, bool]]:
    """Apply non-causal smoothing (moving average within scene boundaries) to eliminate camera lag."""
    if not samples:
        return []
        
    n = len(samples)
    smoothed = []
    
    # 1. Bagi sampel menjadi beberapa segmen scene terpisah berdasarkan boundary cut
    scenes = []
    current_scene = []
    
    for s in samples:
        if s.is_cut and current_scene:
            scenes.append(current_scene)
            current_scene = [s]
        else:
            current_scene.append(s)
            
    if current_scene:
        scenes.append(current_scene)
        
    # 2. Terapkan moving average di dalam masing-masing scene secara terpisah
    window_size = 5  # Jendela smoothing: 2 sebelum, 1 saat ini, 2 sesudah
    half_w = window_size // 2
    
    for scene in scenes:
        scene_len = len(scene)
        for i, s in enumerate(scene):
            # Jika ini adalah segmen master, kita paksa di tengah (tidak usah di-smooth)
            if s.shot_type == "wide_cut":
                smoothed.append((s.raw_cx, s.raw_cy, s.shot_type, s.is_cut))
                continue
                
            # Moving average dengan penanganan batas (boundary clamping)
            sum_cx = 0
            sum_cy = 0
            count = 0
            
            for j in range(max(0, i - half_w), min(scene_len, i + half_w + 1)):
                sum_cx += scene[j].raw_cx
                sum_cy += scene[j].raw_cy
                count += 1
                
            smooth_cx = int(sum_cx / count) if count > 0 else s.raw_cx
            smooth_cy = int(sum_cy / count) if count > 0 else s.raw_cy
            
            smoothed.append((smooth_cx, smooth_cy, s.shot_type, s.is_cut))
            
    return smoothed


def _generate_camera_segments(source_path: str, net) -> List[Dict[str, Any]]:
    """Analyze the full source video to detect scene cuts and classify camera shots (master vs individual).
    Returns a list of ground-truth camera segments.
    """
    cap = cv2.VideoCapture(source_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    duration = total_frames / fps
    
    # Gunakan 4 FPS untuk analisis segmentasi kamera (responsif & akurat)
    analysis_fps = 4.0
    interval = max(1, int(fps / analysis_fps))
    
    prev_hist = None
    frame_idx = 0
    
    raw_frames = []
    
    while True:
        ret, frame = _read_bgr_frame(cap)
        if not ret or frame is None:
            break
            
        t = frame_idx / fps
        
        # Hitung korelasi histogram frame-by-frame untuk deteksi cut presisi milidetik
        hist = _compute_histogram(frame)
        is_cut = False
        if prev_hist is not None:
            is_cut = _is_cut(prev_hist, hist, threshold=0.985)
            
        if frame_idx % interval == 0 or is_cut:
            faces = _detect_faces_dnn(net, frame, CONFIDENCE_THRESHOLD)
            raw_frames.append({
                "time": t,
                "frame_idx": frame_idx,
                "is_cut": is_cut,
                "num_faces": len(faces)
            })
            
        prev_hist = hist
        frame_idx += 1
        
    cap.release()
    
    # Kelompokkan segmentasi berdasarkan transisi cut (is_cut)
    segments = []
    current_segment_frames = []
    
    for f in raw_frames:
        if f["is_cut"] and current_segment_frames:
            segments.append(current_segment_frames)
            current_segment_frames = [f]
        else:
            current_segment_frames.append(f)
            
    if current_segment_frames:
        segments.append(current_segment_frames)
        
    camera_segments = []
    
    for i, seg_frames in enumerate(segments):
        start_t = seg_frames[0]["time"]
        end_t = segments[i+1][0]["time"] if i < len(segments) - 1 else duration
        
        # Tentukan tipe segmen: master (jika >= 2 wajah atau 0 wajah) atau individual (1 wajah)
        faces_counts = [f["num_faces"] for f in seg_frames]
        max_faces = max(faces_counts) if faces_counts else 0
        
        if max_faces >= 2 or max_faces == 0:
            seg_type = "master"
        else:
            seg_type = "individual"
            
        camera_segments.append({
            "start": start_t,
            "end": end_t,
            "type": seg_type
        })
        
    # Gabungkan segmen yang sangat pendek (< 1.5 detik) dengan tetangganya agar tidak flicker
    min_dur = 1.5
    refined_segments = []
    
    for s in camera_segments:
        if not refined_segments:
            refined_segments.append(s)
            continue
            
        last_s = refined_segments[-1]
        dur = s["end"] - s["start"]
        
        if dur < min_dur or s["type"] == last_s["type"]:
            last_s["end"] = s["end"]
        else:
            refined_segments.append(s)
            
    return refined_segments


# ── Pass 2: Render at full framerate with interpolation ──────────

def _render_frames(in_path: str, out_path: str, samples: List[SampleFrame], 
                   smoothed: List[Tuple[int, int, str, bool]], 
                   crop_w: int, crop_h: int) -> str:
    """Pass 2: Render video with interpolated crop positions."""
    cap = cv2.VideoCapture(in_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    
    silent_path = out_path + ".silent.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(silent_path, fourcc, fps, (crop_w, crop_h))
    
    n_samples = len(samples)
    frame_idx = 0
    
    while True:
        ret, frame = _read_bgr_frame(cap)
        if not ret or frame is None:
            break
        
        t = frame_idx / fps
        
        # Find bracketing samples
        prev_idx = 0
        next_idx = n_samples - 1
        for i in range(n_samples - 1):
            if samples[i].time <= t < samples[i + 1].time:
                prev_idx = i
                next_idx = i + 1
                break
        
        prev_s = samples[prev_idx]
        next_s = samples[next_idx]
        prev_smooth = smoothed[prev_idx]
        next_smooth = smoothed[next_idx]
        
        # Interpolation
        if prev_idx == next_idx:
            # Only one sample or exact match
            cx, cy, shot_type = prev_smooth[0], prev_smooth[1], prev_smooth[2]
        elif next_smooth[3]:  # next sample is a cut
            # CUT BOUNDARY: snap to next position (no interpolation across cut)
            if t < next_s.time:
                # Hold position of current scene
                cx, cy, shot_type = prev_smooth[0], prev_smooth[1], prev_smooth[2]
            else:
                # Snap instantly to new scene at the exact moment of the cut
                cx, cy, shot_type = next_smooth[0], next_smooth[1], next_smooth[2]
        else:
            # NORMAL: lerp with easing
            dt = next_s.time - prev_s.time
            alpha = (t - prev_s.time) / dt if dt > 0 else 0.0
            alpha = _ease_in_out(alpha)  # ease-in-out
            cx = int(_lerp(prev_smooth[0], next_smooth[0], alpha))
            cy = int(_lerp(prev_smooth[1], next_smooth[1], alpha))
            shot_type = prev_smooth[2]  # use prev shot type
        
        # Render
        if shot_type == "wide_cut":
            cropped = _letterbox(frame, crop_w, crop_h)
        else:
            # Apply dynamic zoom: slow push-in zoom (6% max zoom-in over duration)
            progress = min(1.0, max(0.0, frame_idx / total_frames))
            zoom_factor = 1.0 - 0.06 * progress
            
            w_z = int(crop_w * zoom_factor)
            h_z = int(crop_h * zoom_factor)
            # Ensure even dimensions
            w_z = max(2, w_z - (w_z % 2))
            h_z = max(2, h_z - (h_z % 2))
            
            x0 = max(0, min(src_w - w_z, cx - w_z // 2))
            y0 = max(0, min(src_h - h_z, cy - h_z // 2))
            cropped = frame[y0:y0 + h_z, x0:x0 + w_z]
            
            if w_z != crop_w or h_z != crop_h:
                cropped = cv2.resize(cropped, (crop_w, crop_h), interpolation=cv2.INTER_LANCZOS4)
        
        writer.write(cropped)
        frame_idx += 1
    
    cap.release()
    writer.release()
    
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
    
    # Compute target crop dimensions
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
    writer = cv2.VideoWriter(silent_path, fourcc, fps, (crop_w, crop_h))
    
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
    """Escape a file path for use inside an ffmpeg filter string.

    On Windows, drive-letter colons (C:) conflict with ffmpeg's filter option
    separator.  Fix: convert backslashes to forward-slash, then escape colons.
    """
    return path.replace("\\", "/").replace(":", "\\:")


def _mux_with_subtitles(
    silent_path: str,
    audio_source: str,
    out_path: str,
    subtitle_path: Optional[str] = None,
    fonts_dir: Optional[str] = None,
) -> None:
    """Single ffmpeg call: re-encode video with optional ASS burn-in + audio mux.

    When *subtitle_path* is provided the video is re-encoded through the
    ``ass`` filter (required because video filters cannot run on stream-copy).
    Without subtitles the video is still stream-copied for speed.
    """
    vf_parts: List[str] = []
    if subtitle_path:
        escaped = _ffmpeg_escape_path(os.path.abspath(subtitle_path))
        ass_filter = f"ass='{escaped}'"
        if fonts_dir:
            ass_filter += f":fontsdir='{_ffmpeg_escape_path(os.path.abspath(fonts_dir))}'"
        vf_parts.append(ass_filter)

    cmd = ["ffmpeg", "-y", "-loglevel", "error"]

    if vf_parts:
        # Re-encode: filter requires decode → filter → encode
        cmd += ["-i", silent_path]
        cmd += ["-i", audio_source]
        cmd += ["-vf", ",".join(vf_parts)]
        cmd += [
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-map", "0:v:0", "-map", "1:a:0?",
            "-shortest",
            out_path,
        ]
    else:
        # No subtitles → stream copy (fast, lossless)
        cmd += ["-i", silent_path]
        cmd += ["-i", audio_source]
        cmd += [
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k",
            "-map", "0:v:0", "-map", "1:a:0?",
            "-shortest",
            out_path,
        ]

    subprocess.run(cmd, check=True)


def _reframe_vertical(
    in_path: str,
    out_path: str,
    aspect_ratio: str,
    camera_segments: List[Dict[str, Any]],
    clip_start_offset: float = 0.0,
    is_master: bool = False,
    subtitle_path: Optional[str] = None,
    fonts_dir: Optional[str] = None,
) -> str:
    """Two-pass smart crop using ground-truth camera segments and non-causal smoothing."""
    if is_master:
        silent_path = _render_master_letterbox(in_path, out_path, aspect_ratio)
    else:
        target_ratio = _ratio(aspect_ratio)
        
        # Load DNN model
        if not os.path.exists(_PROTOTXT) or not os.path.exists(_MODEL):
            raise RuntimeError(f"DNN model not found at {_PROTOTXT} or {_MODEL}")
        net = cv2.dnn.readNetFromCaffe(_PROTOTXT, _MODEL)
        
        cap = cv2.VideoCapture(in_path)
        if not cap.isOpened():
            raise RuntimeError(f"could not open {in_path}")
        
        src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        
        # Compute crop dimensions
        if target_ratio < src_w / src_h:
            crop_h = src_h
            crop_w = int(crop_h * target_ratio)
        else:
            crop_w = src_w
            crop_h = int(crop_w / target_ratio)
        crop_w = max(2, crop_w - (crop_w % 2))
        crop_h = max(2, crop_h - (crop_h % 2))
        
        # Pass 1: Analysis guided by camera segments
        samples = _analyze_video(in_path, net, crop_w, crop_h, src_w, src_h, camera_segments, clip_start_offset)
        
        # Apply non-causal smoothing (moving average inside scene boundaries) to eliminate lag
        smoothed = _apply_smoothing_non_causal(samples, src_w, src_h)
        
        # Pass 2: Render with zero-lag smooth interpolation
        silent_path = _render_frames(in_path, out_path, samples, smoothed, crop_w, crop_h)

    # Final mux: audio + optional subtitle burn-in (single re-encode if subtitles)
    _mux_with_subtitles(silent_path, in_path, out_path, subtitle_path, fonts_dir)

    # Preserve intermediate for potential restyle (don't delete silent_path)
    return out_path


def _update_render_progress(task_id: str, current: int, total: int, msg: str):
    try:
        import asyncio
        from ..state import store
        pct = 60.0 + (float(current) / float(total)) * 30.0
        
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            future = asyncio.run_coroutine_threadsafe(
                store.set_progress(task_id, pct, "RENDER", msg), loop
            )
            future.result(timeout=2.0)
        else:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(store.set_progress(task_id, pct, "RENDER", msg))
            loop.close()
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
) -> List[Dict]:
    clips_dir = str(STORAGE_DIR / task_id / "clips")
    os.makedirs(clips_dir, exist_ok=True)
    results = []
    
    # Load DNN model untuk analisis segmen kamera video sumber
    if not os.path.exists(_PROTOTXT) or not os.path.exists(_MODEL):
        raise RuntimeError(f"DNN model not found at {_PROTOTXT} or {_MODEL}")
    net = cv2.dnn.readNetFromCaffe(_PROTOTXT, _MODEL)
    
    # 1. Muat atau buat segmentasi kamera video sumber (Ground Truth Segmenter)
    camera_segments_path = STORAGE_DIR / task_id / "camera_segments.json"
    camera_segments = []
    
    if camera_segments_path.exists():
        try:
            with open(camera_segments_path, "r", encoding="utf-8") as f:
                camera_segments = json.load(f)
            log.info("Loaded camera segments cache for task %s", task_id)
        except Exception as e:
            log.error("Failed to load camera segments cache: %s", e)
            
    if not camera_segments:
        log.info("Generating camera segments for source video %s...", source_path)
        camera_segments = _generate_camera_segments(source_path, net)
        try:
            with open(camera_segments_path, "w", encoding="utf-8") as f:
                json.dump(camera_segments, f, indent=2)
            log.info("Saved camera segments cache to %s", camera_segments_path)
        except Exception as e:
            log.error("Failed to save camera segments cache: %s", e)
            
    # Read the full transcript segments from cached json
    import json
    transcript_segments = []
    json_path = STORAGE_DIR / task_id / "transcript.json"
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                transcript_segments = json.load(f).get("segments", [])
        except Exception as e:
            log.error("Failed to load transcript.json for clip rendering: %s", e)

    # If transcript.json does not exist or has no segments, fall back to segments from main pipeline or cache
    for i, h in enumerate(highlights, 1):
        _update_render_progress(task_id, i - 1, len(highlights), f"Merender klip {i} dari {len(highlights)}…")
        out_path = os.path.join(clips_dir, f"short_{i:02d}.mp4")
        cut_path = out_path + ".cut.mp4"
        clip_ass_path = os.path.join(clips_dir, f"short_{i:02d}.ass")
        
        try:
            h_start = float(h["start_time"])
            h_end = float(h["end_time"])
            
            # Prepare segments offset specifically for this subclip
            clip_segments = []
            for seg in transcript_segments:
                s_start = float(seg.get("start", seg.get("start_time", 0.0)))
                s_end = float(seg.get("end", seg.get("end_time", 0.0)))
                
                # Check overlap: if segment overlaps with the highlight window
                if s_end > h_start and s_start < h_end:
                    # Clip boundaries to fit inside the highlight window
                    clamped_start = max(s_start, h_start)
                    clamped_end = min(s_end, h_end)
                    
                    # Create a copy offset to 0.0 relative to subclip start
                    seg_copy = dict(seg)
                    seg_copy["start"] = clamped_start - h_start
                    seg_copy["end"] = clamped_end - h_start
                    seg_copy["start_time"] = clamped_start - h_start
                    seg_copy["end_time"] = clamped_end - h_start
                    clip_segments.append(seg_copy)
            
            # Generate subtitle ASS specific to this clip
            resolved_subtitle_path = subtitle_path
            if clip_segments and subtitle_path:
                from .subtitles import generate_ass, STYLES, DEFAULT_STYLE
                style_key = subtitle_style
                if not style_key:
                    style_key = DEFAULT_STYLE
                    if os.path.exists(subtitle_path):
                        try:
                            with open(subtitle_path, "r", encoding="utf-8") as f:
                                main_ass_content = f.read()
                                from ..state import store
                                task_record = None
                                try:
                                    import asyncio
                                    try:
                                        loop = asyncio.get_running_loop()
                                    except RuntimeError:
                                        loop = None

                                    if loop and loop.is_running():
                                        import concurrent.futures
                                        future = asyncio.run_coroutine_threadsafe(store.get(task_id), loop)
                                        task_record = future.result(timeout=2.0)
                                    else:
                                        loop = asyncio.new_event_loop()
                                        task_record = loop.run_until_complete(store.get(task_id))
                                        loop.close()
                                except Exception:
                                    pass
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
                    play_res_x=1080, # PlayResX
                    play_res_y=1920, # PlayResY
                    fonts_dir=fonts_dir,
                )

            _cut_subclip(source_path, h_start, h_end, cut_path)
            _reframe_vertical(
                cut_path, out_path, aspect_ratio,
                camera_segments=camera_segments,
                clip_start_offset=h_start,
                subtitle_path=resolved_subtitle_path,
                fonts_dir=fonts_dir,
            )
            results.append({**h, "clip_url": f"/clips/{task_id}/short_{i:02d}.mp4"})
        except Exception as e:
            results.append({**h, "clip_url": None, "error": str(e)})
        finally:
            if os.path.exists(cut_path):
                os.remove(cut_path)
    _update_render_progress(task_id, len(highlights), len(highlights), "Semua klip selesai dirender")
    return results
