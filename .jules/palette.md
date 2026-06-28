## 2024-06-21 - Accessible Interactive Cards (Stretched Link Pattern)
**Learning:** Using `onClick` and `role="button"` on a `div` creates an inaccessible card with nested interactive element issues. The "Stretched Link" pattern is superior.
**Action:** Next time, wrap the main card title in a `<Link>` with `before:absolute before:inset-0`, make the parent card `relative`, and set other interactive elements (like a delete button) to `relative z-10`. Use `focus-within` on the parent to show the focus ring.
## 2024-05-30 - Localized Tooltips for Icon Buttons
**Learning:** Icon-only buttons often lack proper accessibility and context. The `title` attribute is helpful but unstyled, while the app uses Indonesian as its primary language. Applying a `Tooltip` component improves visual consistency, and localizing the `aria-label` (e.g. from "Delete history" to "Hapus riwayat") ensures a coherent experience for screen reader users.
**Action:** Always wrap icon-only buttons in `Tooltip` components from the design system and ensure `aria-label` and `TooltipContent` are localized to Indonesian to match the app's language context.
