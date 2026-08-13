# Communication Memoization Design

**Goal:** Prevent Communication page state updates from rerendering unchanged board symbol cards while preserving every existing communication flow.

**Design:** Keep `SymbolCard` as a memoized leaf with its existing `BoardSymbol` and callback API. Extract the active-board grid into a `CommunicationGrid` component that derives positioned cells with `useMemo`; the parent supplies stable dimensions, symbols, and `handleSymbolClick`. Keep the sentence strip and other overlays behaviorally unchanged, but pass named callbacks from `Communication` rather than creating per-render inline handlers where they are memoized children.

**Verification:** Add a Testing Library/Vitest render-spy test around `CommunicationGrid`: rerender with a changed search value and the same symbol objects, then assert unchanged cards render once. Run frontend lint, all Vitest tests, and the production build, followed by the required browser smoke of the communication board.
