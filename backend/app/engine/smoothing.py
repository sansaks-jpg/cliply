"""Kalman-filter smoothing and sample data structures for face tracking.

Provides jitter-free crop position smoothing within scene boundaries.
"""
from dataclasses import dataclass
from typing import List, Tuple

import cv2
import numpy as np


class FaceKalmanTracker:
    """8-state constant-velocity Kalman filter for smooth face tracking."""
    def __init__(self):
        self.kf = cv2.KalmanFilter(8, 4, 0, cv2.CV_32F)
        dt = 1.0
        self.kf.transitionMatrix = np.array([
            [1,0,0,0,dt,0,0,0],
            [0,1,0,0,0,dt,0,0],
            [0,0,1,0,0,0,dt,0],
            [0,0,0,1,0,0,0,dt],
            [0,0,0,0,1,0,0,0],
            [0,0,0,0,0,1,0,0],
            [0,0,0,0,0,0,1,0],
            [0,0,0,0,0,0,0,1],
        ], dtype=np.float32)
        self.kf.measurementMatrix = np.eye(4, 8, dtype=np.float32)
        cv2.setIdentity(self.kf.processNoiseCov, 1e-4)
        cv2.setIdentity(self.kf.measurementNoiseCov, 1e-1)
        cv2.setIdentity(self.kf.errorCovPost, 1.0)

    def predict(self):
        return self.kf.predict()

    def update(self, bbox):
        """bbox = [cx, cy, w, h]"""
        meas = np.array([bbox[0], bbox[1], bbox[2], bbox[3]], dtype=np.float32).reshape(4, 1)
        return self.kf.correct(meas)


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


def _ease_in_out(t: float) -> float:
    """Ease-in-out interpolation (smooth start/end)."""
    return t * t * (3.0 - 2.0 * t)


def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation."""
    return a + (b - a) * t


def _apply_smoothing_non_causal(samples: List[SampleFrame], src_w: int, src_h: int) -> List[Tuple[int, int, float, str, bool]]:
    """Apply Kalman-filter smoothing within scene boundaries for jitter-free tracking."""
    if not samples:
        return []

    # Group samples into scenes separated by cuts
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

    result = []
    for scene in scenes:
        if not scene:
            continue
        # wide_cut (master) segments: no smoothing, pass through
        if all(s.shot_type == "wide_cut" for s in scene):
            for s in scene:
                result.append((s.raw_cx, s.raw_cy, s.face_ratio, s.shot_type, s.is_cut))
            continue

        # One Kalman tracker per scene, reset on first non-wide frame
        kalman = FaceKalmanTracker()
        first = True
        for s in scene:
            if s.shot_type == "wide_cut":
                result.append((s.raw_cx, s.raw_cy, s.face_ratio, s.shot_type, s.is_cut))
                first = True  # Reset Kalman after wide_cut to prevent state leak
                continue
            if first:
                kalman.update([s.raw_cx, s.raw_cy, int(s.face_ratio * src_w), int(s.face_ratio * src_h)])
                smooth_cx, smooth_cy = s.raw_cx, s.raw_cy
                first = False
            else:
                # Predict then correct
                kalman.predict()
                corrected = kalman.update([s.raw_cx, s.raw_cy, int(s.face_ratio * src_w), int(s.face_ratio * src_h)])
                smooth_cx = int(corrected[0][0])
                smooth_cy = int(corrected[1][0])

            result.append((smooth_cx, smooth_cy, s.face_ratio, s.shot_type, s.is_cut))

    return result
