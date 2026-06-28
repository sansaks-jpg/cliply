"""Camera segment analysis — scene cut detection & shot type classification.

Uses PySceneDetect for cut detection and face count analysis for
master/individual shot classification.
"""
import logging
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np

from scenedetect import detect, ContentDetector

from .face_detection import _detect_faces
from ..config import RENDER_CFG

log = logging.getLogger(__name__)


def _classify_shot(face_ratio: float) -> str:
    if face_ratio > RENDER_CFG.CLOSEUP_THRESHOLD:
        return "closeup"
    if face_ratio > RENDER_CFG.MEDIUM_THRESHOLD:
        return "medium"
    return "wide_cut"


def _generate_camera_segments(source_path: str, detector, face_detector: str) -> List[Dict[str, Any]]:
    """Analyze the full source video to detect scene cuts using PySceneDetect and classify camera shots.
    Returns a list of ground-truth camera segments.
    """
    from .render import _read_bgr_frame

    # 1. Jalankan deteksi scene cut menggunakan PySceneDetect
    try:
        scenes = detect(source_path, ContentDetector(threshold=27.0))
        # Cut terjadi pada frame index start dari setiap scene (kecuali scene pertama yang dimulai dari 0)
        cut_frames = {scene[0].get_frames() for scene in scenes if scene[0].get_frames() > 0}
    except Exception as e:
        log.error("Failed to detect scenes with PySceneDetect: %s. Falling back to empty cut list.", e)
        cut_frames = set()

    cap = cv2.VideoCapture(source_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    duration = total_frames / fps
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))

    # Gunakan 4 FPS untuk analisis segmentasi kamera (responsif & akurat)
    analysis_fps = 4.0
    interval = max(1, int(fps / analysis_fps))

    frame_idx = 0
    raw_frames = []

    while True:
        ret, frame = _read_bgr_frame(cap)
        if not ret or frame is None:
            break

        t = frame_idx / fps

        # Pemicu scene cut berdasarkan indeks frame dari PySceneDetect
        is_cut = frame_idx in cut_frames

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
