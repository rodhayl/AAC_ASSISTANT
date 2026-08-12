# BoardEditor Split and Bug Fixes Implementation Plan

> **Document status (2026-08-12): COMPLETED / HISTORICAL.** The split, synchronization fix, tests, and frontend gates described below are already integrated. Treat task steps and commit commands as provenance only; do not execute them as an outstanding checklist.
>
> **Current outcome:** the implementation is in `src/frontend/src/pages/BoardEditor.tsx` and focused components/hooks; the regression is `src/frontend/tests/BoardEditorStructure.test.tsx` (not `src/frontend/tests/BoardEditorStructure.test.tsx`). Use the current frontend gate in `README.md` for revalidation.

> **Historical workflow note:** the original plan referenced an external plan-execution workflow file, which is not part of the current repository. Do not follow that historical instruction; use the current validation commands in `README.md`.

**Goal:** Split the BoardEditor god page into focused collaboration, AI, and settings modules while preserving all editor behavior and removing the delayed store sync and eager status callback invocation.

**Architecture:** Keep BoardEditor responsible for board loading, local unsaved symbol overrides, drag/drop, and orchestration. Extract the WebSocket lifecycle into `useBoardCollab`, and extract the existing AI suggestion and board settings markup into presentational components that receive state and callbacks. Derive displayed symbols synchronously from the Zustand board snapshot plus a small override map, so unsaved drag/edit changes remain local without a timer-based store synchronization.

**Tech Stack:** React 19, TypeScript, Zustand, dnd-kit, Vitest, Testing Library.

---

### Task 1: Add regression coverage

**Files:**
- Create: `src/frontend/tests/BoardEditorStructure.test.tsx`

Write focused tests for the collaboration hook's encoded-token connection, local move broadcast, remote move callback, and the AI panel's inline unconfigured-provider error.

### Task 2: Extract collaboration lifecycle

**Files:**
- Create: `src/frontend/src/hooks/useBoardCollab.ts`
- Modify: `src/frontend/src/pages/BoardEditor.tsx`

Move WebSocket URL construction, connection setup/cleanup, remote `board_change` move handling, and local move sending into the hook. Keep the backend's raw WebSocket protocol and `1008` auth-close behavior unchanged.

### Task 3: Extract AI and settings UI

**Files:**
- Create: `src/frontend/src/components/board/AISuggestionPanel.tsx`
- Create: `src/frontend/src/components/board/BoardSettingsDialog.tsx`
- Modify: `src/frontend/src/pages/BoardEditor.tsx`

Move the existing markup without changing translation keys, controls, disabled states, or callbacks. Keep AI missing-settings feedback inline and retain primary-provider-only settings.

### Task 4: Replace delayed local synchronization

**Files:**
- Modify: `src/frontend/src/pages/BoardEditor.tsx`

Replace the `setTimeout(..., 0)` state copy with synchronous derivation from `currentBoard.symbols` and local overrides. Preserve unsaved drag/edit state until a successful refresh, and replace the immediately-invoked `useCallback` status computation with `useMemo`.

### Task 5: Validate and commit

Run `npm --prefix src/frontend run lint`, `npm --prefix src/frontend test -- --run`, and `npm --prefix src/frontend run build`; start the declared backend/frontend services and verify the editor grid, add/drag/save/remove/edit/settings/AI/clear flows and two-context collaboration with zero console errors. Commit with message `feat(frontend): split board editor and fix render sync`.
