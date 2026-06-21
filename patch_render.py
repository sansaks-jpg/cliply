import re

with open('backend/app/engine/render.py', 'r') as f:
    content = f.read()

# Replace in _analyze_video
old_analyze_loop = """        while True:
            ret, frame = _read_bgr_frame(cap)
            if not ret or frame is None:
                break

            t = frame_idx / fps"""

new_analyze_loop = """        while True:
            t = frame_idx / fps"""

content = content.replace(old_analyze_loop, new_analyze_loop)

old_analyze_sample = """            if should_sample:
                last_sample_frame_idx = frame_idx"""

new_analyze_sample = """            if should_sample:
                ret, frame = _read_bgr_frame(cap)
                if not ret or frame is None:
                    break
                last_sample_frame_idx = frame_idx"""

content = content.replace(old_analyze_sample, new_analyze_sample)

old_analyze_end = """                # Simpan frame sampel saat ini sebagai histori sampel berikutnya
                frame_prev_sample = frame.copy() if frame is not None else None

            frame_idx += 1"""

new_analyze_end = """                # Simpan frame sampel saat ini sebagai histori sampel berikutnya
                frame_prev_sample = frame.copy() if frame is not None else None
            else:
                ret = cap.grab()
                if not ret:
                    break

            frame_idx += 1"""

content = content.replace(old_analyze_end, new_analyze_end)

# Replace in _generate_camera_segments
old_camera_loop = """    while True:
        ret, frame = _read_bgr_frame(cap)
        if not ret or frame is None:
            break

        t = frame_idx / fps"""

new_camera_loop = """    while True:
        t = frame_idx / fps"""

content = content.replace(old_camera_loop, new_camera_loop)

old_camera_sample = """        if frame_idx % interval == 0 or is_cut:
            # FIX 1: Turunkan threshold jadi 0.25 khusus buat ngecek scene"""

new_camera_sample = """        if frame_idx % interval == 0 or is_cut:
            ret, frame = _read_bgr_frame(cap)
            if not ret or frame is None:
                break
            # FIX 1: Turunkan threshold jadi 0.25 khusus buat ngecek scene"""

content = content.replace(old_camera_sample, new_camera_sample)

old_camera_end = """            })

        frame_idx += 1"""

new_camera_end = """            })
        else:
            ret = cap.grab()
            if not ret:
                break

        frame_idx += 1"""

content = content.replace(old_camera_end, new_camera_end)


with open('backend/app/engine/render.py', 'w') as f:
    f.write(content)
