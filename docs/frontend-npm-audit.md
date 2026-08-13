# Frontend npm audit

Audit date: 2026-08-07

## Result

The frontend production dependency audit is clean:

```text
npm audit --omit=dev
0 vulnerabilities
```

The current runtime dependencies include:

- `axios` `^1.19.0`
- `react` `19.2.7`
- `react-dom` `19.2.7`
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
npm --prefix src/frontend audit --omit=dev
npm --prefix src/frontend run build
npm --prefix src/frontend run build:e2e
```

Do not use `npm audit fix --force` without reviewing the resulting major
version changes and rerunning the complete frontend gate.
