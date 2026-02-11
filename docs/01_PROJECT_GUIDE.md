# Project Guide

This guide consolidates configuration, API usage, security/privacy requirements, operations, and utility tooling for AAC Assistant.

## 1. Prerequisites

- Python 3.10+
- Node.js 20+
- npm 10+

## 2. Configuration

1. Copy `env.properties.example` to `env.properties`.
2. Set a strong `JWT_SECRET_KEY`.
3. Keep `ALLOW_DB_RESET=false` for public/production deployments.
4. Keep `AAC_SEED_SAMPLE_DATA=false` for public/production deployments.

Hardened baseline:

```properties
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8086
FRONTEND_PORT=5176
JWT_SECRET_KEY=REPLACE_WITH_STRONG_RANDOM
ENVIRONMENT=production
FORCE_HTTPS=true
SECURE_COOKIES=true
ALLOW_DB_RESET=false
AAC_SEED_SAMPLE_DATA=false
AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN=true
AAC_BOOTSTRAP_ADMIN_USERNAME=admin1
AAC_BOOTSTRAP_ADMIN_PASSWORD=Admin123
```

Frontend optional env template: `src/frontend/.env.example`.

## 3. Run and Validate

Install:

```bash
python -m pip install -r requirements.txt
npm --prefix src/frontend ci
```

Run (development):

```bash
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8086
npm --prefix src/frontend run dev
```

Validation:

```bash
python -m pytest -q tests
python -m flake8 src tests
npm --prefix src/frontend run lint
npm --prefix src/frontend test -- --run
npm --prefix src/frontend run build
python -m pip check
python -m pip_audit -r requirements.txt
npm --prefix src/frontend audit
```

## 4. API Overview

Local API base URL: `http://localhost:8086/api`

Interactive docs:

- Swagger: `http://localhost:8086/docs`
- ReDoc: `http://localhost:8086/redoc`

Main endpoint groups:

- `/api/auth/*`
- `/api/boards/*`
- `/api/learning/*`
- `/api/achievements/*`
- `/api/settings/*`
- `/api/notifications/*`
- `/api/analytics/*`
- `/api/guardian-profiles/*`
- `/api/collab/*`

Authenticated requests use `Authorization: Bearer <token>`.

## 5. Security and Privacy

Never commit:

- `env.properties`
- `.env` files with secrets
- Playwright auth state
- private keys/certs
- DB dumps and local artifacts

Keep only safe templates:

- `env.properties.example`
- `src/frontend/.env.example`

RBAC model:

- `admin`: full system management
- `teacher`: managed educational scope
- `student`: self-scope operations

Core enforcement paths:

- `src/api/dependencies.py`
- `src/api/routers/`

## 6. Utility Scripts

Project utility scripts are grouped under `scripts/` and cover:

- DB seeding and user management
- dependency checks and setup helpers
- schema validation and migrations
- diagnostics and local verification helpers

Run scripts directly with `python scripts/<script>.py --help`.

## 7. No-History Export and Publish

1. Build `./_export/` from the working tree.
2. Exclude local/generated files: `.git`, secrets, caches, logs, DB files, runtime uploads, `node_modules`, build output.
3. Verify `_export` contains no secrets or runtime artifacts.
4. Initialize and push from `_export` as a new repository.
