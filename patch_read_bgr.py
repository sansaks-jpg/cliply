with open('backend/app/engine/render.py', 'r') as f:
    content = f.read()

old_read = """def _read_bgr_frame(cap) -> Tuple[bool, Optional[np.ndarray]]:
    \"\"\"Read a frame and guarantee it has 3 channels (BGR), converting from grayscale if necessary.\"\"\"
    ret, frame = cap.read()
    if not ret or frame is None:
        return False, None
    if len(frame.shape) == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    elif len(frame.shape) == 3 and frame.shape[2] == 1:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    return True, frame"""

new_read = """def _read_bgr_frame(cap) -> Tuple[bool, Optional[np.ndarray]]:
    \"\"\"Read a frame and guarantee it has 3 channels (BGR), converting from grayscale if necessary.\"\"\"
    ret, frame = cap.retrieve()
    if not ret or frame is None:
        return False, None
    if len(frame.shape) == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    elif len(frame.shape) == 3 and frame.shape[2] == 1:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    return True, frame"""

content = content.replace(old_read, new_read)

with open('backend/app/engine/render.py', 'w') as f:
    f.write(content)
