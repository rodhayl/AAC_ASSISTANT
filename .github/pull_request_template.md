## Motivation

Why is this change needed?

## Changes

A concise summary of what changed.

## Test evidence

- [ ] `uv run ruff check src tests scripts`
- [ ] `uv run python scripts/check_dependency_usage.py`
- [ ] `uv run pip-audit --requirement requirements.txt --strict --progress-spinner off`
- [ ] `uv run pip-audit --local --strict --progress-spinner off`
- [ ] `uv run python -m compileall -q src scripts`
- [ ] `uv run pytest -q`
- [ ] `npm --prefix src/frontend run typecheck`
- [ ] `npm --prefix src/frontend run lint`
- [ ] `npm --prefix src/frontend audit --omit=dev --audit-level=moderate`
- [ ] `npm --prefix src/frontend audit --audit-level=high`
- [ ] `npm --prefix src/frontend run test -- --run`
- [ ] `npm --prefix src/frontend run build`

List any manual or end-to-end testing performed.

## Security and privacy

Describe any security, authorization, or data-handling impact. If this touches
auth, uploads, network exposure, or dependencies, explain how risks were
addressed.

## Migration and rollback

Any schema/data migration or rollback considerations.
