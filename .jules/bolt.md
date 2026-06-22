## 2024-06-21 - Optimize OpenCV frame sampling in `render.py`
**Learning:** When using `cv2.VideoCapture` to read frames at a fraction of the native framerate (e.g., analyzing at 5 FPS for a 30 FPS video), calling `cap.read()` unconditionally on every frame is highly inefficient. `cap.read()` both demultiplexes and decodes the frame.
**Action:** Use `cap.grab()` to advance the pointer quickly without decoding, and only use `cap.retrieve()` (or a wrapped decode call) on the frames that are actually selected for analysis. This drastically reduces CPU load in sparse sampling loops.
## 2024-06-25 - Prevent inline large object reallocation in React component
**Learning:** Large objects like style definition maps and pure functions can cause unnecessary overhead if defined inline inside a React component (like `Home` in Next.js), especially when the component relies on an interval (`setInterval`) that forces re-renders.
**Action:** Always hoist large configuration objects and pure functions that don't depend on component props or state to the top level of the module (outside the component function) to reduce GC pressure and allocation overhead.
