# AAC Assistant

Privacy-focused AAC software for communication boards, symbol search, learning
sessions, and browser-based speech. The application is a FastAPI backend and a
React 19/Vite frontend. In production, one backend process serves both the API
and the built single-page application.

## What is included

- FastAPI API and SQLite data layer for AAC workflows
- React/Vite interface for communication, boards, symbols, learning, and
  administration
- Optional local speech-to-text through the `voice` uv extra
- Learning sessions with adaptive LLM questions: auto-ask questions (can be
  toggled per learning mode for conversational modes), a manual "New question"
  button, correct-answer highlighting, live progress chips, and an end-of-session
  summary modal
- Automated Python and frontend test suites
- Windows scripts for installation, running, testing, and packaging

## Prerequisites

For a source checkout, install:

- Windows 10 or newer
- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+ and npm 10+ (needed to build or run the frontend)

The packaged Windows application does not require a separate Python or Node.js
installation. Node.js is only needed for source-checkout frontend development
and builds.

## Quick start

From the repository root, the recommended Windows setup is:

```bat
install_dependencies.bat
```

On Windows source checkouts this now attempts to bootstrap `uv` automatically
when it is missing, then runs `uv sync`, creates or migrates `.env`, repairs
the JWT secret, and installs/builds the frontend. To include optional
speech-to-text support:

```bat
install_dependencies.bat voice
```

The equivalent core Python setup is:

```powershell
uv sync
npm --prefix src/frontend ci
npm --prefix src/frontend run build
```

For development and validation tools, sync the dev group:

```powershell
uv sync --group dev
```

Configuration is read from `.env`. The safe template is `.env.example`; do not
commit your local `.env`.

## Run the application

### Linux source checkout

The Linux launcher is separate from the Windows scripts and does not change the
Windows startup or packaging flow. From the repository root:

```bash
uv sync
npm --prefix src/frontend ci
npm --prefix src/frontend run build
chmod +x start.sh
./start.sh
```

Use `./start.sh --dev` for the backend plus Vite development mode. The launcher
uses `.venv/bin/python` when available and otherwise delegates to `uv run`.

### Production mode, one process

```bat
start.bat
```

The default launcher runs one uvicorn process on `http://127.0.0.1:8086` and
serves the API, built React application, uploads, and API docs from that port.
If `uv` is missing on Windows, `start.bat` tries to install it automatically
before launching. If the frontend build is missing and Node.js is available,
the launcher builds it automatically. On first run, the default bootstrap
administrator is:

- Username: `admin1`
- Password: `Admin123`

Change this password after first login. The bootstrap values can be changed in
`.env` before first run.

### Development mode, uvicorn plus Vite

```bat
start.bat --dev
```

This starts the backend on port `8086` and the Vite development server on port
`5176`. Open `http://127.0.0.1:5176` for the frontend during development.
The backend remains available at `http://127.0.0.1:8086`.

The equivalent manual commands, in two terminals, are:

```powershell
uv run python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8086
npm --prefix src/frontend run dev -- --host 127.0.0.1 --port 5176
```

Useful endpoints:

- Application: `http://127.0.0.1:8086/`
- Frontend development server: `http://127.0.0.1:5176/`
- Swagger: `http://127.0.0.1:8086/docs`
- ReDoc: `http://127.0.0.1:8086/redoc`
- Health check: `http://127.0.0.1:8086/api/health`

## Configuration reference

Copy `.env.example` to `.env` only when setting up manually. The table below
lists every key in the template. Values supplied as process environment
variables take precedence over the file.

