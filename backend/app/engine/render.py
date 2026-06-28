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
) -> List[SampleFrame]:
    """Pass 1: Analyze video using ground-truth camera segments to guide crop decisions.
    Applies strict behavior per segment type (master vs individual closeups) to eliminate noise.
    """
    if sp is None:
        sp = apply_sensitivity(50)
    cap = cv2.VideoCapture(in_path)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

        samples: List[SampleFrame] = []
        frame_idx = 0

        # State tracking
        tracked_faces = {}  # tid -> {"cx": cx, "cy": cy, "face_h": face_h, "missed_frames": 0, "bbox": bbox}

        active_speaker_id = None
        speaker_hold_counter = 0
        shot_hold_counter = 0

        last_shot_type = "closeup"
        last_valid_cx = src_w // 2
        last_valid_cy = src_h // 2
        last_valid_ratio = 0.22  # default medium-ish ratio

        last_sample_frame_idx = -999
        is_first_frame_of_cut = True
        frame_prev_sample = None
        face_lost_counter = 0

        # Amortized O(1) camera segment pointers
        active_seg_idx = 0
        last_sample_seg_idx = 0
        n_segments = len(camera_segments)

        while True:
            ret, frame = _read_bgr_frame(cap)
            if not ret or frame is None:
                break

            t = frame_idx / fps
            t_source = t + clip_start_offset

            # 1. Tentukan segmen kamera aktif menggunakan pointer amortized O(1)
            while active_seg_idx < n_segments - 1 and camera_segments[active_seg_idx + 1]["start"] <= t_source:
                active_seg_idx += 1

            active_seg = camera_segments[active_seg_idx] if n_segments > 0 else None

            is_master_segment = True
            seg_type = "master"
            if active_seg is not None:
                seg_type = active_seg["type"]
                is_master_segment = (seg_type == "master")

            # 2. Pemicu snap reset (is_cut): Terjadi saat berpindah indeks segmen kamera
            is_cut = False
            if len(samples) > 0:
                if last_sample_seg_idx != active_seg_idx:
                    is_cut = True

            # Tentukan interval sampling dinamis: 5 FPS untuk individu agar responsif, 2 FPS untuk master
            current_sample_fps = 2.0 if is_master_segment else 5.0
            sample_interval = max(1, int(fps / current_sample_fps))

            # 3. Ambil sampel jika berada di batas segmen (agar snap instan pas),
            # ATAU jika sudah melewati interval sampling reguler
            should_sample = is_cut or (frame_idx - last_sample_frame_idx >= sample_interval)

            if should_sample:
                last_sample_frame_idx = frame_idx
                last_sample_seg_idx = active_seg_idx

                if is_cut:
                    # Reset pelacakan wajah pada transisi kamera baru
                    tracked_faces.clear()
                    is_first_frame_of_cut = True
                    active_speaker_id = None
                    speaker_hold_counter = 0
                    shot_hold_counter = sp.min_shot_hold_samples

                    # Default fallback spasial awal yang disesuaikan berdasarkan segmentasi
                    if active_seg is not None and "avg_cx" in active_seg:
                        last_valid_cx = int(active_seg["avg_cx"])
                    else:
                        if seg_type == "left":
                            last_valid_cx = int(src_w * 0.25)
                        elif seg_type == "right":
                            last_valid_cx = int(src_w * 0.75)
                        else:
                            last_valid_cx = src_w // 2
                    last_valid_cy = src_h // 2
                    last_valid_ratio = 0.22
                    last_shot_type = "closeup" if not is_master_segment else "wide_cut"

                is_group = False

                # FACE DETECTION (master & individual)
                if is_master_segment:
                    faces = _detect_faces(detector, face_detector, frame, max(0.20, sp.confidence_threshold - 0.10))
                else:
                    faces = _detect_faces(detector, face_detector, frame, sp.confidence_threshold)

                # Camera Lock Anchor
                locked_cx = int(active_seg.get("avg_cx", src_w // 2)) if active_seg else src_w // 2

                # Filter spasial: abaikan wajah dari sisi yang salah
                filtered_faces = []
                for face in faces:
                    cx, cy, conf, face_h, bbox = face
                    if seg_type == "left":
                        if cx < src_w * 0.6:
                            filtered_faces.append(face)
                    elif seg_type == "right":
                        if cx > src_w * 0.4:
                            filtered_faces.append(face)
                    else:
                        filtered_faces.append(face)

                num_faces_detected = len(filtered_faces)
                current_faces = []

                if num_faces_detected > 0:
                    # Greedy One-to-One Matching
                    candidates = []
                    for f_idx, (cx, cy, conf, face_h, bbox) in enumerate(filtered_faces):
                        face_height_px = face_h * src_h
                        local_threshold = max(50.0, face_height_px * 1.5)

                        for tid, tinfo in tracked_faces.items():
                            dist = np.hypot(cx - tinfo["cx"], cy - tinfo["cy"])
                            if dist < local_threshold:
                                candidates.append((dist, f_idx, tid))

                    candidates.sort(key=lambda x: x[0])

                    matched_faces_map = {}
                    assigned_tids = set()

                    for dist, f_idx, tid in candidates:
                        if f_idx not in matched_faces_map and tid not in assigned_tids:
                            matched_faces_map[f_idx] = tid
                            assigned_tids.add(tid)

                    for f_idx, face in enumerate(filtered_faces):
                        cx, cy, conf, face_h, bbox = face
                        bbox_prev = None

                        if f_idx in matched_faces_map:
                            tid = matched_faces_map[f_idx]
                            bbox_prev = tracked_faces[tid].get("bbox")
                            tracked_faces[tid].update({
                                "cx": cx, "cy": cy, "face_h": face_h,
                                "missed_frames": 0, "bbox": bbox
                            })
                        else:
                            assigned_ids = set(tracked_faces.keys())
                            tid = 0
                            while tid in assigned_ids:
                                tid += 1
                            tracked_faces[tid] = {
                                "cx": cx, "cy": cy, "face_h": face_h,
                                "missed_frames": 0, "bbox": bbox
                            }

                        motion_val = _compute_mouth_motion(frame, frame_prev_sample, bbox, bbox_prev)
                        size_score = min(1.0, face_h / 0.5)
                        total_score = sp.motion_weight * motion_val + sp.size_weight * size_score

                        current_faces.append({
                            "id": tid, "cx": cx, "cy": cy, "face_h": face_h,
                            "bbox": bbox, "motion": motion_val, "score": total_score
                        })

                # Kelola masa tenggang missed tracker
                detected_ids = {f["id"] for f in current_faces}
                for tid in list(tracked_faces.keys()):
                    if tid not in detected_ids:
                        tracked_faces[tid]["missed_frames"] += 1
                        if tracked_faces[tid]["missed_frames"] > sp.max_missed_samples:
                            del tracked_faces[tid]
                            if active_speaker_id == tid:
                                active_speaker_id = None
                                speaker_hold_counter = 0

                if num_faces_detected > 0:
                    face_lost_counter = 0

                    if num_faces_detected >= 2:
                        # 2+ orang di frame → tampilkan horizontal + blur
                        is_group = True

                    effective_switch_margin = sp.switch_margin
                    if num_faces_detected > 2:
                        effective_switch_margin *= 1.5

                    for f in current_faces:
                        tinfo = tracked_faces.get(f["id"])
                        if tinfo is not None:
                            if "motion_history" not in tinfo:
                                tinfo["motion_history"] = []
                            tinfo["motion_history"].append(f["motion"])
                            if len(tinfo["motion_history"]) > 3:
                                tinfo["motion_history"].pop(0)
                            smooth_motion = sum(tinfo["motion_history"]) / len(tinfo["motion_history"])
                        else:
                            smooth_motion = f["motion"]
                        bonus = 0.05 if f["id"] == active_speaker_id else 0
                        f["score"] = sp.motion_weight * smooth_motion + sp.size_weight * min(1.0, f.get("face_h", 1.0) / 0.5) + bonus

                    best_face = max(current_faces, key=lambda f: f["score"])
                    curr_active_face = next((f for f in current_faces if f["id"] == active_speaker_id), None)

                    if active_speaker_id is None or curr_active_face is None:
                        active_speaker_id = best_face["id"]
                        speaker_hold_counter = 1
                        main_face = best_face
                    else:
                        if best_face["id"] == active_speaker_id:
                            speaker_hold_counter += 1
                            main_face = best_face
                        else:
                            score_diff = best_face["score"] - curr_active_face["score"]
                            if speaker_hold_counter >= sp.min_hold_samples and score_diff >= effective_switch_margin:
                                active_speaker_id = best_face["id"]
                                speaker_hold_counter = 1
                                main_face = best_face
                            else:
                                speaker_hold_counter += 1
                                main_face = curr_active_face

                    # Deadzone Tracking horizontal & Snap instan
                    if is_group:
                        # 2+ orang: tampilkan horizontal + blur background, bukan crop
                        target_cx = src_w // 2
                        target_cy = src_h // 2
                        face_ratio = 0.0  # force wide_cut classification
                    else:
                        live_cx = main_face["cx"]

                        if is_first_frame_of_cut:
                            target_cx = live_cx
                            is_first_frame_of_cut = False
                        else:
                            deadzone_margin = int(crop_w * 0.10)
                            diff_x = live_cx - last_valid_cx

                            if abs(diff_x) < deadzone_margin:
                                target_cx = last_valid_cx
                            else:
                                target_cx = live_cx

                            target_cx = int(0.75 * target_cx + 0.25 * locked_cx)

                        target_cy = main_face["cy"]
                        face_ratio = main_face["face_h"]

                    # Klasifikasi tipe shot dengan hysteresis
                    shot_type_raw = _classify_shot(face_ratio)
                    if shot_type_raw == "wide_cut":
                        shot_type_raw = "closeup"

                    if shot_type_raw == last_shot_type:
                        shot_hold_counter += 1
                        shot_type_to_use = last_shot_type
                    else:
                        if shot_hold_counter >= sp.min_shot_hold_samples:
                            last_shot_type = shot_type_raw
                            shot_hold_counter = 1
                            shot_type_to_use = shot_type_raw
                        else:
                            shot_hold_counter += 1
                            shot_type_to_use = last_shot_type

                    last_valid_cx = target_cx
                    last_valid_cy = target_cy
                    last_valid_ratio = face_ratio
                    last_shot_type = shot_type_to_use
                else:
                    # Wajah hilang sementara -> TAHAN POSISI TERAKHIR
                    face_lost_counter += 1
                    if face_lost_counter > 6:
                        target_cx = int(0.90 * last_valid_cx + 0.10 * locked_cx)
                        target_cy = int(0.90 * last_valid_cy + 0.10 * (src_h // 2))
                    else:
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
                    is_group_reaction=is_group,
                ))

                frame_prev_sample = frame.copy() if frame is not None else None

            frame_idx += 1
    finally:
        cap.release()

    return samples


# ── Pass 2: Render at full framerate with interpolation ──────────

def _render_frames(in_path: str, out_path: str, samples: List[SampleFrame],
                   smoothed: List[Tuple[int, int, float, str, bool]],
                   crop_w: int, crop_h: int) -> str:
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

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(silent_path, cv2.CAP_FFMPEG, fourcc, fps, (crop_w, crop_h))
        if not writer.isOpened():
            raise RuntimeError(f"Could not open VideoWriter for path: {silent_path}")
        try:
            n_samples = len(samples)
            frame_idx = 0

            # Amortized O(1) bracket pointer
            sample_pointer = 0

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
                if shot_type == "wide_cut":
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
        cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
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

            samples = _analyze_video(in_path, detector, crop_w, crop_h, src_w, src_h, camera_segments, clip_start_offset=0.0, face_detector=face_detector, sp=sp)

            if not samples:
                log.warning("Samples kosong setelah _analyze_video. Fallback ke master letterbox.")
                silent_path = _render_master_letterbox(in_path, out_path, aspect_ratio)
            else:
                smoothed = _apply_smoothing_non_causal(samples, src_w, src_h)
                silent_path = _render_frames(in_path, out_path, samples, smoothed, crop_w, crop_h)
        finally:
            if hasattr(detector, "close"):
                try:
                    detector.close()
                except Exception:
                    pass

    _mux_with_subtitles(silent_path, in_path, out_path, subtitle_path, fonts_dir, encoder_args)
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
            )
            results.append({**h, "clip_url": f"/clips/{task_id}/short_{i:02d}.mp4"})
        except Exception as e:
            results.append({**h, "clip_url": None, "error": str(e)})
        finally:
            if os.path.exists(cut_path):
                os.remove(cut_path)
    _update_render_progress(task_id, len(highlights), len(highlights), "Semua klip selesai dirender")
    return results
