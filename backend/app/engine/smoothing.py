"""Sample data structures and interpolation utilities for face tracking."""
from dataclasses import dataclass
from typing import List, Tuple


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
    """Return raw sample values for two-pass interpolation in render stage."""
    if not samples:
        return []
    result = []
    for s in samples:
        result.append((s.raw_cx, s.raw_cy, s.face_ratio, s.shot_type, s.is_cut))
    return result
