with open('backend/app/engine/render.py', 'r') as f:
    content = f.read()

# For _read_bgr_frame we have to change retrieve to retrieve(0) or something? Wait, cap.retrieve() is fine.
# We don't want to use grab() and retrieve() for _render_frames and _render_master_letterbox because we decode *every* frame there.
# Let's revert _render_frames and _render_master_letterbox to use read()

old_render_loop = """            while True:
                ret = cap.grab()
                if not ret:
                    break
                ret, frame = _read_bgr_frame(cap)"""
new_render_loop = """            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break
                if len(frame.shape) == 2:
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                elif len(frame.shape) == 3 and frame.shape[2] == 1:
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)"""
content = content.replace(old_render_loop, new_render_loop)

old_master_loop = """    while True:
        ret = cap.grab()
        if not ret:
            break
        ret, frame = _read_bgr_frame(cap)"""
new_master_loop = """    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            break
        if len(frame.shape) == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        elif len(frame.shape) == 3 and frame.shape[2] == 1:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)"""
content = content.replace(old_master_loop, new_master_loop)

with open('backend/app/engine/render.py', 'w') as f:
    f.write(content)
