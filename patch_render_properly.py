import re

with open('backend/app/engine/render.py', 'r') as f:
    content = f.read()

# Fix _analyze_video loop
old_analyze = """        while True:
            t = frame_idx / fps
            t_source = t + clip_start_offset"""

new_analyze = """        while True:
            ret = cap.grab()
            if not ret:
                break

            t = frame_idx / fps
            t_source = t + clip_start_offset"""

content = content.replace(old_analyze, new_analyze)

old_analyze_else = """            else:
                ret = cap.grab()
                if not ret:
                    break

            frame_idx += 1"""

new_analyze_else = """            frame_idx += 1"""

content = content.replace(old_analyze_else, new_analyze_else)

# Fix _generate_camera_segments loop
old_camera = """    while True:
        t = frame_idx / fps

        # Pemicu scene cut berdasarkan indeks frame dari PySceneDetect"""

new_camera = """    while True:
        ret = cap.grab()
        if not ret:
            break

        t = frame_idx / fps

        # Pemicu scene cut berdasarkan indeks frame dari PySceneDetect"""

content = content.replace(old_camera, new_camera)

old_camera_else = """        else:
            ret = cap.grab()
            if not ret:
                break

        frame_idx += 1"""

new_camera_else = """        frame_idx += 1"""

content = content.replace(old_camera_else, new_camera_else)

with open('backend/app/engine/render.py', 'w') as f:
    f.write(content)
