"""Smart crop renderer — two-pass interpolation, cut detection, motion-aware face selection.

Fix 1: Two-pass interpolation (sample 2FPS → EMA → lerp render with easing)
Fix 2: Cut detection (histogram correlation) + EMA reset on cuts
Fix 3: Smart face selection (motion energy mouth + group_reaction for 3+ faces)
"""
import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from ..config import STORAGE_DIR

log = logging.getLogger(__name__)

# ── tuning knobs ──────────────────────────────────────────────────
SAMPLE_FPS = 4
EMA_FACTOR = 0.15
CONFIDENCE_THRESHOLD = 0.30
CLOSEUP_THRESHOLD = 0.30
MEDIUM_THRESHOLD = 0.15
LETTERBOX_BLUR = 61
CUT_THRESHOLD = 0.97          # histogram correlation below this = cut
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
_MODEL_YN = os.path.join(_DIR, "..", "..", "models", "face_detection_yunet_2023mar.onnx")


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


def _load_face_detector(face_detector: str):
    """Factory to load selected face detector (YuNet, MediaPipe BlazeFace, YOLOv8-Face, SSD)."""
    if face_detector == "yunet":
        _MODEL_YN = os.path.join(_DIR, "..", "..", "models", "face_detection_yunet_2023mar.onnx")
        if not os.path.exists(_MODEL_YN):
            raise RuntimeError(f"YuNet model not found at {_MODEL_YN}")
        return cv2.FaceDetectorYN.create(
            model=_MODEL_YN,
            config="",
            input_size=(300, 300),
            score_threshold=0.3,
            nms_threshold=0.3
        )
    elif face_detector == "mediapipe":
        _MODEL_MP = os.path.join(_DIR, "..", "..", "models", "blaze_face_short_range.tflite")
        if not os.path.exists(_MODEL_MP):
            raise RuntimeError(f"MediaPipe BlazeFace model not found at {_MODEL_MP}")
        import mediapipe as mp
        BaseOptions = mp.tasks.BaseOptions
        FaceDetector = mp.tasks.vision.FaceDetector
        FaceDetectorOptions = mp.tasks.vision.FaceDetectorOptions
        options = FaceDetectorOptions(
            base_options=BaseOptions(model_asset_path=_MODEL_MP),
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            min_detection_confidence=0.20
        )
        return FaceDetector.create_from_options(options)
    elif face_detector == "yolov8-face":
        _MODEL_YOLO = os.path.join(_DIR, "..", "..", "models", "yolov8n-face.onnx")
        if not os.path.exists(_MODEL_YOLO):
            raise RuntimeError(f"YOLOv8-Face model not found at {_MODEL_YOLO}")
        return cv2.dnn.readNetFromONNX(_MODEL_YOLO)
    elif face_detector == "ssd":
        _PROTOTXT = os.path.join(_DIR, "..", "..", "models", "deploy.prototxt")
        _MODEL = os.path.join(_DIR, "..", "..", "models", "res10_300x300_ssd_iter_140000.caffemodel")
        if not os.path.exists(_PROTOTXT) or not os.path.exists(_MODEL):
            raise RuntimeError(f"SSD model not found at {_PROTOTXT} or {_MODEL}")
        return cv2.dnn.readNetFromCaffe(_PROTOTXT, _MODEL)
    else:
        raise ValueError(f"Unknown face detector: {face_detector}")


def _detect_faces(detector, face_detector_type: str, frame: np.ndarray, conf_threshold: float = 0.3) -> List[Tuple[int, int, float, float, Tuple[int, int, int, int]]]:
    """Unified face detection entry point supporting multiple models."""
    if face_detector_type == "yunet":
        return _detect_faces_yunet(detector, frame, conf_threshold)
    elif face_detector_type == "mediapipe":
        return _detect_faces_mediapipe(detector, frame, conf_threshold)
    elif face_detector_type == "yolov8-face":
        return _detect_faces_yolov8(detector, frame, conf_threshold)
    elif face_detector_type == "ssd":
        return _detect_faces_ssd(detector, frame, conf_threshold)
    else:
        raise ValueError(f"Unknown face detector type: {face_detector_type}")


