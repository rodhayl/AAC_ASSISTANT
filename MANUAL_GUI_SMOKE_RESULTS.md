# GUI / Frontend Validation Results

**Date**: 2026-08-28 (updated 2026-08-29: full E2E results + final spec hardening)

## Full Playwright E2E suite (real browser, production build, real backend)

- **243 tests — all passing** (`npx playwright test` per the documented CI flow in
  `docs/test_scenarios/execute_all_scenarios.md`: isolated `.ci-e2e-data` DB,
  `TESTING=1` seeded server on :8086, production build served by the backend)

### Verification sequence (final)

| Step | Result |
|---|---|
| Initial full suite | 241 passed / 8 failed (all 8 root-caused below) |
| Targeted re-run of the 4 affected specs after root-cause fixes | 12 passed (26.5s) |
| Full suite after the voice-mode fix | 243 passed (8.4m) |
| Targeted re-run after final locator hardening | 10 passed (24.7s) |
| Final full suite (clean tree) | 243 passed (8.4m / 9.0m / 8.4m) |

### E2E failures found and fixed during this pass

1. **`advanced.spec.ts` — notifications (2 tests)**: `getByLabel(/notifications/i)`
   resolved to 2 elements — the Navbar bell button and sonner's Toaster live
   region (default `containerAriaLabel` is "Notifications alt+T"). Root-cause fix:
   `AppToaster.tsx` now passes `containerAriaLabel="Alerts"` (post-fix page
   snapshots show the region as "Alerts alt+T"), and the spec uses the unambiguous
   `getByRole('button', { name: /notifications|notificaciones/i })`.
2. **`communication.spec.ts` — chip removal**: the chip locator used the Tailwind
   class `div.flex-shrink-0` with an anchored `^label$` regex, but the chip's text
   also carries the image-fallback copy ("Image unavailable horse"). Root-cause
   fix: `SentenceStrip.tsx` chips now carry `data-testid="sentence-chip"`; the
   spec locates via
   `.locator('[data-testid="sentence-chip"]', { hasText: <label> })` — substring
   match, no anchored regex, no Tailwind-class dependency.
3. **`contrast-interactive.spec.ts` — symbol-search step (4 tests)**: the spec
   clicked a "Add symbol" button, which only exists on empty cells; board 1 is
   fully populated (12 symbols / 3x4 grid). The step is now conditional — it
   audits whatever surface is present.
4. **`llm-integration.spec.ts` — Ask AI**: the mocked `/api/learning/start`
   response omitted `board_id`, so Communication's board-mismatch effect
   (`currentSession.board_id !== activeBoardId`) called `resetSession()` and
   dropped the in-flight answer before it could render. Mock now returns
   `board_id: 1`, matching the opened board.
5. **`voice-mode.spec.ts` — persistence (2 tests)**: `#pref-voice-mode-enabled` is
   Base UI Switch's hidden mirror input (`aria-hidden`, `tabindex=-1`, 1px
   clipped); Playwright's `check()/uncheck()` cannot drive it —
   `locator.uncheck: Clicking the checkbox did not change its state`. The spec now
   clicks the visible `getByRole('switch', { name: /voice mode|modo de voz/i })`
   control and asserts the persisted value through the mirror input
   (`toBeChecked()` before save and after reload).

## Full non-E2E frontend suite

- **80 test files, 649 tests — all passing** (`npm test -- --run`)
- Full backend suite: **924 tests — all passing** (`uv run pytest`, 3m13s)
- TypeScript: pass (`npm run typecheck`)
- ESLint: pass (`npm run lint`)
- Production build: pass (`npm run build`), bundle within budget
- `git diff --check`: clean

## Fixes applied during this pass

1. `tests/Boards.test.tsx` — the loading-spinner test ended before the mount fetch
   resolved, emitting `act(...)` warnings. Added `await waitFor(...)` to flush the
   async update inside the test.
2. `tests/VoiceTab.test.tsx` — the warm-up indicator tests updated the zustand
   store in `finally` blocks outside `act`. Wrapped in `act()` and flushed with
   `waitFor`.
3. `tests/learningSymbolAudio.test.tsx` — the voice-toggle test wrapped
   `screen.findByTitle()` inside `await act(...)` (a pattern React 19 rejects).
   Simplified to the suite-standard pattern.
4. `vitest.setup.ts` — added `globalThis.IS_REACT_ACT_ENVIRONMENT = true`, the
   documented React 19 requirement, eliminating the whole class of
   "environment is not configured to support act" noise.

## Coverage by area

- Auth: Login, Register, Setup, authStore, ResetPasswordModal, SecurityTab
- Boards: Boards, BoardEditor, BoardEditorStructure, BoardEditorToolbar,
  BoardsAssignedBoards, boardStoreCrud, boardStoreLoading
- Communication: Communication, CommunicationChat, CommunicationFeatures,
  CommunicationGrid, CommunicationToolbar, CommunicationBoardSearch,
  SentenceStrip, Smartbar, communicationSessionToast
- Learning: LearningChatPanel, LearningHeader, LearningInputRow, LearningModesTab,
  LearningQuestionCard, SessionSummaryModal, learningSymbolAudio, learningTopics
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

## Backend smoke (same pass, no Playwright)

- `/api/health`: 200 · `/ready`: 503 during warmup → 200 with `ready=true`
  (4/4 providers) after polling · `/`: 200 · `/docs`: 200 · `/openapi.json`: 200
- Invalid login: 401 · `admin1` login: 200 (token issued)
- LM Studio model-list route unauthenticated: 401
- `GET /api/analytics/log`: 404 (correct — the compatibility operation is `POST`)

## Limitation

The jsdom section above is component/store coverage; real-browser interaction is
covered by the Playwright E2E suite at the top of this document (243 specs
against the production build and a seeded backend). Still outside the evidence
produced here: subjective visual/aesthetic review, screen-reader and
switch/eye-gaze assistive-tech UX, real audio-hardware behaviour, and clinical
appropriateness — these require human review (see
`docs/test_scenarios/execute_all_scenarios.md`, "Evidence and safety
requirements").
