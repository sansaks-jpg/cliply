import re

with open('backend/app/engine/render.py', 'r') as f:
    content = f.read()

# remove double check
old_render = """                elif len(frame.shape) == 3 and frame.shape[2] == 1:
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                if not ret or frame is None:
                    break"""
new_render = """                elif len(frame.shape) == 3 and frame.shape[2] == 1:
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)"""

content = content.replace(old_render, new_render)

old_master = """        elif len(frame.shape) == 3 and frame.shape[2] == 1:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        if not ret or frame is None:
            break"""
new_master = """        elif len(frame.shape) == 3 and frame.shape[2] == 1:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)"""

content = content.replace(old_master, new_master)

with open('backend/app/engine/render.py', 'w') as f:
    f.write(content)
