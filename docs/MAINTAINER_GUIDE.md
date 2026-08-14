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
   Ensures zero regressions against real FastAPI and SPA backend instances, including automated Axe Core accessibility scans (`e2e/axe-accessibility.spec.ts`).

3. **CI Gate Completion:**
   Confirm all required GitHub Actions jobs (`backend`, `frontend`, `packaging-windows`, `e2e-production`, `secret-scan`, `dependency-review`, `codeql`) pass 100% green on the pull request.

---

## 2. Release Checklist

When preparing an official semantic-versioned release (e.g. `v2.x.y`):

1. **Version Alignment:**
   - Confirm version constants in `pyproject.toml`, `src/config.py`, `src/frontend/src/config.ts`, `installer/installer.iss`, `.env.example`, and `docs/RELEASE_NOTES.md` are aligned.
   - Verify alignment using test suite: `uv run pytest tests/test_config_pydantic.py`.

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
