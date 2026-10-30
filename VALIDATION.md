# Validation — 30 October 2026

Base: `750dd4ee2384a5306f7319838566aba665a38971` (12 February 2026), with the
small changes listed in SNAPSHOT_CHANGES.md. Python 3.12.14, Node v24.22.1.

## Passed

- Original React frontend: `npm run build` (TypeScript project build + Vite 7.2.4).
- Original focused frontend test: `npm test -- --run tests/learningSymbolAudio.test.tsx`: 3/3 tests.
- JWT-focused tests: `python -m unittest discover -s tests -p 'test_snapshot_jwt_unit.py'`: 10/10 tests.
- Ollama adapter-focused offline tests: `python -m unittest discover -s tests -p 'test_snapshot_ollama_unit.py'`: 5/5 tests.
- Startup-focused offline tests: 3/3 (launcher config default/override, Python
  entrypoint configuration, Windows-script source defaults). Combined focused
  JWT/Ollama/startup suite: 18/18. Windows scripts were inspected, not executed.
- Python syntax compilation of source/scripts.
- Bootstrap checks: missing password rejected, explicit synthetic password creates an administrator, existing administrator preserved; password never printed.
- Actual backend startup, synthetic SQLite fixtures, compiled frontend served.
- Real ASGI HTTP integration using FastAPI TestClient (no endpoint response mocks):
  health, compiled frontend, login, profile, AI settings, silent preferences,
  board creation, symbol list, two symbol additions, board reload, enable AI,
  real Beam suggestions, no pre-application mutation, apply one, reload,
  new login, and persisted board retrieval. All 18 requests returned HTTP 200.
- The backend called `https://ollama.com/api/chat`, model `beam:cloud`, received
  HTTP 200 and three valid items: Water, Apple, Banana. Saved board had two
  symbols before generation and three after an explicit application step.
- Encoded static path traversal probe returned HTTP 404.

## Not claimed / not run

- Browser GUI: NOT_RUN. Chromium launch was blocked by the environment's socket
  policy. Sandbox protections were not disabled. API integration is not GUI E2E.
- No complete pytest/Vitest/Playwright suite, clinical assessment, accessibility
  certification, security audit, Windows installer acceptance, or microphone/
  speech-output test was performed.
- Local Whisper, Torch/embedding models, FAISS semantic retrieval and local
  Ollama inference were not installed/downloaded/tested. Optional provider
  objects can report initialized even when their native packages are unavailable;
  `/ready` alone is not evidence that voice/vector features work.
- Python core versions are pinned in requirements-core.txt as tested; this is
  not a statement that every dependency has passed a vulnerability audit.
- Native/optional workflows remain historical source, not validated artifacts.

Only synthetic data was used. The runtime provider credential was held in the
server process environment and is not present in this source, tests or evidence.
