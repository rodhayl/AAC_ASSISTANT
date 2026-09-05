# UI Simplification & Migration Plan

> Status: implemented through Phase 5 audit (2026-08-28). Last updated: 2026-08-28.
> Research date: 2026-08-26 (web-sourced, see "Sources" at the end).

## 1. Why

The frontend (`src/frontend`) hand-rolls a lot of UI that mature headless
primitives already provide. Measured duplication (Aug 2026):

| Pattern | Count | Cost |
| --- | --- | --- |
| Hand-rolled `fixed inset-0` modals/overlays (`role="dialog"`, focus trap, ESC, scroll lock reimplemented per file) | **16 files** | Biggest source of duplicated, hard-to-audit code |
| Native `<select>` elements styled ad-hoc | **29** | No accessible listbox behavior, inconsistent styling |
| Solid buttons as raw class strings (`bg-indigo-600 text-white px-4 py-2 rounded-lg`) | **~57** | Variant changes are find/replace; hover/disabled/loading inconsistent |
| Custom `Toggle` | 9 call sites | Fine, but no switch semantics/`data-state` from a primitive |
| `ConfirmDialog` | 7 call sites | Reimplements AlertDialog |
| Toast usage | 13 files / 5 direct calls | Custom `ToastContainer` reimplements a toast system |
| Custom `Button` | 2 call sites | Nearly unused — most pages bypass it |

Stack today: React 19.2, Tailwind CSS v4, react-router 8, zustand, lucide-react,
clsx + tailwind-merge, @dnd-kit. **No headless primitive library.**

## 2. Target stack (Aug-2026 best practice, researched — not from memory)

- **`shadcn/ui`** is the dominant way teams consume accessible primitives with
  Tailwind (113k+ GitHub stars, ~3.9M weekly CLI downloads, 50+ registry
  components). It copies component source into the repo (you own the code, no
  version lock-in) and is fully updated for **Tailwind v4 + React 19** (uses
  `data-slot` instead of `forwardRef`).
- **`Base UI`** (`@base-ui/react`, MUI) is the headless primitive layer that
  shadcn/ui **made the default in July 2026**. It reached v1.0.0 in Dec 2025,
  is built by ex-Radix engineers, ships monthly with a full-time team, has 35
  components (Dialog, Select, Switch, Tooltip, Combobox, Drawer…), smaller
  bundles than Radix, built-in RTL, and `keepMounted` for exit animations.
- Radix UI remains fully supported (shadcn `-b radix` flag) — use it only if we
  need Context Menu / Hover Card / Toast primitives, which Base UI lacks.
- Toasts: shadcn's toast layer is **`sonner`** (sold/installed as a separate
  package; the shadcn toast docs use it).
- **Keep** (no change): Tailwind v4, @dnd-kit (board grid drag/drop), zustand
  (app state), lucide-react (icons), react-router 8, the custom `themeStore`
  + HCM CSS (works and is audited), the WCAG contrast audit specs.

## 3. Migration strategy

Do it in **phases**, each independently shippable and verified by the existing
gates (unit tests + `contrast-audit.spec.ts` + `contrast-interactive.spec.ts` +
appearance/visual-smoke). Never break the accessibility audit; the HCM/dark
system must keep working — shadcn/Base UI components are unstyled by default,
so our Tailwind styling and the `html.high-contrast` palette remap keep
applying unchanged.