| Key | Default | Meaning |
| --- | --- | --- |
| `BACKEND_HOST` | `0.0.0.0` | Address uvicorn binds to. Use `127.0.0.1` for local-only service access. |
| `BACKEND_PORT` | `8086` | Port for the API and production-served frontend. |
| `FRONTEND_PORT` | `5176` | Vite port used by `start.bat --dev`. |
| `DATABASE_NAME` | `aac_assistant.db` | SQLite filename inside `DATA_DIR`. |
| `DATA_DIR` | `data` | Writable directory for the SQLite database, vector table, and model cache. |
| `JWT_SECRET_KEY` | `CHANGE_ME_TO_A_SECURE_RANDOM_STRING` in the template | Secret used to sign access and refresh tokens. The placeholder is replaced in place with a stable random value on first run. |
| `ALLOWED_ORIGINS` | `http://localhost:5176,http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:5176` | Comma-separated browser origins permitted by CORS. |
| `LOGS_DIR` | `logs` | Writable directory for application logs. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Base URL for the optional Ollama provider. |
| `OPENROUTER_API_KEY` | Empty | Optional API key for OpenRouter. Leave empty when unused. |
| `APP_NAME` | `AAC Assistant` | Display/application name used by the backend. |
| `APP_VERSION` | `2.0.0` | Application version reported by the backend and aligned with the Windows installer release. |
| `ENVIRONMENT` | `development` | Runtime mode. Use `production` for a deployed instance. |
| `DEFAULT_LOCALE` | `es` | Default locale for seeded and newly created application content. |
| `ALLOW_DB_RESET` | `false` | Enables the administrative database reset endpoint. Keep false outside disposable local development. |
| `AAC_SEED_SAMPLE_DATA` | `false` | Seeds demo users and boards when true. Keep false for a fresh production database. |
| `AAC_ENABLE_SYMBOL_IMAGE_BACKFILL` | `false` | Opt-in maintenance task that looks up and downloads missing symbol images during startup. Keep false for normal low-resource operation. |
| `AAC_SYMBOL_IMAGE_BACKFILL_LIMIT` | `100` | Maximum missing symbol images processed when backfill is enabled. Set to `0` to skip it. |
| `AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN` | `true` | Creates the bootstrap administrator when no administrator exists. |
| `AAC_BOOTSTRAP_ADMIN_USERNAME` | `admin1` | Username created by the first-run bootstrap. |
| `AAC_BOOTSTRAP_ADMIN_PASSWORD` | `Admin123` | Password created by the first-run bootstrap. Change it immediately after login. |

The application also accepts these operational environment variables, which
are intentionally not in the distributable template:

- `DATABASE_URL`: optional SQLAlchemy URL for tests or an explicitly managed
  database; otherwise SQLite uses `DATA_DIR/DATABASE_NAME`.
- `TESTING=1`: disables rate limiting for automated validation.
- `AAC_ASSISTANT_PORTABLE=1`: in a frozen onedir build, keeps `data/`, `logs/`,
  and `uploads/` beside the executable instead of using `%APPDATA%`.

## Optional voice setup

Voice input is optional. Browser speech synthesis remains available without
the extra; the extra supplies local speech-to-text through faster-whisper.

Install the extra in a source checkout:

```powershell
uv sync --extra voice
```

Windows administrators can also install the missing `faster-whisper` extra from
the in-app Settings -> Voice panel with one click when running from a source
checkout.

For development and tests, use both groups:

```powershell
uv sync --group dev --extra voice
```

