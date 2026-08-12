# Release PyInstaller Inno Slim Implementation Plan

> **Document status (2026-08-12): COMPLETED / HISTORICAL.** The onedir packaging pipeline, installer, runtime paths, graceful update event, headless launcher flag, and release gates are already integrated. This plan records the original design and validation intent; it is not an outstanding checklist. Current recovery and rollback procedures live in `docs/RELEASE_READINESS.md`. The verified two-artifact rollback exercise used the current payload under two version labels, so it proves installer/data preservation mechanics but not cross-version schema compatibility or automatic rollback.

> **Historical workflow note:** the original plan referenced an external plan-execution workflow file, which is not part of the current repository. Do not follow that historical instruction; use the current release gates in `README.md` and `docs/RELEASE_READINESS.md`.

**Goal:** Produce a slim, reproducible PyInstaller onedir build and Inno Setup installer that runs the production SPA on port 8086 while keeping installed user data writable and preserving it during uninstall.

**Architecture:** PyInstaller bundles the launcher, backend package, built frontend, n-grams, and companion templates as read-only resources. Frozen runtime paths resolve bundled resources through `_MEIPASS`; installed writable data uses `%APPDATA%\AACAssistant` when the executable is under Program Files, while portable copies keep `data/`, `logs/`, and `uploads/` beside the executable. The batch file is an unattended shim around `uv`, PyInstaller, and an absolute Inno compiler path.

**Tech Stack:** Python 3.13, PyInstaller 6.21 onedir, FastAPI/Uvicorn, React/Vite, Inno Setup 6.7.3, Windows batch.

---

### Task 1: Make frozen runtime resources and writable paths correct

**Files:**
- Modify: `src/config.py`
- Modify: `src/api/main.py`
- Modify: `src/aac_app/services/template_manager.py`
- Test: `tests/test_packaging_runtime.py`

Add tests for installed-versus-portable runtime roots, bundled n-gram/template lookup, and frozen frontend resolution. Implement `_MEIPASS`-aware bundled paths and `%APPDATA%\AACAssistant` for installed locations without changing development paths.

### Task 2: Rewrite the PyInstaller build specification

**Files:**
- Modify: `AAC_Assistant.spec`

Use `launcher.pyw` as the GUI entry, include the built SPA, source package, n-grams, companion templates, and `.env.example`, and exclude voice/dev packages including `faster_whisper`, `ctranslate2`, and `av`. Keep the output onedir and console-free.

### Task 3: Replace the package batch script

**Files:**
- Modify: `build_package.bat`

Make the script fail fast, build the frontend, invoke `uv run pyinstaller`, verify `dist\AAC_Assistant\AAC_Assistant.exe`, invoke the absolute Inno compiler path (with PATH fallback), and never kill processes by image name or generate inline scripts.

### Task 4: Update the installer and packaging documentation

**Files:**
- Modify: `installer.iss`
- Modify: `README.md`

Install the onedir output, ship `.env.example`, use the current output path, retain user data directories, and delete only logs/cache/app files on uninstall. Document Program Files UAC, per-user override, portable mode, voice post-install setup, and the verification commands.

### Task 5: Verify, smoke, and commit

Run the packaging regression tests, full backend/frontend gates, PyInstaller build, size checks, frozen login/boards smoke, Inno compile, and a disposable install/uninstall check confirming app removal with data/uploads preserved. Commit the verified repository changes with the feature id.
