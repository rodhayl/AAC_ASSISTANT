# Accessibility

Accessibility is core to AAC software, because the primary users may have
motor, visual, or cognitive disabilities. This document records what we test,
what we know works, and what still needs work. It is **not** a WCAG conformance
claim.

## 1. What we test

### Automated checks (CI)

- `npm run lint` — ESLint with React accessibility rules (`jsx-a11y`).
- `npm run build` — type-safe component props.
- Playwright end-to-end suite includes a visual/contrast smoke test that renders
  the application in light, dark, and high-contrast modes at desktop and mobile
  viewports, plus a keyboard-operation spec (`e2e/accessibility.spec.ts`) that
  verifies the skip link, symbol activation via Enter, and keyboard-operable
  sentence controls.
- `useAccessibleInteraction` unit tests cover dwell-time selection and
  repeat-click debouncing for board symbols.

### Manual checks performed to date

- Keyboard focus is visible and reachable on primary navigation.
- Communication board symbols are large touch/click targets.
- Toggles and form controls expose accessible names (`aria-label`) via the
  shared `Toggle` component.
- High-contrast and dark modes are selectable in Settings.
- Text size is not fixed; the interface scales with browser zoom.

## 2. Known limitations

These are honest, current limitations; they are not exhaustive:

- **No formal WCAG 2.x audit.** Automated checks do not guarantee conformance.
- **No dedicated screen-reader test pass** has been recorded. We have not
  verified every flow with NVDA/JAWS/VoiceOver.
- **Symbol alt text** is present for seeded symbols, but operator-uploaded
  symbols depend on the label the operator provides.
- **Reduced-motion preference** is honored for CSS animations and transitions
  via a global `prefers-reduced-motion` rule (durations collapse to 0.01ms);
  JavaScript-driven smooth scrolling (e.g., section `scrollIntoView`) is not yet
  covered.
- **Dwell-time selection** works on board symbols: press-and-hold for the
  configured `dwell_time` selects the symbol (`useAccessibleInteraction`, unit
  tested). Automatic **switch/scanning input** (a highlight that cycles between
  targets) is not yet implemented.
- **Color-independent communication** is partially supported (labels always
  accompany symbols); we have not audited every chart/status indicator for
  color-only encoding.

## 3. Tested environments

- Chromium (Playwright) headless, desktop and mobile viewports.
- Windows 10/11 (packaged application smoke).
- Light, dark, and high-contrast themes.

## 4. Reporting accessibility issues

Please open an issue with:

- The affected screen and steps to reproduce.
- The assistive technology and browser you use.
- What you expected versus what happened.

## 5. Future work

- Add a dedicated screen-reader test pass.
- Implement automatic switch-access / scanning input (a focus/selection
  highlight that cycles between targets) as a complement to dwell-click.
- Cover JavaScript-driven smooth scrolling under `prefers-reduced-motion`.
- Audit color-only indicators and add non-color affordances.
- Move toward a documented WCAG 2.2 AA target with an external audit.
