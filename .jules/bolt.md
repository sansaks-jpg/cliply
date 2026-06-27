## 2025-02-23 - [O(N*M) Word-to-Segment Mapping Bottleneck]
**Learning:** Found a performance bottleneck in `backend/app/engine/transcriber.py` where mapping transcribed words to segments was O(N*M) via a nested loop. This degrades exponentially for longer videos with many segments.
**Action:** Used `bisect` library and binary search for O(N log M) finding segment candidates based on timestamps.
