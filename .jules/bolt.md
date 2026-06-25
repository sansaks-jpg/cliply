## 2024-05-18 - [Extract State for Animated Previews]
**Learning:** Frequent interval updates tied to high-level state (like a subtitle animation tick inside a main page component) cause unnecessary full-page re-renders. This is an anti-pattern in React because it forces layout calculation and DOM reconciliation for unrelated sibling elements.
**Action:** Always encapsulate rapidly changing UI state (like `setInterval`-based animation frames) into small, isolated child components so only the exact DOM nodes needing the update are re-rendered.
