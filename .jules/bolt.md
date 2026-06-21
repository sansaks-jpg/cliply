## 2024-06-21 - Optimize OpenCV frame sampling in `render.py`
**Learning:** When using `cv2.VideoCapture` to read frames at a fraction of the native framerate (e.g., analyzing at 5 FPS for a 30 FPS video), calling `cap.read()` unconditionally on every frame is highly inefficient. `cap.read()` both demultiplexes and decodes the frame.
**Action:** Use `cap.grab()` to advance the pointer quickly without decoding, and only use `cap.retrieve()` (or a wrapped decode call) on the frames that are actually selected for analysis. This drastically reduces CPU load in sparse sampling loops.
