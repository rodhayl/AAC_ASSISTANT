# Historical source provenance

Selected commit: `bad3692bc31f0ab709621a37585c30b9acaed681` (2026-08-31 21:07:38 UTC).

All 56 files under `historical/frontend/` were verified byte-identical against their original Git blob IDs on 30 October 2026. Files have been selected, not refactored or repaired. The original MIT LICENSE is preserved. Root docs/package metadata, ignore rules, CLI and its Node tests are new supporting material. No later private product implementation or Git history is included.

## Verification scope

Node.js v24.22.1: the synthetic CLI completed and the six targeted Node tests passed. Historical React/Vitest tests are source only: no frontend build, static typecheck, browser run, original Vitest suite or complete product acceptance is claimed.

## Original Git blob IDs

| Path (relative to historical/frontend) | Git blob ID |
| --- | --- |
| `src/components/board/AISuggestionPanel.tsx` | `04c2081e4d8ed0ae1e546d16af6f9eee9cef6ea1` |
| `src/components/board/BoardEditorGrid.tsx` | `544553f98bfd9ee12e6955370db1e6a298d2bce3` |
| `src/components/board/BoardEditorToolbar.tsx` | `eaa7141bd6f0be542e2993f7f5b5f92628f94646` |
| `src/components/board/BoardSettingsDialog.tsx` | `6ccf639a305f1c608934fdd9bd8060e936201c90` |
| `src/components/board/CommunicationGrid.tsx` | `048ee810bcab3c36206b48128be024666c9dc022` |
| `src/components/board/CommunicationToolbar.tsx` | `7e8dfd7921b8c9abb8357df7c80ebb455e512eca` |
| `src/components/board/DraggableSymbol.tsx` | `916e5520a8ca22234e2474fb7b78123ccb4a4d28` |
| `src/components/board/DroppableCell.tsx` | `bf89e265cab364c65fc31994864c49da70897686` |
| `src/components/board/KeyboardOverlay.tsx` | `a4535b6682b4594ce050d4c1384df775e0c3458e` |
| `src/components/board/SentenceStrip.tsx` | `20eac0ecd329c9460af57f40a27878e4fd67d2c2` |
| `src/components/board/SymbolCard.tsx` | `6a55f52b489dab65092fdbf7474679e3543f9c18` |
| `src/components/common/SymbolImage.tsx` | `f62bcd632451dc62d2bc19a4e439e88ac2a81c04` |
| `src/components/ui/AccessibleButton.tsx` | `0acb34d7ae30681ba3005b97d98949ee79498fd3` |
| `src/components/ui/AppToaster.tsx` | `6ffaa628d868a9bfd1c8e7620c899041033060a9` |
| `src/components/ui/ConfirmDialog.tsx` | `eec5e305a22374de5033beec4c8e1f1958425034` |
| `src/components/ui/FormLabel.tsx` | `580b7c0c51e020fee4af7711e2f615b0c0674415` |
| `src/components/ui/LoadingState.tsx` | `bd54d41923cfbaf0a2eadf3670a9d5d17e7b0b40` |
| `src/components/ui/SectionTitle.tsx` | `d3a32823d3352dfbf99acb68d1f2ca253438bfac` |
| `src/components/ui/StatusMessage.tsx` | `58b3b41ca6aeaae379c82f4adf83060cb3f8807e` |
| `src/components/ui/Toggle.tsx` | `4b35fce9e6ad9fafa940c8089217c66147fa0eb4` |
| `src/components/ui/alert-dialog.tsx` | `05dce24f0babf893b03ff6561c9e1e4f11eae7e2` |
| `src/components/ui/button.tsx` | `f9bb0ff707476b00e3b95fec3d8bac46c04cb5ed` |
| `src/components/ui/dialog.tsx` | `ac58a26f1aea4bce4ca913c779ff7c9b1b59a58d` |
| `src/components/ui/icon-button.tsx` | `c2a9368aef633b3b363673b3ad14e0369862915a` |
| `src/components/ui/select.tsx` | `56a7734f983ae81cd8258eece3183fa1325df841` |
| `src/components/ui/switch.tsx` | `b8a452237f78b6e9f8a7d4a1a7f1da578d306e44` |
| `src/components/ui/tooltip.tsx` | `69e8a822c0e10629683093292a1b3b5de14ccb08` |
| `src/hooks/useAccessibleInteraction.ts` | `ffa4f7bd9920f27762edc5f1af74419b0b20dfce` |
| `src/hooks/useAutoHide.ts` | `c756e8783fb8cb747481444c3855c18015e2d2ba` |
| `src/hooks/useBoardEditorSymbols.ts` | `eb6f1c9f146c54cda1686a3deb2bda392c0fc8cf` |
| `src/index.css` | `a29f2b4f265b0573f496f2faa93b6ad9576ace6d` |
| `src/lib/boardGrid.ts` | `52b1f94440f6127fbf47a899cc603c35dda7827b` |
| `src/lib/download.ts` | `6a660eb09558ad69b76e6286ac1bb18f104a0f2b` |
| `src/lib/format.ts` | `0cfc8fd76b64bda0154a615310b21239ec6c4a71` |
| `src/lib/gloss.ts` | `8fe38ebb1784c53bac1b306c6e4f7700a3ae3bb2` |
| `src/lib/symbolCategoryStyle.ts` | `2f5ea8b2e783571c69726db7a29bdb0e871bccde` |
| `src/lib/symbols.ts` | `4fa6c7d7586345b954c79a43118787307537878c` |
| `src/lib/utils.ts` | `13654ca0d220776ac22ae33e4de5be0973976412` |
| `src/locales/en/common.json` | `29d09871bf044ade10bda0a4c97de41163bb6f36` |
| `src/locales/en/pages/boards.json` | `ef98876d863c6377befc4ac8424d87e53d6e5b9c` |
| `src/locales/es/common.json` | `ef721cece9958256d313cd798de6d4d7c88821c8` |
| `src/locales/es/pages/boards.json` | `9defc4609c81c415e2310f5eccfd22698469e6f9` |
| `src/pages/boardEditorUtils.ts` | `edcba0dbdb1ef7edb5f4357db5a30d929f45e6ac` |
| `src/types/index.ts` | `2410df9c69f53b99f3aa21c79504730da3fe1844` |
| `tests/BoardEditorToolbar.test.tsx` | `83f8040a9c7986d7c8d0769dbd0403c9f2f97c69` |
| `tests/CommunicationGrid.test.tsx` | `b4a1ad100fcc854793331e4e9b3a6698480dd8d9` |
| `tests/CommunicationToolbar.test.tsx` | `61d43e711c63feb88d706fb5fc21e0b8d0d9d26e` |
| `tests/ConfirmDialog.test.tsx` | `8adbca856df6c84e2b17078b506f816fb03ca418` |
| `tests/IconButton.test.tsx` | `4ffd1c7884772d803ddef0b8fceeb6425bcbf022` |
| `tests/SentenceStrip.test.tsx` | `525b0260d1884ba98601d2edd87dc56dca25d60d` |
| `tests/SymbolCard.test.tsx` | `e7b9e1af6d2544fca58ab6ec3dbb09a7a2f472a0` |
| `tests/download.test.ts` | `5890702ae50b501a87ff8ff1b4c691dab06b6f6e` |
| `tests/format.test.ts` | `4d5a7a13aa182a2b8429d40dee4aa9f3fa0278c8` |
| `tests/styleTokens.test.ts` | `573295cdabb926220c41b5e62d51fafcceb0cdc6` |
| `tests/symbols.test.ts` | `22e691f29b8ca95009852f9f5ddd547c84ec36bd` |
| `tests/useAccessibleInteraction.test.tsx` | `3aff85bf6591ad169e003552acf6ae692f490f96` |
