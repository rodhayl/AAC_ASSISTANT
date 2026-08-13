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
  viewports.

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
- **Reduced-motion preference** is not yet systematically honored across all
  animations.
- **Dwell-time and switch-access support** (common AAC input methods) is
  partial; `dwell_time` is stored as a preference but is not yet wired to a
  scanning input mode.
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
- Implement switch-access / scanning input driven by `dwell_time`.
- Honor `prefers-reduced-motion`.
- Audit color-only indicators and add non-color affordances.
- Move toward a documented WCAG 2.2 AA target with an external audit.
