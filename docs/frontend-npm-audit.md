# Frontend npm audit

Audit date: 2026-09-05 (re-verified after moving build-only tooling out of runtime dependencies and updating `qs` in the development tree)

> This is the current production-dependency audit record. Re-run the commands below after any dependency change; build/test counts belong to the current validation run, not to this audit record unless explicitly dated.

## Result

The frontend production dependency audit is clean:

```text
npm audit --omit=dev --audit-level=moderate
0 vulnerabilities
```

`shadcn` and `tw-animate-css` are development/build dependencies. They are
needed to compile the CSS but are not shipped or required by the built SPA;
keeping them out of `dependencies` also prevents their CLI-only transitive tree
from entering production installs.

The current runtime dependencies include:

- `axios` `^1.19.0`
- `react` `19.2.8`
- `react-dom` `19.2.8`
- `react-router` `8.3.0`

The application is a client-only Vite SPA. It does not use React Server
Components or server actions.

## React Router v8 migration

The application migrated from `react-router-dom` 7.x to the published
`react-router` 8.3.0 package. React Router v8 separates core and DOM exports:

- Core route APIs such as `Route`, `Routes`, `Navigate`, `Outlet`, and hooks are
  imported from `react-router`.
- Browser/document APIs such as `createBrowserRouter`, `RouterProvider`, and
  `MemoryRouter` are imported from `react-router/dom`.

The Vite vendor chunk and Vitest mocks were updated to use the new package
name. TypeScript, lint, unit tests, production build, E2E build, and
`npm ci --dry-run` all pass after the migration.

## Verification

Run these checks after changing frontend dependencies:

```text
npm --prefix src/frontend ci
npm --prefix src/frontend run typecheck
npm --prefix src/frontend run lint -- --max-warnings=0
npm --prefix src/frontend test -- --run
npm --prefix src/frontend run i18n:audit
npm --prefix src/frontend audit --omit=dev --audit-level=moderate
npm --prefix src/frontend audit --audit-level=high
npm --prefix src/frontend run build
npm --prefix src/frontend run build:e2e
```

The production audit blocks moderate-or-higher findings; the full
development-tree audit blocks high-or-higher findings. Lower-severity advisories
in build-only tooling must be fixed via a targeted, compatible resolution or
kept documented here, and must never enter the production graph.

### Development-only advisory history

On 2026-09-05 the full development-tree audit reported one moderate `qs`
advisory (`GHSA-x5fp-wj9c-mxmx`, `GHSA-4mjr-xmp4-gh2g`, fixed in `6.16.0`)
through `shadcn`'s CLI dependency chain (`shadcn` → `@modelcontextprotocol/sdk`
→ `express` → `qs`). It was resolved the same day with a lockfile-only update
of `qs` `6.15.3` → `6.16.0`, which is inside the existing parent ranges
(`express ^6.14.0`, `body-parser ^6.15.2`), so no override or manifest change
was required. The production graph never contained that chain. The full audit
(including development dependencies) now reports 0 vulnerabilities.

Do not use `npm audit fix --force` without reviewing the resulting major
version changes and rerunning the complete frontend gate. Prefer a targeted
`npm update <package>` when the parent ranges already permit the fixed version,
and record the change here.