The first transcription downloads the `tiny` faster-whisper model (about 39M parameters / 75 MB; the compatible CTranslate2 conversion of OpenAI's Whisper-tiny) by default. Administrators can choose `tiny`, `base`, `small`, `medium`, or `large-v3` in Settings → Voice. The selected model is cached in `data/models/`. Download it ahead of time with:

```powershell
uv run python -m src.aac_app.providers.model_download
```

The model cache is local runtime data and is ignored by Git. See
[`docs/voice.md`](docs/voice.md) for the browser recording and cache details.
The packaged installer does not bundle the model, so the first voice use on a
new installation needs network access.

## Test and lint

Install the development dependencies first:

```powershell
uv sync --group dev
npm --prefix src/frontend ci
```

Run the backend suite and Ruff:

```powershell
uv run pytest -q tests
uv run ruff check src tests
```

Run the frontend lint, Vitest suite, and production build:

```powershell
npm --prefix src/frontend run lint
npm --prefix src/frontend test -- --run
npm --prefix src/frontend run build
```

The Windows convenience runner executes the backend tests, Ruff, and frontend
tests:

```bat
run_tests.bat
```

The Playwright regression suite requires a running production server and the
seeded E2E users. Override their credentials when validating a differently
configured database:

```powershell
$env:E2E_ADMIN_USERNAME = "admin1"
$env:E2E_ADMIN_PASSWORD = "Admin123"
$env:E2E_STUDENT_USERNAME = "student1"
$env:E2E_STUDENT_PASSWORD = "Student123"
npm --prefix src/frontend exec playwright test
```

Setup fails clearly if those fixtures cannot authenticate; it does not create
random fallback users.

## Build a Windows package

Packaging requires the dev group, Node.js/npm, and Inno Setup 6.7.3:

```powershell
uv sync --group dev
npm --prefix src/frontend ci
build_package.bat
```

The build script reads the installer version directly from `installer.iss`,
then discovers Inno Setup from the standard per-user/system locations or
`PATH`. For a custom installation, set `INNO_SETUP_PATH` to the full path of
`ISCC.exe` before running the script (quoted environment values are accepted).

`build_package.bat` builds the frontend, creates the PyInstaller onedir output,
and compiles the Inno Setup installer. Outputs are:

- `dist\AAC_Assistant\AAC_Assistant.exe`
- `dist\AAC_Assistant_Setup_<version>.exe` (currently `2.0.0`)

The installer uses `%APPDATA%\AACAssistant` for writable data when installed
under Program Files. A portable onedir copy can keep `data/`, `logs/`, and
`uploads/` beside the executable. Uninstall removes application files and
disposable logs, but preserves the database and uploads.

## Repository layout

- `src/api/main.py`: FastAPI application and lifespan setup
- `src/api/routers/`: domain routers for authentication, boards, symbols,
  learning, settings, administration, and related APIs
- `src/api/deps/`: request dependencies for database sessions, auth,
  providers, and cached application settings
- `src/config.py`: typed `.env` settings and legacy configuration migration
- `src/aac_app/db.py`: process-wide SQLAlchemy engine and session factory
- `src/aac_app/schema.py`: idempotent SQLite schema creation and additive
  upgrades, which are the local app's migration strategy
- `src/aac_app/models/`: one SQLAlchemy model module per domain entity
- `src/aac_app/services/`: domain services
- `src/aac_app/services/learning/`: focused learning session, question,
  response, and summary modules
- `src/aac_app/providers/`: optional speech and HTTP AI providers
- `src/frontend/`: React/Vite application
- `scripts/`: database, setup, diagnostic, and server utilities
- `tests/`: automated backend tests
- `TEST_SCENARIOS/`: retained manual QA references; the automated suites are
  authoritative for repeatable validation

The detailed technical guide is
[`docs/01_PROJECT_GUIDE.md`](docs/01_PROJECT_GUIDE.md).

## Troubleshooting

### Port 8086 or 5176 is already in use

The launcher fails fast instead of taking over another process. Inspect the
listener in PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 8086 -State Listen
Get-NetTCPConnection -LocalPort 5176 -State Listen
```

Stop only a process you started, or change `BACKEND_PORT` and
`FRONTEND_PORT` in `.env` before launching. Keep the Vite port aligned with
`ALLOWED_ORIGINS` when using a browser development server.

### Migrating a legacy `env.properties`

`.env` is the canonical configuration file. If `.env` does not exist but a
legacy `env.properties` is present, the first run copies it to `.env` and
preserves the legacy file for rollback during this release. Review the new
file, then use `.env.example` as the reference for future installations.
The JWT secret is repaired in place, so existing tokens may need to be
refreshed after migration.

### Frontend assets are missing

Run:

```powershell
npm --prefix src/frontend ci
npm --prefix src/frontend run build
```

Then run `start.bat` again. A source checkout can also let the production
launcher build the frontend automatically when Node.js is available.

### Voice model download fails

Confirm the optional dependency is installed with `uv sync --extra voice` and
retry the model command. Ensure `data/models/` is writable and that the
machine can reach Hugging Face. The core keyboard, symbol, and browser speech
features work without the local transcription model.

### Bootstrap login does not work

Check `AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN`, username, and password in `.env`.
Bootstrap only creates an administrator when no administrator exists. For a
fresh disposable database, remove the database under `DATA_DIR` and start
again; never remove a production database to recover an account.

## Security

- Never commit `.env`, database files, logs, uploads, model caches, or
  Playwright authentication state.
- Use a unique `JWT_SECRET_KEY` and rotate credentials if a secret is exposed.
- Keep `ALLOW_DB_RESET=false` and `AAC_SEED_SAMPLE_DATA=false` for deployed
  instances.
- Change the bootstrap administrator password immediately after first login.
- The frontend uses the published React Router `8.3.0` package and its v8
  import split (`react-router` plus `react-router/dom`). The current production
  dependency audit reports zero vulnerabilities. Re-run `npm audit
  --omit=dev` after dependency changes.

## License

MIT. See [`LICENSE`](LICENSE).
