# Exact source scope

56 unchanged historical files. Paths below are relative to `historical/frontend/`; original prefix was `src/frontend/`.

- `src/components/board/AISuggestionPanel.tsx`
- `src/components/board/BoardEditorGrid.tsx`
- `src/components/board/BoardEditorToolbar.tsx`
- `src/components/board/BoardSettingsDialog.tsx`
- `src/components/board/CommunicationGrid.tsx`
- `src/components/board/CommunicationToolbar.tsx`
- `src/components/board/DraggableSymbol.tsx`
- `src/components/board/DroppableCell.tsx`
- `src/components/board/KeyboardOverlay.tsx`
- `src/components/board/SentenceStrip.tsx`
- `src/components/board/SymbolCard.tsx`
- `src/components/common/SymbolImage.tsx`
- `src/components/ui/AccessibleButton.tsx`
- `src/components/ui/AppToaster.tsx`
- `src/components/ui/ConfirmDialog.tsx`
- `src/components/ui/FormLabel.tsx`
- `src/components/ui/LoadingState.tsx`
- `src/components/ui/SectionTitle.tsx`
- `src/components/ui/StatusMessage.tsx`
- `src/components/ui/Toggle.tsx`
- `src/components/ui/alert-dialog.tsx`
- `src/components/ui/button.tsx`
- `src/components/ui/dialog.tsx`
- `src/components/ui/icon-button.tsx`
- `src/components/ui/select.tsx`
- `src/components/ui/switch.tsx`
- `src/components/ui/tooltip.tsx`
- `src/hooks/useAccessibleInteraction.ts`
- `src/hooks/useAutoHide.ts`
- `src/hooks/useBoardEditorSymbols.ts`
- `src/index.css`
- `src/lib/boardGrid.ts`
- `src/lib/download.ts`
- `src/lib/format.ts`
- `src/lib/gloss.ts`
- `src/lib/symbolCategoryStyle.ts`
- `src/lib/symbols.ts`
- `src/lib/utils.ts`
- `src/locales/en/common.json`
- `src/locales/en/pages/boards.json`
- `src/locales/es/common.json`
- `src/locales/es/pages/boards.json`
- `src/pages/boardEditorUtils.ts`
- `src/types/index.ts`
- `tests/BoardEditorToolbar.test.tsx`
- `tests/CommunicationGrid.test.tsx`
- `tests/CommunicationToolbar.test.tsx`
- `tests/ConfirmDialog.test.tsx`
- `tests/IconButton.test.tsx`
- `tests/SentenceStrip.test.tsx`
- `tests/SymbolCard.test.tsx`
- `tests/download.test.ts`
- `tests/format.test.ts`
- `tests/styleTokens.test.ts`
- `tests/symbols.test.ts`
- `tests/useAccessibleInteraction.test.tsx`

## References to omitted infrastructure

These unresolved imports are intentional exclusions, not a passing build. Type-only references may also appear here. Original component tests that depend on them are retained as source evidence, not represented as executed.

- `../../hooks/useBoardCollab (from src/components/board/AISuggestionPanel.tsx)`
- `../../lib/tts (from src/components/board/DraggableSymbol.tsx)`
- `../../store/authStore (from src/components/board/DraggableSymbol.tsx)`
- `../../store/themeStore (from src/components/ui/AppToaster.tsx)`
- `../config (from src/lib/utils.ts)`
- `../i18n/index (from src/lib/format.ts)`
- `../src/i18n/index (from tests/format.test.ts)`
- `../store/authStore (from src/hooks/useAccessibleInteraction.ts)`
- `./useBoardCollab (from src/hooks/useBoardEditorSymbols.ts)`
