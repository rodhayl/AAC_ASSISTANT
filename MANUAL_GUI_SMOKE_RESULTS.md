# GUI / Frontend Validation Results

**Date**: 2026-08-28 (updated 2026-08-29 with full E2E results)

## Full Playwright E2E suite (real browser, production build, real backend)

- **243 tests — all passing** (`npx playwright test` per the documented CI flow in
  `docs/test_scenarios/execute_all_scenarios.md`: isolated `.ci-e2e-data` DB,
  `TESTING=1` seeded server on :8086, production build served by the backend)

### E2E failures found and fixed during this pass

1. **`advanced.spec.ts` — notifications (2 tests)**: `getByLabel(/notifications/i)`
   resolved to 2 elements — the Navbar bell button and sonner's Toaster live
   region (default `containerAriaLabel` is "Notifications alt+T"). Root-cause fix:
   `AppToaster.tsx` now passes `containerAriaLabel="Alerts"`; spec hardened to
   `getByRole('button', ...)`.
2. **`communication.spec.ts` — chip removal**: the chip locator used the Tailwind
   class `div.flex-shrink-0` with an anchored `^label$` regex, but the chip's text
   also carries the image-fallback copy ("Image unavailable horse"). Root-cause
   fix: `SentenceStrip.tsx` chips now carry `data-testid="sentence-chip"`; the spec
   locates by testid with substring match.
3. **`contrast-interactive.spec.ts` — symbol-search step (4 tests)**: the spec
   clicked a "Add symbol" button, which only exists on empty cells; board 1 is
   fully populated (12 symbols / 3x4 grid). The step is now conditional — it
   audits whatever surface is present.
4. **`llm-integration.spec.ts` — Ask AI**: the mocked `/api/learning/start`
   response omitted `board_id`, so Communication's board-mismatch effect called
   `resetSession()` and dropped the in-flight answer. Mock now returns
   `board_id: 1`.
5. **`voice-mode.spec.ts` — persistence (2 tests)**: `#pref-voice-mode-enabled` is
   Base UI Switch's hidden mirror input (`aria-hidden`, 1px clipped); Playwright's
   `check()/uncheck()` cannot drive it. The spec now clicks the visible
   `[role="switch"]` control and asserts through the mirror input.

## Full non-E2E frontend suite

- **80 test files, 649 tests — all passing** (`npm test -- --run`)
- TypeScript: pass (`npm run typecheck`)
- ESLint: pass (`npm run lint`)
- Production build: pass (`npm run build`), bundle within budget
- `git diff --check`: clean

## Fixes applied during this pass

1. `tests/Boards.test.tsx` — the loading-spinner test ended before the mount fetch
   resolved, emitting `act(...)` warnings. Added `await waitFor(...)` to flush the
   async update inside the test.
2. `tests/VoiceTab.test.tsx` — warm-up indicator tests set zustand state in
   `finally` blocks outside `act`, and the "no warm-up" test ended before the
   mount fetch resolved. Wrapped store updates in `act()` and flushed the fetch
   with `waitFor`.
3. `tests/learningSymbolAudio.test.tsx` — the voice-toggle test wrapped
   `screen.findByTitle()` inside `await act(...)`, which React 19 reported as an
   unconfigured act environment. Simplified to the suite-standard
   `fireEvent.click(await findBy...)` pattern (RTL already wraps `fireEvent` in
   `act`).
4. `vitest.setup.ts` — set `globalThis.IS_REACT_ACT_ENVIRONMENT = true`, the
   documented React 19 requirement for act-wrapped updates, to eliminate the
   class of "environment is not configured to support act" noise.

## Coverage by area

- Auth: Login, Register, Setup, authStore, ResetPasswordModal, SecurityTab
- Boards: Boards, BoardEditor, BoardEditorStructure, BoardEditorToolbar,
  BoardsAssignedBoards, boardStoreCrud, boardStoreLoading
- Communication: Communication, CommunicationChat, CommunicationFeatures,
  CommunicationGrid, CommunicationToolbar, CommunicationBoardSearch,
  SentenceStrip, Smartbar, communicationSessionToast
- Learning: LearningChatPanel, LearningHeader, LearningInputRow, LearningModesTab,
  LearningModeKey, LearningQuestionCard, SessionSummaryModal, learningQuestionFlow,
  learningHistoryRefresh, learningSymbolAudio, learningTopics
- Students/teachers: Students, UserManagement, usePreferences
- Symbols: Symbols, SymbolCard, SymbolEditorDialog, SymbolSearchModal, SymbolHunt,
  useSymbolHunt, symbols, SymbolGrid
- Achievements: Achievements
- Settings: AppearanceTab, ProfileTab, SecurityTab, VoiceTab, AiProviderFields,
  AiProviderTab, DataManagementTab, SettingsManager, settingsStore,
  settingsI18n, localeStore, ttsStore
- Stores/utils: api, ws, offlineStore, notificationsStore, dashboardStore,
  toastStore, themeStore, authStore, download, format, lazyWithRetry, prodGuard,
  reducedMotion, normalizeUILanguage, _i18n_check, i18n, useAccessibleInteraction,
  useVoiceRecorder, NotificationsPanel, OfflineConflictsPanel, ConfirmDialog,
  IconButton, EndToEndOptions, NotFound, Dashboard

## Limitation

This is jsdom component/store coverage, not interactive browser validation. No
interactive Chrome/DevTools control is available in this session, so click-level
visual layout, real rendering, keyboard traversal in a real browser, and console
state during live interaction remain outside the evidence produced here.