### Phase 0 — Foundation ✅ DONE (2026-08-26)
- `npx shadcn init -b base -t vite --preset nova` (Base UI, shadcn v4.19).
- Added the `@/*` path alias (`tsconfig.app.json` `paths`, `vite.config.ts`
  `resolve.alias`, `vitest.config.ts` same — required by shadcn and by the
  component's `@/lib/utils` import).
- `components.json` (base-nova, lucide, neutral). New deps: `@base-ui/react`,
  `class-variance-authority`, `tw-animate-css`. The CLI's `@fontsource-variable/geist`
  and the Geist font swap were **reverted** (kept Inter — not part of this work).
- `src/index.css`: kept `@import "tw-animate-css"` + `@import "shadcn/tailwind.css"`
  and the shadcn CSS variables; mapped `--primary`/`--primary-foreground` to the
  app's brand tokens (`rgb(var(--brand-rgb))` / `var(--color-white)`) so buttons
  follow the theme + HCM inversion automatically.
- **Name conflict resolved**: the app already used `text-primary` to mean "main
  text color" (13+ call sites), so the shadcn `Button` default variant uses
  `bg-brand text-white` (indigo + HCM-aware) instead of `bg-primary`.
- `src/components/ui/button.tsx` (Base UI primitive + cva, `data-slot`, custom
  `loading` prop, sizes matched to the app: default `h-9 px-4`, sm `h-8 px-3`).
- Deleted the old hand-rolled `src/components/ui/Button.tsx` and migrated its
  4 consumers (`ConfirmDialog`, `Boards`, `Symbols`, `SymbolGrid`) to the new
  component (`primary→default`, `danger→destructive`, `secondary→outline`).
- Verified: typecheck, lint, build, 652 unit tests, 152/152 E2E (incl. the
  WCAG contrast audit on the migrated pages).

### Phase 1 — Dialog + AlertDialog (replaces the 16 hand-rolled overlays)
- **Dialog migration: DONE.** `npx shadcn add dialog alert-dialog` was run
  earlier; every true modal now renders through the shared Base UI
  `Dialog`/`AlertDialog` primitives: `BoardSettingsDialog`, `ConfirmDialog`,
  `SymbolPicker`, `SymbolEditorDialog`, `SymbolSearchModal`,
  `ResetPasswordModal`, `GuardianProfileModal`, `SessionSummaryModal`,
  `KeyboardOverlay`, `PartnerOverlay`, and the in-page modals in `Students`
  (edit/assign/create/preferences), `Achievements` (editor/award/delete),
  `UserManagement` (edit/create), `SecurityTab` (change password), and
  `LearningModesTab` (prompt preview). External component APIs were kept so
  call sites barely changed; each migration deleted its hand-rolled backdrop,
  ESC listener, and `useModalFocusTrap` usage. The now-consumer-less
  `src/hooks/useModalFocusTrap.ts` (and its test) were deleted.
  - `Layout`'s mobile sidebar backdrop is not a dialog and was left as is.
  - `LearningChatPanel`'s end-session prompt is a non-modal popover
    (`aria-modal="false"`) and stays hand-rolled on purpose.
  - `admin.spec.ts`'s `div.fixed.inset-0` workaround for the un-ported
    GuardianProfileModal was replaced with `getByRole('dialog')`.
- Gate: audit specs + unit tests per migrated dialog. Verified: typecheck,
  lint, build, 177 targeted unit tests, 111/111 contrast-audit +
  contrast-interactive E2E in all four modes.
- Remaining (not done): a thin `AppDialog` wrapper has not been extracted —
  direct `DialogContent` usage per component proved sufficient; revisit only
  if dialog styling starts drifting between files.

### Phase 2 — Select (replaces the 29 native selects)
- **Select migration: DONE (high-value set).** `npx shadcn add select`
  (Base UI Select). Migrated the dynamic/longer lists where the primitive
  earns its keep: `SymbolSearchModal` (category + language filters),
  `SymbolPicker` (upload category), `GuardianProfileModal` (template), and
  `Boards` (student-assign picker). Two jsdom notes baked into tests:
  `vitest.setup.ts` needed `ResizeObserver`/`scrollIntoView`/pointer-capture
  polyfills (Base UI open handler hangs without them), and options must be
  activated with `fireEvent.pointerDown` + `fireEvent.click` (`userEvent` and
  click-only both hang/fail to commit). Base UI Select cannot commit an
  empty-string item value, so "All" filters use an `all`/`none` sentinel
  mapped back to the empty filter state.
- Kept native `<select>` (small, unchanged option lists or hard E2E/test
  contracts — each a deliberate decision):
  - `Students` edit role (3 static options; `selectOptions` unit contract).
  - `Achievements` editor selects (small/dynamic-in-modal; `selectOptions`).
  - `Symbols` category + sort (small lists; unit + E2E `selectOption`).
  - `LearningHeader` mode/difficulty and `BoardsAndTopicsSidebar` picks
    (small; E2E `learning-topics`/`llm-integration` `selectOption`).
  - `LanguageSwitcher` (2), `AppearanceTab` theme (4), `BoardSettingsDialog`
    category (7) — unchanged small lists.
  - `AiProviderFields` provider/model (model list is long, but the
    `maintenance.spec` E2E drives it via `selectOption`; revisit if that spec
    is ever rewritten).
  - `SymbolEditorDialog` linked board (modest list; unit asserts options).
  - `VoiceTab` voice/model selects (native `optgroup` groups + `toHaveValue`
    + pre-rendered-option assertions in tests; `tts-warmup` E2E touches the
    page).
  - `LearningModesTab` preview student (small dynamic list).
- Final inventory: 19 native selects remain, each deliberately retained for
  small static lists, optgroup/pre-rendered-option contracts, or E2E compatibility;
  the board picker and category filters requested for the follow-up are migrated.

### Phase 3 — Switch + Tooltip + Button sweep ✅ DONE (2026-08-28)

- `npx shadcn add switch tooltip`
- Replace `ui/Toggle` internals with the shadcn `Switch` (keep the same props
  so the 9 call sites barely change); verify the HCM knob fix still holds.
- **Button sweep: DONE (part of Phase 0 completion).** All raw solid
  primary buttons (the `bg-indigo-600 text-white hover:bg-indigo-700`
  pattern and the `bg-brand` ones) were converted to the shadcn `Button`:
  ~40 raw buttons across 30 files → **66 `<Button>` usages in 32 files**;
  zero raw primary-styled buttons remain (`grep '<button' | grep
  'bg-brand|bg-indigo-600'` → 0). Icon/ghost/text actions stay as raw
  `<button>` where the component adds nothing. Links styled as buttons use
  the exported `buttonVariants` (`NotFound`). Converted call sites also got
  their conflicting leftover classes stripped (`hover:bg-indigo-700`,
  `disabled:opacity-50`, redundant `px-4 py-2 rounded-lg`), since the
  `default` variant provides `bg-brand text-white hover:bg-brand/80` and the
  base has `disabled:opacity-50`.
  - Note: the mechanical sweep initially left mismatched `</Button>`/`</button>`
    tags in 16 files; all were repaired and verified by typecheck + lint.

### Phase 4 — Toasts ✅ DONE (2026-08-28)

- Install `sonner`, add `<Toaster />` next to `ToastContainer`; migrate the
  13 files' toast calls to `toast()`. Delete `ToastContainer` when coverage is
  complete.
- Base UI has no Toast primitive — sonner is the shadcn-recommended layer.

### Phase 5 — Reuse sweep & cleanup ✅ AUDITED (2026-08-28)

- Extract repeated markup into shared components where it earns its keep:
  empty states (`EmptyState`), page headers, form fields (label + input +
  error), badges (we already have `symbolCategoryStyle`). Reuse, don't
  abstract for its own sake.
- Delete now-unused custom components (`Toggle` after switch, `ToastContainer`
  after sonner, `ConfirmDialog` wrapper if folded into `AlertDialog`).
- Follow the repo's production-only rule: any component left without a runtime
  reference is removed together with its tests.

## 4. Guardrails

- **Accessibility audit is the contract.** Every phase re-runs
  `contrast-audit.spec.ts` (all routes × 4 modes), `contrast-interactive.spec.ts`
  (modals/panels × 4 modes), appearance + visual-smoke. The `high-contrast`
  remap in `index.css` must keep passing — Base UI parts are unstyled, so they
  inherit the palette remap like today's markup.
- **Theme system untouched.** `themeStore`, `SettingsManager`, the HCM CSS
  blocks and the dark-mode token fixes from the 2026-08 audit stay as-is; the
  migration only changes which DOM the classes land on.
- **No dependency roulette.** Add only `@base-ui/react` (+ `sonner`); shadcn
  copies its own code. Do not introduce a full styled library (MUI, Mantine,
  Ant, Chakra) — the app is Tailwind-native and that would fight the theme
  system.
- **Per-phase PRs.** Each phase is small, reviewed, and verified independently.

## 5. Expected outcome

- ~16 duplicated dialog implementations → 1 primitive + thin wrappers.
- ~57 duplicated button strings → 1 variant-based `Button`.
- Accessible Selects, Switch, Tooltips, toasts with correct ARIA/focus/ESC
  behavior out of the box (currently hand-maintained and easy to regress).
- Smaller frontend surface to audit; the contrast audit stays the safety net.

## 6. Sources (retrieved 2026-08-26)

- shadcn/ui — Tailwind v4 + React 19 support: https://ui.shadcn.com/docs/tailwind-v4
- shadcn changelog — Base UI default (July 2026): https://ui.shadcn.com/docs/changelog/2026-07-base-ui-default
- Radix vs Base UI comparison (Jul 2026): https://www.shadcndeck.com/blog/radix-vs-base-ui
- Top Headless UI libraries for React in 2026: https://www.greatfrontend.com/blog/top-headless-ui-libraries-for-react-in-2026
- shadcn Base UI docs (dialog/alert-dialog): https://ui.shadcn.com/docs/components/base/dialog
