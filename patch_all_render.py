with open('backend/app/engine/render.py', 'r') as f:
    content = f.read()

# Make _read_bgr_frame use retrieve instead of read
old_read = """def _read_bgr_frame(cap) -> Tuple[bool, Optional[np.ndarray]]:
    \"\"\"Read a frame and guarantee it has 3 channels (BGR), converting from grayscale if necessary.\"\"\"
    ret, frame = cap.read()"""
new_read = """def _read_bgr_frame(cap) -> Tuple[bool, Optional[np.ndarray]]:
    \"\"\"Read a frame and guarantee it has 3 channels (BGR), converting from grayscale if necessary.\"\"\"
    ret, frame = cap.retrieve()"""
content = content.replace(old_read, new_read)

# Fix _analyze_video loop
old_analyze_loop = """        while True:
            ret, frame = _read_bgr_frame(cap)
            if not ret or frame is None:
                break

            t = frame_idx / fps"""
new_analyze_loop = """        while True:
            ret = cap.grab()
            if not ret:
                break

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

# Fix _generate_camera_segments loop
old_camera_loop = """    while True:
        ret, frame = _read_bgr_frame(cap)
        if not ret or frame is None:
            break

        t = frame_idx / fps"""
new_camera_loop = """    while True:
        ret = cap.grab()
        if not ret:
            break

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

# Fix _render_frames
old_render_loop = """            while True:
                ret, frame = _read_bgr_frame(cap)"""
new_render_loop = """            while True:
                ret = cap.grab()
                if not ret:
                    break
                ret, frame = _read_bgr_frame(cap)"""
content = content.replace(old_render_loop, new_render_loop)

# Fix _render_master_letterbox
old_master_loop = """    while True:
        ret, frame = _read_bgr_frame(cap)"""
new_master_loop = """    while True:
        ret = cap.grab()
        if not ret:
            break
        ret, frame = _read_bgr_frame(cap)"""
content = content.replace(old_master_loop, new_master_loop)

with open('backend/app/engine/render.py', 'w') as f:
    f.write(content)