def _detect_faces_yunet(detector, frame: np.ndarray, conf_threshold: float = 0.3) -> List[Tuple[int, int, float, float, Tuple[int, int, int, int]]]:
    """Detect faces using YuNet (extremely fast, lightweight, and accurate for side profile)."""
    h, w = frame.shape[:2]
    detector.setInputSize((w, h))
    detector.setScoreThreshold(conf_threshold)
    retval, detections = detector.detect(frame)
    
    faces = []
    if detections is not None:
        for face in detections:
            x1, y1, box_w, box_h = map(int, face[0:4])
            conf = float(face[14])
            x1, y1 = max(0, x1), max(0, y1)
            x2 = min(w, x1 + box_w)
            y2 = min(h, y1 + box_h)
            box_w = x2 - x1
            box_h = y2 - y1
            cx = x1 + box_w // 2
            cy = y1 + box_h // 2
            face_h_ratio = box_h / h
            faces.append((cx, cy, conf, face_h_ratio, (x1, y1, x2, y2)))
    return faces


def _detect_faces_mediapipe(detector, frame: np.ndarray, conf_threshold: float = 0.3) -> List[Tuple[int, int, float, float, Tuple[int, int, int, int]]]:
    """Detect faces using MediaPipe BlazeFace (short range)."""
    h, w = frame.shape[:2]
    import mediapipe as mp
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
    detection_result = detector.detect(mp_image)
    
    faces = []
    if detection_result.detections:
        for detection in detection_result.detections:
            score = detection.categories[0].score
            if score < conf_threshold:
                continue
            bbox = detection.bounding_box
            x1 = bbox.origin_x
            y1 = bbox.origin_y
            box_w = bbox.width
            box_h = bbox.height
            x1, y1 = max(0, x1), max(0, y1)
            x2 = min(w, x1 + box_w)
            y2 = min(h, y1 + box_h)
            box_w = x2 - x1
            box_h = y2 - y1
            cx = x1 + box_w // 2
            cy = y1 + box_h // 2
            face_h_ratio = box_h / h
            faces.append((cx, cy, score, face_h_ratio, (x1, y1, x2, y2)))
    return faces


def _detect_faces_yolov8(net, frame: np.ndarray, conf_threshold: float = 0.3) -> List[Tuple[int, int, float, float, Tuple[int, int, int, int]]]:
    """Detect faces using YOLOv8-face ONNX model (fast and accurate)."""
    h, w = frame.shape[:2]
    blob = cv2.dnn.blobFromImage(frame, 1/255.0, (640, 640), swapRB=True, crop=False)
    net.setInput(blob)
    out = net.forward()
    predictions = out[0].T
    
    boxes = []
    confidences = []
    for pred in predictions:
        conf = float(pred[4])
        if conf < conf_threshold:
            continue
        cx_net, cy_net, w_net, h_net = pred[0:4]
        x1_net = cx_net - w_net / 2.0
        y1_net = cy_net - h_net / 2.0
        x1 = int(x1_net * (w / 640.0))
        y1 = int(y1_net * (h / 640.0))
        box_w = int(w_net * (w / 640.0))
        box_h = int(h_net * (h / 640.0))
        boxes.append([x1, y1, box_w, box_h])
        confidences.append(conf)
        
    indices = cv2.dnn.NMSBoxes(boxes, confidences, conf_threshold, nms_threshold=0.45)
    
    faces = []
    if len(indices) > 0:
        indices = indices.flatten()
        for idx in indices:
            x1, y1, box_w, box_h = boxes[idx]
            x1, y1 = max(0, x1), max(0, y1)
            x2 = min(w, x1 + box_w)
            y2 = min(h, y1 + box_h)
            box_w = x2 - x1
            box_h = y2 - y1
            cx = x1 + box_w // 2
            cy = y1 + box_h // 2
            face_h_ratio = box_h / h
            faces.append((cx, cy, confidences[idx], face_h_ratio, (x1, y1, x2, y2)))
    return faces


