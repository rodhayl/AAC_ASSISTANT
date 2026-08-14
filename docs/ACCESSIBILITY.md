# Accessibility

Accessibility is core to AAC software, because the primary users may have
motor, visual, or cognitive disabilities. This document records what we test,
what we know works, and what still needs work. It is **not** a WCAG conformance
claim.

## 1. What we test

### Automated checks (CI)

- **Axe Core automated scans (`e2e/axe-accessibility.spec.ts`)** — Automated accessibility testing integrated via `@axe-core/playwright` across critical pages:
  - First-run setup (`/setup`)
  - Login (`/login`)
  - Communication board (`/communication`)
  - Active learning mode (`/learning`)
  - Settings & Accessibility panel (`/settings`)
  Enforces zero serious or critical accessibility violations on WCAG 2.0/2.1 Level A/AA rulesets.
- **Keyboard navigation & focus traps (`e2e/accessibility.spec.ts`)** — Verifies skip-to-content links, tab order, modal focus entrapment, and Enter/Space activation for all communication board symbols and sentence controls.
- **CSS `prefers-reduced-motion` compliance** — Global CSS media query clamps animation and transition durations to 0.01ms for users with vestibular sensitivity (`src/frontend/tests/reducedMotion.test.ts`).
- **ESLint accessibility rules (`jsx-a11y`)** — Enforces accessible labels, image alt text, and semantic HTML elements during build.
- **`useAccessibleInteraction` unit tests** — Validates dwell-time press-and-hold selection and repeat-click debouncing.

### Manual checks performed to date

- Keyboard focus visibility and reachability on primary navigation routes.
- Communication board symbols formatted as large touch and click targets.
- Toggles and form controls expose explicit accessible names (`aria-label`) via the shared `Toggle` component.
- High-contrast mode and dark mode theme switching in Settings.
- Viewport scaling and zoom compatibility up to 200%.

## 2. Untested assistive technologies

The following assistive technologies have not yet undergone structured manual auditing by clinical specialists or native assistive-device users:
- Dedicated screen-reader verification with NVDA (Windows), JAWS (Windows), or VoiceOver (macOS / iOS).
- Physical single-switch and dual-switch hardware scanning devices.
- Eye-tracking and head-mouse hardware integrations.

## 3. Known limitations

These are honest, current limitations; they are not exhaustive:

- **No formal WCAG 2.x conformance claim.** Automated Axe scans check technical accessibility rules but do not replace human evaluator testing.
- **No clinical or specialist certification.** AAC Assistant has not undergone formal clinical trials.
- **Symbol alt text** is provided for seeded core vocabulary; custom operator-uploaded symbols depend on the label assigned by the operator.
- **Switch-access / scanning input** (cycling highlight across rows/columns for single-switch users) is planned on the roadmap (Issue #6) and is not yet implemented.

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
