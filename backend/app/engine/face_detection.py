"""Face detection — multi-model loader & unified detection interface.

Supports YuNet, MediaPipe BlazeFace, YOLOv8-Face, and SSD ResNet-10.
"""
import logging
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

log = logging.getLogger(__name__)

_DIR = os.path.dirname(os.path.abspath(__file__))


@dataclass
class SensitivityParams:
    """Runtime-adjusted detection parameters derived from sensitivity (0-100)."""
    confidence_threshold: float
    motion_weight: float
    size_weight: float
    switch_margin: float
    min_hold_samples: int
    min_shot_hold_samples: int
    max_missed_samples: int


def apply_sensitivity(sensitivity: int = 50, face_detector: str = "yunet") -> SensitivityParams:
    """Return SensitivityParams tuned per face detector model.

    ``sensitivity`` param is DEPRECATED — thresholds are auto-tuned per model.
    Kept for backward compatibility.
    """
    _PER_MODEL = {
        "yunet":        SensitivityParams(0.35, 0.60, 0.40, 0.12, 3, 3, 4),
        "mediapipe":    SensitivityParams(0.25, 0.65, 0.35, 0.15, 4, 4, 5),
        "yolov8-face":  SensitivityParams(0.40, 0.55, 0.45, 0.10, 3, 3, 3),
        "ssd":          SensitivityParams(0.50, 0.60, 0.40, 0.15, 4, 4, 4),
    }
    return _PER_MODEL.get(face_detector, _PER_MODEL["yunet"])


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
                          bbox_curr: Tuple[int, int, int, int],
                          bbox_prev: Optional[Tuple[int, int, int, int]]) -> float:
    """Compute motion energy in mouth region (lower 40% of face bbox) with motion compensation.

    Rejects global head motion by shifting prev ROI to align with current bbox center.
    """
    if frame_prev is None or bbox_prev is None:
        return 0.0

    x1_c, y1_c, x2_c, y2_c = bbox_curr
    x1_p, y1_p, x2_p, y2_p = bbox_prev

    # Motion compensation: compute bbox center shift
    cx_c = (x1_c + x2_c) // 2
    cy_c = (y1_c + y2_c) // 2
    cx_p = (x1_p + x2_p) // 2
    cy_p = (y1_p + y2_p) // 2
    dx = cx_c - cx_p
    dy = cy_c - cy_p

    # Apply shift to prev mouth ROI (lower 40% of face bbox)
    h_c = y2_c - y1_c
    my1_c = max(0, min(y1_c + int(h_c * 0.6), frame_curr.shape[0] - 1))
    my2_c = max(0, min(y2_c, frame_curr.shape[0]))
    mx1_c = max(0, min(x1_c, frame_curr.shape[1] - 1))
    mx2_c = max(0, min(x2_c, frame_curr.shape[1]))
    if my2_c <= my1_c or mx2_c <= mx1_c:
        return 0.0
    region_curr = _to_gray(frame_curr[my1_c:my2_c, mx1_c:mx2_c])
    region_curr = cv2.GaussianBlur(region_curr, (5, 5), 0)

    # Motion-compensated prev mouth ROI (shifted by dx, dy)
    h_p = y2_p - y1_p
    my1_p = max(0, min(y1_p + int(h_p * 0.6) + dy, frame_prev.shape[0] - 1))
    my2_p = max(0, min(y2_p + dy, frame_prev.shape[0]))
    mx1_p = max(0, min(x1_p + dx, frame_prev.shape[1] - 1))
    mx2_p = max(0, min(x2_p + dx, frame_prev.shape[1]))
    if my2_p <= my1_p or mx2_p <= mx1_p:
        return 0.0
    region_prev = _to_gray(frame_prev[my1_p:my2_p, mx1_p:mx2_p])
    if region_prev.shape != region_curr.shape:
        region_prev = cv2.resize(region_prev, (region_curr.shape[1], region_curr.shape[0]))
    region_prev = cv2.GaussianBlur(region_prev, (5, 5), 0)

    diff = cv2.absdiff(region_curr, region_prev)
    motion = float(np.mean(diff)) / 255.0

    # Normalize by face height ratio to make scale-invariant
    face_h_ratio = h_c / frame_curr.shape[0]
    if face_h_ratio > 0.01:
        motion = motion / face_h_ratio
    return min(1.0, motion)


def _to_gray(frame: np.ndarray) -> np.ndarray:
    """Safely convert a BGR frame to grayscale, or return as-is if already grayscale."""
    if len(frame.shape) == 2:
        return frame
    if len(frame.shape) == 3 and frame.shape[2] == 1:
        return frame[:, :, 0]
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)