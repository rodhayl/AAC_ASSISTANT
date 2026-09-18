# Maintainer Guide and Release Runbook

This guide summarizes standard operational procedures for maintainers reviewing pull requests, running validation, and creating official releases.

---

## 1. Pull Request Verification Checklist

Before merging any pull request into `main`:

1. **Automated Verification Suite:**
   Run the local verification script:
   ```bash
   uv run python scripts/verify_pr.py
   ```
   This executes:
   - Backend `ruff` linting and syntax compilation.
   - Backend `pytest` suite with branch/statement coverage.
   - Frontend TypeScript typechecking (`tsc -b --noEmit`).
   - Frontend ESLint (`eslint .`).
   - Frontend Vitest suite with v8 coverage provider.
   - Frontend production build and bundle size validation.
   - Documentation markdown link validation.

2. **Integration / E2E Verification:**
   When UI, auth, or routing logic changes:
   ```bash
   npm --prefix src/frontend run test:e2e
   ```
   Ensures zero regressions against real FastAPI and SPA backend instances, including automated Axe Core accessibility scans (`e2e/axe-accessibility.spec.ts`) and the appearance/contrast suites (`e2e/appearance.spec.ts`, `e2e/contrast-audit.spec.ts`, `e2e/contrast-interactive.spec.ts`). The contrast specs render every route and interactive overlay in all four modes (light, dark, high-contrast, high-contrast-dark) and fail on any painted text below WCAG AA (4.5:1).

   The server under `PLAYWRIGHT_BASE_URL` (default `http://127.0.0.1:8086`) can run with or without sample seeding. With `AAC_SEED_SAMPLE_DATA=true` the seed passwords must match `e2e/auth.setup.ts` (`AAC_SEED_ADMIN1_PASSWORD`, `AAC_SEED_STUDENT1_PASSWORD`, `AAC_SEED_TEACHER1_PASSWORD`), otherwise the seeded demo users receive random passwords and the auth setup fails; see `docs/test_scenarios/execute_all_scenarios.md` for the full recipe. With `AAC_SEED_SAMPLE_DATA=false`, start the server with `E2E_PROVISION_VIA_API=1` so `auth.setup.ts` provisions the student/teacher accounts through the admin API. Demo-board specs build what they need either way (see §1b).

3. **CI Gate Completion:**
   Confirm all required GitHub Actions jobs (`backend`, `frontend`, `packaging-windows`, `e2e-clean`, `e2e-production-gate`, `e2e-production-compat`, `secret-scan`, `dependency-review`, `codeql`) pass 100% green on the pull request.

   When hosted runner minutes are exhausted, every one of those jobs dies a
   few seconds after it starts regardless of the change. In that case the
   repository gates are the local suites instead: `scripts/verify_pr.py` (§1),
   the targeted Playwright recipes (§1b), and `build_package.bat` with
   `AAC_SIGN_RELEASE=1` for packaging (§2). §1c runs the same gate inside a
   Linux container when a non-Windows environment is required. Restore CI by
   adding minutes or raising the spending limit in GitHub billing settings;
   nothing in the repository has to change.

---

## 1b. Test Suite Structure

Tests are organized by concern, not by phase. Backend tests live in `tests/`
(with shared fixtures in `tests/conftest.py` and helpers in
`tests/auth_helpers.py`); frontend unit tests live in `src/frontend/tests/`;
browser E2E specs live in `src/frontend/e2e/`.

- **Backend API tests** (`tests/test_*_routes.py`, `tests/test_api_*`, ...)
  exercise endpoints through `TestClient` against an isolated temporary
  SQLite database.
- **Backend unit tests** cover services and helpers directly
  (`tests/test_auth_pwdlib.py`, `tests/test_translation_service.py`, ...).
- **Domain consolidation:** overlapping suites are merged per domain rather
  than duplicated (e.g. the legacy helper module `test_utils_auth.py` was
  renamed to `tests/auth_helpers.py`, and the frozen-runtime cases were
  folded into `tests/test_packaging_improvements.py`).
- **Coverage gates:** backend `pytest --cov` reports line/branch coverage
  (~80% lines); frontend Vitest enforces a regression guard in
  `src/frontend/vitest.config.ts` on the application-only baseline
  (lines/statements ≥ 50%, functions ≥ 45%, branches ≥ 45%).
- **E2E** (`src/frontend/e2e/`) runs against a real FastAPI + SPA backend
  with sample seeding and deterministic seed passwords (see `auth.setup.ts`),
  and (with `AAC_SEED_SAMPLE_DATA=false`) against a clean database where every
  spec builds the demo data it needs through the API.

### Which E2E specs need the demo board

No spec requires seeded sample data. Specs that assert the demo board
(`Comunicación General` / `General Communication Board`) call
`ensureDemoBoard()` from `src/frontend/e2e/demo-fixture.ts` in their setup,
which builds the same shape through the public API when it is missing and
reuses the seeded board when it already exists (so the seeded
`e2e-production-compat` job is unaffected):

