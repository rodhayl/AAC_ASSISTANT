# Communication Memoization Design

> **Document status (2026-08-12): COMPLETED / HISTORICAL.** The memoized grid, render-count regression coverage, and frontend validation described below are already integrated. This file records the design rationale; it is not an active implementation checklist.
>
> **Current outcome:** `src/frontend/src/components/board/CommunicationGrid.tsx` owns the memoized grid and `src/frontend/src/pages/Communication.tsx` owns orchestration. The regression is in `src/frontend/tests/CommunicationGrid.test.tsx`; current frontend validation is recorded in `README.md`.

**Goal:** Prevent Communication page state updates from rerendering unchanged board symbol cards while preserving every existing communication flow.

**Design:** Keep `SymbolCard` as a memoized leaf with its existing `BoardSymbol` and callback API. Extract the active-board grid into a `CommunicationGrid` component that derives positioned cells with `useMemo`; the parent supplies stable dimensions, symbols, and `handleSymbolClick`. Keep the sentence strip and other overlays behaviorally unchanged, but pass named callbacks from `Communication` rather than creating per-render inline handlers where they are memoized children.

**Verification:** Add a Testing Library/Vitest render-spy test around `CommunicationGrid`: rerender with a changed search value and the same symbol objects, then assert unchanged cards render once. Run frontend lint, all Vitest tests, and the production build, followed by the required browser smoke of the communication board.
