## 2026-06-23 - [Memoization of Heavy UI Style Computation]
**Learning:** React re-renders component on every state change (e.g., animation tick ), causing functions like `makeTextShadow` (which contains nested loops) and `getDynamicPreviewStyles` to be recalculated constantly on the main thread, wasting CPU.
**Action:** Extract computationally expensive operations from the render path and wrap them in `useMemo` keyed to the specific state they depend on (e.g., `subtitleStyle`).
## 2026-06-23 - [Memoization of Heavy UI Style Computation]
**Learning:** React re-renders component on every state change (e.g., animation tick wordProgressIndex), causing functions like makeTextShadow (which contains nested loops) and getDynamicPreviewStyles to be recalculated constantly on the main thread, wasting CPU.
**Action:** Extract computationally expensive operations from the render path and wrap them in useMemo keyed to the specific state they depend on (e.g., subtitleStyle).
