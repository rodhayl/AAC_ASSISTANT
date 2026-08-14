# Contributing

Thank you for considering a contribution to AAC Assistant. This project builds
communication software for people with speech and communication disabilities,
so correctness and safety matter more than velocity.

## Code of Conduct

All participants must follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Getting started

1. Read the [README](../README.md) and the [project guide](../docs/01_PROJECT_GUIDE.md).
2. Set up the development environment:

   ```powershell
   install_dependencies.bat
   ```

   Or manually:

   ```powershell
   uv sync --group dev
   npm --prefix src/frontend ci
   ```

## Development workflow

1. Create a feature or fix branch from `main`.
2. Make small, focused, reviewable changes.
3. Run the checks before opening a pull request:

   ```powershell
   uv run ruff check src tests scripts
   uv run python -m compileall -q src scripts
   uv run pytest -q
   npm --prefix src/frontend run typecheck
   npm --prefix src/frontend run lint
   npm --prefix src/frontend run test -- --run
   npm --prefix src/frontend run build
   ```

4. Add or update tests for every meaningful change.
5. Open a pull request and describe the motivation, user-visible change, and
   test evidence.

## Style and conventions

- Backend follows `ruff` formatting/linting. No `print()` or `console.log`
  debugging output in production code.
- Frontend follows ESLint and the existing React/TypeScript conventions.
- Prefer deleting dead code and reusing existing components over adding new
  abstractions.
- Keep the core AAC experience local-first and offline-capable.

## Testing guidance

- Prefer the lowest-cost test level that catches the defect.
- End-to-end tests exercise the real backend where possible; mocks are only
  acceptable for genuinely external dependencies (e.g., third-party LLMs).

## Security

Report vulnerabilities privately. See [SECURITY.md](SECURITY.md).
