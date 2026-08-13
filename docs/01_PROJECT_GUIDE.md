# AAC Assistant project guide

This guide describes the current local-first architecture, configuration,
operations, API surface, and privacy requirements. For the shortest setup
path, see the root [`README.md`](../README.md).

## 1. Prerequisites and commands

Use Python 3.13+, [uv](https://docs.astral.sh/uv/), Node.js 20+, and npm 10+.
The root scripts are the supported Windows entry points:

```bat
install_dependencies.bat
start.bat
start.bat --dev
run_tests.bat
build_package.bat
```

The equivalent development commands are:

```powershell
uv sync --group dev
npm --prefix src/frontend ci
uv run pytest -q tests
uv run ruff check src tests
npm --prefix src/frontend run lint
npm --prefix src/frontend test -- --run
npm --prefix src/frontend run build
```

Production uses one uvicorn process on port `8086` to serve the API and the
built React application. `start.bat --dev` starts uvicorn on `8086` and Vite on
`5176`.

## 2. Configuration

`.env` is the canonical runtime configuration. Start from `.env.example`.
`src/config.py` loads typed settings with pydantic-settings, creates the file
when needed, and replaces a JWT placeholder with a stable random secret.

For one release, an existing legacy `env.properties` is copied to `.env` when
`.env` is absent and is preserved for rollback. New deployments must use
`.env.example` and `.env`.

Important production settings:

```dotenv
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8086
FRONTEND_PORT=5176
ENVIRONMENT=production
JWT_SECRET_KEY=REPLACE_WITH_A_LONG_RANDOM_SECRET
ALLOW_DB_RESET=false
AAC_SEED_SAMPLE_DATA=false
AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN=true
AAC_BOOTSTRAP_ADMIN_USERNAME=admin1
AAC_BOOTSTRAP_ADMIN_PASSWORD=Admin123
```

The README contains the complete key-by-key configuration reference.
`TESTING=1` is an operational environment variable for automated validation;
it disables request rate limiting. `DATABASE_URL` may be supplied for isolated
tests, but normal deployments use SQLite at `DATA_DIR/DATABASE_NAME`.

## 3. Architecture

### Application entry point and API

- `src/api/main.py` creates the FastAPI application, configures lifespan
  startup, mounts static assets, and registers routers.
- `src/api/routers/` contains focused domain routers for authentication,
  boards, symbols, learning, settings, administration, analytics,
  notifications, exports, and providers.
- `src/api/deps/` is the request dependency package:
  - `auth.py` provides current-user and role checks.
  - `db.py` provides request-scoped database sessions.
  - `providers.py` creates optional AI provider integrations lazily.
  - `settings.py` reads cached database-backed application settings.
- `src/api/schemas.py` defines request and response models.

### Database and models

- `src/aac_app/db.py` owns the process-wide SQLAlchemy engine and session
  factory. Services and routers receive sessions rather than opening hidden
  sessions for request work.
- `src/aac_app/models/` is a package with one module per domain entity.
  `models/__init__.py` imports the modules once so all tables are registered
  in the shared `Base.metadata`.
- `src/aac_app/schema.py` is the SQLite schema strategy. Startup first creates
  missing ORM tables, then applies idempotent additive column upgrades for
  databases from older releases. There is no separate migration service to
  run for the local desktop application.
- `src/aac_app/seed.py` performs core achievement/bootstrap setup and only
  creates demo users and boards when `AAC_SEED_SAMPLE_DATA=true`.

### Services and providers

- `src/aac_app/services/` contains domain operations for boards, symbols,
  authentication, achievements, analytics, notifications, and translations.
- `src/aac_app/services/learning/` is the focused learning package. It splits
  session lifecycle, question generation, response handling, summaries, and
  shared prompt helpers into small modules, with
  `LearningCompanionService` as the public service facade.
- `src/aac_app/providers/` contains optional HTTP AI providers and the lazy
  faster-whisper speech provider. The browser handles speech synthesis and
  microphone capture; server-side audio devices are not required.
- Semantic search uses fastembed embeddings and sqlite-vec in the SQLite
  database. Runtime model caches belong under `data/models/` and are never
  committed.

### Frontend

`src/frontend/` is a React 19, Vite 7, TypeScript, Tailwind CSS, and Zustand
application. Route-level lazy loading keeps the production bundle small.
Vite is a development server only; the production backend serves
`src/frontend/dist/` as the SPA.

Learning-session question flow (`src/frontend/src/components/learning/` and
`src/frontend/src/store/learningStore.ts`):

- After a session starts, the first adaptive question is auto-requested. After
  each successful answer (text, voice, or symbols), the next question loads
  after a short reveal delay so the correct answer stays highlighted on the
  card (green = correct, red = wrong pick).
- Each learning mode has an `auto_ask_enabled` flag (see
  `src/aac_app/models/learning.py` and the editor in
  `src/frontend/src/pages/Settings/LearningModesTab.tsx`). Conversational modes
  can turn auto-asking off; the manual "New question" button still works.
  The question flow also pauses while symbol-first view is active.
- The chat header shows live progress chips (comprehension score, correct
  count, current difficulty) fed by the answer responses, and an "End Session"
  button that opens the session summary modal (score, questions answered,
  correct answers, and the LLM-generated summary from
  `POST /api/learning/{id}/end`).

## 4. API overview

Local API base URL: `http://127.0.0.1:8086/api`

Interactive documentation:

- Swagger: `http://127.0.0.1:8086/docs`
- ReDoc: `http://127.0.0.1:8086/redoc`
- Health: `http://127.0.0.1:8086/api/health`

Main endpoint groups:

- `/api/auth/*`
- `/api/boards/*`
- `/api/learning/*`
- `/api/learning-modes/*`
- `/api/achievements/*`
- `/api/settings/*`
- `/api/notifications/*`
- `/api/analytics/*`
- `/api/guardian-profiles/*`
- `/api/collab/*`
- `/api/providers/*`
- `/api/data/*`

Authenticated requests use `Authorization: Bearer <token>`. The role model is:

- `admin`: full system and user management
- `teacher`: managed educational scope and assigned students
- `student`: own account, assigned boards, and self-scope operations

## 5. Security, privacy, and repository hygiene

Never commit:

- `.env` or other local secret files
- `env.properties` from an installation
- database files, logs, uploads, or model caches
- Playwright authentication state
- private keys, certificates, or exported user data

`.env.example` is the only runtime configuration template intended for new
installations. `.gitignore` also excludes `data/`, `logs/`, `dist/`, `build/`,
uploads, local caches, and dependency directories.

Core enforcement paths are `src/api/deps/` and `src/api/routers/`. Keep
`ALLOW_DB_RESET=false`, `AAC_SEED_SAMPLE_DATA=false`, and a unique
`JWT_SECRET_KEY` for any shared or deployed instance. Change the bootstrap
administrator password immediately after first login.

## 6. Utilities and manual QA

Project utilities under `scripts/` cover setup, bootstrap administration,
database inspection, migration helpers, diagnostics, and server preparation.
Run a utility's help command with:

```powershell
uv run python scripts/<script>.py --help
```

`TEST_SCENARIOS/` is intentionally retained as a manual QA reference for
role-oriented walkthroughs. It is not part of the automated test collection;
the pytest, Vitest, and Playwright suites are the repeatable validation
sources.

## 7. Packaging and release checks

The release flow is:

1. `uv sync --group dev`
2. `npm --prefix src/frontend ci`
3. `build_package.bat`

PyInstaller creates an onedir application and Inno Setup creates the Windows
installer. The optional speech model is downloaded after installation rather
than bundled. Installed copies use `%APPDATA%\AACAssistant` for writable data
when the application is under Program Files; portable copies can keep runtime
data beside the executable.

Before a release, verify:

```powershell
uv run pytest -q tests
uv run ruff check src tests
npm --prefix src/frontend run lint
npm --prefix src/frontend test -- --run
npm --prefix src/frontend run build
git ls-files
```

No tracked file should exceed 50 MB, and no tracked path should contain a
downloaded speech or embedding model.
