## 2024-06-28 - React State Isolation for Animation
**Learning:** Having an animation `setInterval` update state directly inside a large parent component (like `Home` containing forms and long lists) causes massive performance degradation due to the entire component tree unnecessarily re-rendering twice a second.
**Action:** Always isolate frequent, animation-related state updates into their own dedicated leaf components (e.g., `AnimatedSubtitlePreview`). This restricts React's reconciliation process to only the small part of the DOM that actually changes.
