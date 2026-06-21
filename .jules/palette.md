## 2024-06-21 - Accessible Interactive Cards (Stretched Link Pattern)
**Learning:** Using `onClick` and `role="button"` on a `div` creates an inaccessible card with nested interactive element issues. The "Stretched Link" pattern is superior.
**Action:** Next time, wrap the main card title in a `<Link>` with `before:absolute before:inset-0`, make the parent card `relative`, and set other interactive elements (like a delete button) to `relative z-10`. Use `focus-within` on the parent to show the focus ring.
