## 2024-06-21 - Accessible Interactive Cards (Stretched Link Pattern)
**Learning:** Using `onClick` and `role="button"` on a `div` creates an inaccessible card with nested interactive element issues. The "Stretched Link" pattern is superior.
**Action:** Next time, wrap the main card title in a `<Link>` with `before:absolute before:inset-0`, make the parent card `relative`, and set other interactive elements (like a delete button) to `relative z-10`. Use `focus-within` on the parent to show the focus ring.
## 2024-05-18 - [Accessibility: ARIA Labels for Icon Buttons & Interactive Toggles]
**Learning:** Icon-only buttons (like the mute/unmute button in the vertical player) and styled interactive elements (like the subtitle style buttons) lacked proper ARIA attributes, making them inaccessible to screen readers.
**Action:** Added `aria-label` to icon-only buttons to convey their action, taking state into account (e.g., mute vs. unmute). Added `aria-pressed` and `aria-label` to custom toggle buttons to communicate their state and purpose.
