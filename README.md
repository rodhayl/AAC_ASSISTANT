# AAC Assistant

Privacy-focused AAC application with a FastAPI backend and React/Vite frontend.

## What Is Included

- Backend API and services for AAC workflows
- React frontend for communication boards, learning flows, and settings
- Test suite for backend and frontend behavior
- Windows startup, dependency, test, and packaging scripts

## Repository Layout

- Backend API entry point: `src/api/main.py`
- Core domain/services: `src/aac_app/`
- Frontend app: `src/frontend/`
- Automation and helper scripts: `scripts/`
- Tests: `tests/`
- Main technical guide: `docs/01_PROJECT_GUIDE.md`

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+
- npm 10+

## Configuration

1. Run `install_dependencies.bat` once (it creates `.env` from `.env.example` if missing).
2. Replace bootstrap defaults and keep a strong random `JWT_SECRET_KEY` for shared/public deployments.
3. For public/production deployments keep:
- `ALLOW_DB_RESET=false`
- `AAC_SEED_SAMPLE_DATA=false`

## Install

Windows (recommended):

```bat
install_dependencies.bat
```

Manual:

```bash
uv sync
npm --prefix src/frontend ci
```

## Run

Option 1 (Windows launcher script):

```bat
start.bat
```

`start.bat` runs the production server as one uvicorn process and serves the
built frontend and API on port 8086. On first run, if no admin account exists,
it also creates a bootstrap admin account:

- Username: `admin1`
- Password: `Admin123`

You can override these in `.env`:

- `AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN`
- `AAC_BOOTSTRAP_ADMIN_USERNAME`
- `AAC_BOOTSTRAP_ADMIN_PASSWORD`

Option 2 (manual dev run):

```bash
uv run python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8086
npm --prefix src/frontend run dev
```

Endpoints:

- Frontend dev app: `http://localhost:5176`
- Backend API: `http://localhost:8086`
- Swagger docs: `http://localhost:8086/docs`
- ReDoc docs: `http://localhost:8086/redoc`

## Validate

Windows test runner (recommended):

```bat
run_tests.bat
```

`run_tests.bat` checks whether `.venv` and `src/frontend/node_modules` exist.
If they are missing, it prompts:

`Dependencies are missing. Would you like to install them now? (Y/N)`

Manual validation:

```bash
python -m pytest -q tests
python -m flake8 src tests
python -m pip check
python -m pip_audit -r requirements.txt
cmd /c npm.cmd --prefix src/frontend run lint
cmd /c npm.cmd --prefix src/frontend test -- --run
cmd /c npm.cmd --prefix src/frontend run build
cmd /c npm.cmd --prefix src/frontend audit --audit-level=high
```

## Packaging (Windows)

- Build script: `build_package.bat`
- PyInstaller spec: `AAC_Assistant.spec` (PyInstaller 6.21 onedir)
- Inno Setup script: `installer.iss` (Inno Setup 6.7.3)

Build a release from a checkout with the frontend dependencies installed:

```bat
build_package.bat
```

The build produces `dist\AAC_Assistant\AAC_Assistant.exe` and
`dist\AAC_Assistant_Setup_2.0.0.exe`. The batch file invokes
`C:\Users\rulfe\AppData\Local\Programs\Inno Setup 6\ISCC.exe` when it is not
already on `PATH`; install Inno Setup 6.7.3 per-user with winget if needed.
The installer requires UAC approval for the default Program Files location.
Use the installer's directory dialog to choose a per-user location when
administrator approval is not available.

Installed copies keep the database, logs, and uploads in
`%APPDATA%\AACAssistant`, so standard users can run the app without writing to
Program Files. A portable copy of the onedir folder keeps `data\`, `logs\`, and
`uploads\` beside the executable. Set `AAC_ASSISTANT_PORTABLE=1` to force this
portable behavior. Uninstall removes application files and disposable logs but
does not remove `data\` or `uploads\`.

Voice is intentionally not bundled. After installation, run
`uv sync --extra voice` in a development checkout or follow `docs/voice.md` to
install/download the optional faster-whisper model; the core packaged app
continues to support browser TTS and keyboard/symbol communication without it.

There is no macOS packaging script in this repository.

## Utility Scripts

Project utilities live in `scripts/` (DB utilities, migration helpers, diagnostics, and setup tooling).

Root Windows helper scripts:

- `install_dependencies.bat`: creates/updates `.venv` with uv and prepares `.env`.
- `start.bat`: starts the production backend and serves the built SPA on port 8086.
- `run_tests.bat`: validates deps/env and runs backend + frontend tests.

Run any script with:

```bash
python scripts/<script_name>.py --help
```

## Documentation Notes

- Canonical technical guide: `docs/01_PROJECT_GUIDE.md`
- Runtime API schema: `http://localhost:8086/docs` and `http://localhost:8086/redoc`
- Deployment configuration template: `.env.example`
- Documentacion en espanol: la guia principal se mantiene en ingles en `docs/01_PROJECT_GUIDE.md`

## Security Notes

- Never commit `env.properties`, `.env` files, or Playwright auth state.
- Rotate credentials immediately if any secret was exposed in a shared working tree.
- Change the bootstrap admin password immediately after first login.

## License

MIT. See `LICENSE`.
