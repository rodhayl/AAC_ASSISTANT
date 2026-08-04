# Frontend npm audit triage

Audit date: 2026-08-04

## Result

The baseline `npm --prefix src/frontend audit --json` reported 17
vulnerability groups: 1 low, 2 moderate, 13 high, and 1 critical.
`npm audit fix` applied the available non-breaking updates. The direct
runtime dependencies were raised to fixed published versions:

- `axios`: `1.13.5` -> `1.19.0`
- `react-router-dom` and its `react-router` dependency: `7.13.0` -> `7.18.2`

The lockfile also updates the vulnerable transitive packages used by the
frontend toolchain. ESLint, Vitest, TypeScript, and the Vite production build
remain green after the update.

## Finding classification

| Finding group | Scope | Remediation |
| --- | --- | --- |
| `axios` | Production dependency | Fixed by the `1.19.0` lockfile update. |
| `follow-redirects`, `form-data` | Reachable through production `axios` (also used by dev `jsdom`) | Fixed by the lockfile update (`1.16.0` and `4.0.6`). |
| `react-router`, `react-router-dom` | Production routing | Updated to the latest published compatible 7.x release, `7.18.2`. One advisory remains, described below. |
| `@babel/core`, `ajv`, `brace-expansion`, `flatted`, `js-yaml`, `minimatch`, `picomatch` | Development-only lint/test/build tooling | Fixed by `npm audit fix`; none ship in `dist/`. |
| `postcss`, `rollup`, `vite`, `vitest`, `ws` | Development-only CSS/build/test tooling | Fixed by `npm audit fix`; none ship in `dist/`. |

## Accepted remaining finding

The final audit reports one high advisory group affecting
`react-router`/`react-router-dom`: `GHSA-qwww-vcr4-c8h2`, an RSC-mode CSRF
bypass. The app uses `createBrowserRouter` and client-side routes only; it
does not use React Server Components or server actions.

`7.18.2` is the latest `react-router-dom` release available from the npm
registry. The advisory's fixed range starts at `8.3.0`, but that release is
not published. The final audit's suggested `7.11.0` "fix" is a semver-major
downgrade from the current 7.18.2 floor, so it is intentionally rejected.
Forcing an unavailable major upgrade or downgrading the stack would either
fail installation or require an unverified migration. The finding is
therefore accepted as no-fix-available for the current published compatible
release and should be rechecked when React Router publishes a fixed version.

## Verification

After each dependency update:

```text
npm --prefix src/frontend run lint
npm --prefix src/frontend test -- --run
npm --prefix src/frontend run build
```

All three commands pass. The final audit has no low, moderate, or critical
findings; the only remaining result is the documented React Router advisory.