| Spec | Demo dependency |
| --- | --- |
| `accessibility.spec.ts` (2 tests) | demo board opens for the student |
| `communication.spec.ts` (4 tests) | demo board + its symbols |
| `pilot-gate.spec.ts` (2 tests) | demo board phrase building |
| `board-assignment.spec.ts` | demo board assigned to `student1` |
| `advanced.spec.ts` | a board exists to open the editor |
| `learning-games.spec.ts` (symbol hunt) | demo board is playable (12 symbols) |
| `learning-topics.spec.ts` | `Comunicación General` is a board option |
| `students-lifecycle.spec.ts` | an assignment to unassign/re-assign |
| `extended-features.spec.ts` | a symbol "in use" on the demo board |

The fixture creates a 3x4 board named `Comunicación General` owned by the admin,
filled with the first 12 catalog symbols (the same pick `seed.py` makes), and
assigns it to the `E2E_STUDENT_*` account. `contrast-interactive.spec.ts` also
calls the fixture, then resolves the board id through the API, so its four
board-editor audits run on both data shapes (the null check that skips them
remains only as a guard against an API-shape change). Everything is green on
seeded and clean databases.

Run the whole suite against either data shape:

```bash
# seeded suite (e2e-production-compat)
npx playwright test
# clean database (e2e-clean) — no filter, no skipped spec
npx playwright test
```

The clean server needs `AAC_SEED_SAMPLE_DATA=false` plus
`E2E_PROVISION_VIA_API=1`, because `auth.setup.ts` provisions the student/teacher
accounts through the admin API when the demo users do not exist.

### E2E isolation rules

* **Never sign out a shared E2E account.** Logout revokes that account's access
tokens server-side (pinned by `pilot-gate.spec.ts`), so logging out the
`admin1` session invalidates `playwright/.auth/admin.json` and every later spec
in the same run is redirected to `/login`. Use a disposable account
(`session-and-board-lifecycle.spec.ts` creates `e2e_iso_admin_*`) instead.
* **Do not fill forms by input index.** Adding a field (e.g. the confirm-password
input) silently shifts the indices; target ids (`#create-student-password`) or
labels instead.
* **Do not scope to bare layout classes.** `.space-y-2` / `.last()` matches
unrelated containers once the surrounding markup changes; use a `data-testid`
on the container (`saved-topics-list`).
* **Match labels bilingually.** The signed-in account's persisted UI language
can override the `localStorage` hint, so use `/new board|nuevo tablero/i`
patterns for user-visible controls.

---

## 1c. Reproducible Linux checks in a container

`Dockerfile.checks` runs the same gate as §1 inside a Linux image matching the
CI runners (Python 3.13, Node 22, `uv`). Use it when a change may behave
differently outside Windows, or when the hosted jobs are unavailable:

```bash
docker build -f Dockerfile.checks -t aac-checks .
docker run --rm aac-checks                                  # full gate
docker run --rm aac-checks uv run pytest tests/<file> -q    # a single file
```

Dependencies come from the lockfiles and the sources arrive through the build
context, so the host needs no Python, Node or `uv`; on Windows this requires
Docker Desktop with the WSL2 backend. Add `-v "$PWD:/workspace"` only when you
want coverage reports and build outputs written back to the host.

---

## 2. Release Checklist

When preparing an official semantic-versioned release (e.g. `v2.x.y`):

1. **Version Alignment:**
   - Bump `[project].version` in `pyproject.toml`: that is the single source the backend (`src/config.py` reads the file, also bundled into the frozen app), the frontend build (injected into `VITE_APP_VERSION`), the installer (`build_package.bat` passes it with `/DMyAppVersion`), and the CI workflows (derived at run time) all use. No other file needs editing, and none may hold a copy of the number.
   - Refresh the lockfile and the release docs: `uv lock`, then `CHANGELOG.md`, `docs/RELEASE_NOTES.md`, and `docs/PROJECT_METRICS.md`.
   - Verify with `uv run pytest tests/test_config_pydantic.py`, which fails if any layer duplicates the version literal.

2. **Documentation & Changelog:**
   - Update `CHANGELOG.md` with release date and categorized changes.
   - Update `docs/RELEASE_NOTES.md` with highlights, security updates, and checksum guidance.
   - Refresh `docs/PROJECT_METRICS.md` with dated repository and test statistics.

3. **Windows Packaging Build & Smoke Test:**
   - Build PyInstaller executable and Inno Setup installer:
     ```powershell
     build_package.bat
     ```
   - Verify non-interactive smoke run with `AAC_ASSISTANT_NO_BROWSER=1`.

4. **Integrity Metadata & SBOM:**
   - Generate release checksums and CycloneDX SBOM:
     ```bash
     uv run python scripts/generate_sbom.py
     ```
   - Produces `dist/SHA256SUMS.txt` and `dist/SBOM.json`.

5. **First-Run Verification:**
   - Test clean installation to verify that first run redirects to `/setup` on loopback (`127.0.0.1`) and requires operator-chosen administrator credentials.

6. **Tagging and Publishing:**
   - Create annotated Git tag from validated `main` commit:
     ```bash
     git tag -a v2.x.y -m "AAC Assistant v2.x.y"
     git push origin v2.x.y
     ```
   - Publish GitHub Release attaching `AAC_Assistant_Setup_2.x.y.exe`, portable `.zip`, `SHA256SUMS.txt`, and `SBOM.json`.