def _detect_faces_ssd(net, frame: np.ndarray, conf_threshold: float = 0.5) -> List[Tuple[int, int, float, float, Tuple[int, int, int, int]]]:
    """Detect faces using SSD ResNet-10 (Caffe)."""
    h, w = frame.shape[:2]
    blob = cv2.dnn.blobFromImage(frame, 1.0, (300, 300), (104, 177, 123))
    net.setInput(blob)
    detections = net.forward()
    
    boxes = []
    confidences = []
    for i in range(detections.shape[2]):
        conf = detections[0, 0, i, 2]
        if conf < conf_threshold:
            continue
        box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
        x1, y1, x2, y2 = box.astype(int)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        box_w = x2 - x1
        box_h = y2 - y1
        boxes.append([x1, y1, box_w, box_h])
        confidences.append(float(conf))
        
    indices = cv2.dnn.NMSBoxes(boxes, confidences, conf_threshold, nms_threshold=0.3)
    
    faces = []
    if len(indices) > 0:
        indices = indices.flatten()
        for idx in indices:
            x1, y1, box_w, box_h = boxes[idx]
            x2 = x1 + box_w
            y2 = y1 + box_h
            cx = x1 + box_w // 2
            cy = y1 + box_h // 2
            conf = confidences[idx]
            face_h_ratio = box_h / h
            faces.append((cx, cy, conf, face_h_ratio, (x1, y1, x2, y2)))
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
    detector,
    crop_w: int,
    crop_h: int,
    src_w: int,
    src_h: int,
    camera_segments: List[Dict[str, Any]],
    clip_start_offset: float = 0.0,
    face_detector: str = "yunet"
) -> List[SampleFrame]:
    """Pass 1: Analyze video using ground-truth camera segments to guide crop decisions.
    Applies strict behavior per segment type (master vs individual closeups) to eliminate noise.
    """
    cap = cv2.VideoCapture(in_path)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        
        samples: List[SampleFrame] = []
        frame_idx = 0
        
        # State tracking
        tracked_faces = {}  # tid -> {"cx": cx, "cy": cy, "face_h": face_h, "missed_frames": 0, "bbox": bbox}
        next_face_id = 0
        
        active_speaker_id = None
        speaker_hold_counter = 0
        shot_hold_counter = 0
        
        last_shot_type = "closeup"
        last_valid_cx = src_w // 2
        last_valid_cy = src_h // 2
        last_valid_ratio = 0.22  # default medium-ish ratio
        
        last_sample_frame_idx = -999
        is_first_frame_of_cut = True
        frame_prev = None
        
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
            seg_type = "master"
            if active_seg is not None:
                seg_type = active_seg["type"]
                is_master_segment = (seg_type == "master")
                
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
                    
            # Tentukan interval sampling dinamis: 5 FPS untuk individu agar responsif, 2 FPS untuk master
            current_sample_fps = 2.0 if is_master_segment else 5.0
            sample_interval = max(1, int(fps / current_sample_fps))
            
            # 3. Ambil sampel jika berada di batas segmen (agar snap instan pas),
            # ATAU jika sudah melewati interval sampling reguler
            should_sample = is_cut or (frame_idx - last_sample_frame_idx >= sample_interval)
            
            if should_sample:
                last_sample_frame_idx = frame_idx
                
                if is_cut:
                    # Reset pelacakan wajah pada transisi kamera baru
                    tracked_faces.clear()
                    is_first_frame_of_cut = True
                    active_speaker_id = None
                    speaker_hold_counter = 0
                    shot_hold_counter = MIN_SHOT_HOLD_SAMPLES
                    
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
                    # Camera Lock Anchor
                    locked_cx = int(active_seg.get("avg_cx", src_w // 2)) if active_seg else src_w // 2
                    
                    # Deteksi wajah diaktifkan untuk menyesuaikan target_cy dan zoom
                    faces = _detect_faces(detector, face_detector, frame, CONFIDENCE_THRESHOLD)
                    
                    # Filter spasial: abaikan wajah dari sisi yang salah untuk mencegah cross-talk
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
                    
                    if num_faces_detected > 0:
                        current_faces = []
                        
                        # Pelacakan dengan threshold jarak dinamis sesuai resolusi (10% lebar frame)
                        tracking_threshold = src_w * 0.10
                        
                        for cx, cy, conf, face_h, bbox in filtered_faces:
                            matched_id = None
                            min_dist = tracking_threshold
                            
                            for tid, tinfo in list(tracked_faces.items()):
                                dist = np.hypot(cx - tinfo["cx"], cy - tinfo["cy"])
                                if dist < min_dist:
                                    min_dist = dist
                                    matched_id = tid
                            
                            if matched_id is not None:
                                tracked_faces[matched_id].update({
                                    "cx": cx,
                                    "cy": cy,
                                    "face_h": face_h,
                                    "missed_frames": 0,
                                    "bbox": bbox
                                })
                            else:
                                matched_id = next_face_id
                                tracked_faces[matched_id] = {
                                    "cx": cx,
                                    "cy": cy,
                                    "face_h": face_h,
                                    "missed_frames": 0,
                                    "bbox": bbox
                                }
                                next_face_id += 1
                                
                            # Hitung mouth motion untuk wajah ini
                            motion_val = _compute_mouth_motion(frame, frame_prev, bbox) if frame_prev is not None else 0.0
                            size_score = min(1.0, face_h / 0.5)
                            total_score = MOTION_WEIGHT * motion_val + SIZE_WEIGHT * size_score
                            
                            current_faces.append({
                                "id": matched_id,
                                "cx": cx,
                                "cy": cy,
                                "face_h": face_h,
                                "bbox": bbox,
                                "motion": motion_val,
                                "score": total_score
                            })
                        
                        # Kelola masa tenggang missed tracker
                        detected_ids = {f["id"] for f in current_faces}
                        for tid in list(tracked_faces.keys()):
                            if tid not in detected_ids:
                                tracked_faces[tid]["missed_frames"] += 1
                                if tracked_faces[tid]["missed_frames"] > MAX_MISSED_SAMPLES:
                                    del tracked_faces[tid]
                                    
                        # Tentukan is_group_reaction
                        if num_faces_detected >= GROUP_REACTION_MIN_FACES:
                            avg_motion = sum(f["motion"] for f in current_faces) / num_faces_detected
                            if avg_motion >= GROUP_REACTION_MOTION_THRESH:
                                is_group = True
                                
                        # Tentukan wajah utama dengan mempertimbangkan hysteresis dan mouth motion
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
                                if speaker_hold_counter >= MIN_HOLD_SAMPLES and score_diff >= SWITCH_MARGIN:
                                    active_speaker_id = best_face["id"]
                                    speaker_hold_counter = 1
                                    main_face = best_face
                                else:
                                    speaker_hold_counter += 1
                                    main_face = curr_active_face
                        
                        # Deadzone Tracking horizontal & Snap instan
                        if is_group:
                            # Group Reaction: posisikan di tengah dari semua wajah yang terdeteksi
                            target_cx = int(sum(f["cx"] for f in current_faces) / len(current_faces))
                            target_cy = int(sum(f["cy"] for f in current_faces) / len(current_faces))
                            face_ratio = 0.0  # Paksa rasio kecil agar masuk wide shot
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
                                    
                                # Mean reversion: tarik kembali perlahan ke locked_cx (anchor) untuk mencegah drift horizontal
                                target_cx = int(0.75 * target_cx + 0.25 * locked_cx)
                                
                            target_cy = main_face["cy"]
                            face_ratio = main_face["face_h"]
                        
                        # Klasifikasi tipe shot dengan hysteresis
                        shot_type_raw = _classify_shot(face_ratio)
                        if is_group:
                            shot_type_raw = "wide_cut"
                        elif shot_type_raw == "wide_cut":
                            shot_type_raw = "closeup"  # Paksa crop di segmen individu
                            
                        if shot_type_raw == last_shot_type:
                            shot_hold_counter += 1
                            shot_type_to_use = last_shot_type
                        else:
                            if shot_hold_counter >= MIN_SHOT_HOLD_SAMPLES:
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
                        # Wajah hilang sementara (oklusi/nengok) -> TAHAN POSISI TERAKHIR secara mutlak.
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
                
            frame_prev = frame.copy() if frame is not None else None
            frame_idx += 1
    finally:
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
    window_size = 3  # FIX: Turunin ke 3 biar gak telat ngerender pergerakan
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


def _generate_camera_segments(source_path: str, detector, face_detector: str) -> List[Dict[str, Any]]:
    """Analyze the full source video to detect scene cuts and classify camera shots (master vs individual).
    Returns a list of ground-truth camera segments.
    """
    cap = cv2.VideoCapture(source_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    duration = total_frames / fps
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    
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
            is_cut = _is_cut(prev_hist, hist, threshold=CUT_THRESHOLD)
            
        if frame_idx % interval == 0 or is_cut:
            # FIX 1: Turunkan threshold jadi 0.25 khusus buat ngecek scene
            # biar muka yg jauh/nengok di kamera master gak gampang hilang
            faces = _detect_faces(detector, face_detector, frame, conf_threshold=0.25)
            raw_frames.append({
                "time": t,
                "frame_idx": frame_idx,
                "is_cut": is_cut,
                "num_faces": len(faces),
                "faces_cx": [face[0] for face in faces] if faces else [],
                "face_ratios": [face[3] for face in faces] if faces else [] # Ambil data ukuran muka
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
        
        total_f = len(seg_frames)
        if total_f == 0:
            seg_type = "master"
        else:
            count_2_plus = sum(1 for f in seg_frames if f["num_faces"] >= 2)
            
            # Wajah kecil: untuk model lain pakai 0.15, untuk mediapipe pakai 0.22
            # karena mediapipe tidak bisa deteksi profil wajah di master shot
            small_ratio_thresh = 0.22 if face_detector == "mediapipe" else 0.15
            count_small_faces = sum(1 for f in seg_frames if f["face_ratios"] and max(f["face_ratios"]) < small_ratio_thresh)
            
            # Cek apakah segmen ini menunjukkan tanda-tanda ada 2+ orang secara konsisten (untuk membedakan dari noise deteksi wajah)
            has_multiple_people = (count_2_plus >= 2) and (count_2_plus / total_f >= 0.08)
            
            # Kriteria deteksi master:
            # 1. Cukup 35% frame kedetek 2 orang (bukti langsung master shot, dinaikkan dari 18% agar lebih kebal noise).
            # 2. ATAU (jika terbukti ada 2+ orang secara konsisten di segmen ini) 70% frame berwajah kecil (kamera jauh/master).
            # Ini mencegah single-person wide/medium shot (yang wajahnya kecil tapi hanya ada 1 orang) dikira sebagai master.
            is_master = (count_2_plus / total_f >= 0.35) or (has_multiple_people and (count_small_faces / total_f >= 0.70))
            
            # Fallback khusus MediaPipe: jika >70% frame tidak ada deteksi wajah sama sekali,
            # kemungkinan besar ini adalah master di mana mediapipe buta profil.
            if face_detector == "mediapipe" and not is_master:
                count_no_faces = sum(1 for f in seg_frames if f["num_faces"] == 0)
                if count_no_faces / total_f >= 0.70:
                    is_master = True
                    
            seg_type = "master" if is_master else "individual"

                
        # Klasifikasi spasial (left/right) jika segmen individual
        if seg_type == "individual":
            all_cx = []
            for f in seg_frames:
                if f.get("faces_cx"):
                    all_cx.append(sum(f["faces_cx"]) / len(f["faces_cx"]))
            
            if all_cx:
                avg_cx = sum(all_cx) / len(all_cx)
                if avg_cx < src_w * 0.47:  # Diperketat agar closeup condong kiri terdeteksi left
                    seg_type = "left"
                elif avg_cx > src_w * 0.53:  # Diperketat agar closeup condong kanan terdeteksi right
                    seg_type = "right"
                else:
                    seg_type = "individual"
            else:
                if len(camera_segments) > 0:
                    seg_type = camera_segments[-1]["type"]
                else:
                    seg_type = "individual"
            
        camera_segments.append({
            "start": start_t,
            "end": end_t,
            "type": seg_type
        })
        
    # FIX: Hapus penggabungan segmen bertipe sama agar batas cut asli tidak hancur.
    refined_segments = camera_segments.copy()
            
    # Pass 2: Hanya gabungkan anomali di tengah jika durasi sangat ekstrem (< 0.5s)
    i = 1
    while i < len(refined_segments) - 1:
        s = refined_segments[i]
        dur = s["end"] - s["start"]
        if dur < 0.5:
            prev_s = refined_segments[i-1]
            next_s = refined_segments[i+1]
            if prev_s["type"] == next_s["type"]:
                prev_s["end"] = next_s["end"]
                refined_segments.pop(i)  # hapus s
                refined_segments.pop(i)  # hapus next_s
                continue
        i += 1
        
    # Pass 3: Gabungkan segmen yang sangat pendek di ujung jika durasi ekstrem < 0.8s
    if len(refined_segments) > 1:
        if (refined_segments[0]["end"] - refined_segments[0]["start"]) < 0.8:
            refined_segments[1]["start"] = refined_segments[0]["start"]
            refined_segments.pop(0)
    if len(refined_segments) > 1:
        if (refined_segments[-1]["end"] - refined_segments[-1]["start"]) < 0.8:
            refined_segments[-2]["end"] = refined_segments[-1]["end"]
            refined_segments.pop(-1)
            
    # Hitung ulang avg_cx yang stabil untuk segmen refined non-master
    for s in refined_segments:
        if s["type"] != "master":
            seg_cx = []
            for f in raw_frames:
                if s["start"] <= f["time"] <= s["end"]:
                    seg_cx.extend(f.get("faces_cx", []))
            if seg_cx:
                s["avg_cx"] = float(sum(seg_cx) / len(seg_cx))
            else:
                if s["type"] == "left":
                    s["avg_cx"] = float(src_w * 0.25)
                elif s["type"] == "right":
                    s["avg_cx"] = float(src_w * 0.75)
                else:
                    s["avg_cx"] = float(src_w / 2.0)
        else:
            s["avg_cx"] = float(src_w / 2.0)
            
    return refined_segments


# ── Pass 2: Render at full framerate with interpolation ──────────

def _render_frames(in_path: str, out_path: str, samples: List[SampleFrame], 
                   smoothed: List[Tuple[int, int, str, bool]], 
                   crop_w: int, crop_h: int) -> str:
    """Pass 2: Render video with interpolated crop positions."""
    silent_path = out_path + ".silent.mp4"
    
    if not samples:
        log.warning("Samples kosong, langsung mengembalikan video fallback.")
        import shutil
        try:
            shutil.copy2(in_path, silent_path)
        except Exception as e:
            log.error("Failed to copy fallback video: %s", e)
        return silent_path
        
    cap = cv2.VideoCapture(in_path)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(silent_path, fourcc, fps, (crop_w, crop_h))
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
                
                # Cari bracketing sample secara maju amortized (O(1))
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
                    # NORMAL: lerp linear untuk mengejar target tanpa jeda perlambatan
                    dt = next_s.time - prev_s.time
                    alpha = (t - prev_s.time) / dt if dt > 0 else 0.0
                    
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
    separator.  Fix: convert backslashes to forward-slash, then escape colons and single quotes.
    """
    return path.replace("\\", "/").replace(":", "\\:").replace("'", r"\'")


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
    is_master: bool = False,
    subtitle_path: Optional[str] = None,
    fonts_dir: Optional[str] = None,
    face_detector: str = "yunet",
) -> str:
    """Two-pass smart crop using ground-truth camera segments and non-causal smoothing."""
    if is_master:
        silent_path = _render_master_letterbox(in_path, out_path, aspect_ratio)
    else:
        target_ratio = _ratio(aspect_ratio)
        
        # Load Face Detector model based on chosen type
        detector = _load_face_detector(face_detector)
        
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
        
        # Deteksi segmen kamera langsung pada potongan subclip (in_path) untuk kecepatan optimal
        camera_segments = _generate_camera_segments(in_path, detector, face_detector)
        
        # Pass 1: Analysis guided by camera segments
        samples = _analyze_video(in_path, detector, crop_w, crop_h, src_w, src_h, camera_segments, clip_start_offset=0.0, face_detector=face_detector)
        
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
        
        loop = getattr(store, "loop", None)
        
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(
                store.set_progress(task_id, pct, "RENDER", msg), loop
            )
        else:
            print(f"[render progress] Task {task_id}: {pct:.1f}% - {msg}", flush=True)
            try:
                if not getattr(store, "_use_redis", False) and task_id in store._mem_tasks:
                    r = store._mem_tasks[task_id]
                    r.progress = float(pct)
                    r.stage = "RENDER"
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
) -> List[Dict]:
    clips_dir = str(STORAGE_DIR / task_id / "clips")
    os.makedirs(clips_dir, exist_ok=True)
    results = []
    
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
                                    if hasattr(store, "_mem_tasks") and task_id in store._mem_tasks:
                                        task_record = store._mem_tasks[task_id]
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
                subtitle_path=resolved_subtitle_path,
                fonts_dir=fonts_dir,
                face_detector=face_detector,
            )
            results.append({**h, "clip_url": f"/clips/{task_id}/short_{i:02d}.mp4"})
        except Exception as e:
            results.append({**h, "clip_url": None, "error": str(e)})
        finally:
            if os.path.exists(cut_path):
                os.remove(cut_path)
    _update_render_progress(task_id, len(highlights), len(highlights), "Semua klip selesai dirender")
    return results
