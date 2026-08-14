# Project metrics

A date-stamped snapshot of only verifiable facts. Figures below marked
"measured" were read directly from the repository or the GitHub public API on
the stated date. Nothing here is invented or estimated from memory.

Snapshot date: **2026-08-14**

## Repository

| Metric | Value | Source |
| ------ | ----- | ------ |
| Repository age | created 2026-02-10 | GitHub API (measured) |
| License | MIT | GitHub API (measured) |
| Visibility | public | GitHub API (measured) |
| Default branch | `main` | GitHub API (measured) |
| Stars | 0 | GitHub API (measured) |
| Forks | 0 | GitHub API (measured) |
| Open issues | 1 | GitHub API (measured) |
| Open pull requests | 1 (`#1`, `020826_improvements` → `main`) | GitHub API (measured) |
| Published releases | none | GitHub API (measured) |
| Contributors (GitHub) | 1 (`rodhayl`) | GitHub API (measured) |
| Watchers | 0 | GitHub API (measured) |
| Branches | `main`, `020826_improvements`, `080826_continuation`, `chore/codex-oss-readiness` | GitHub API (measured) |

> The active development branch `chore/codex-oss-readiness` contains the latest
> coherent and tested product state and supersedes `080826_continuation`
> (which is an ancestor of it). This is a maintainer statement based on the
> commit graph.

## Code and tests (measured locally)

| Metric | Value |
| ------ | ----- |
| Backend tests (pytest) | 647 passed (reproduced on 2026-08-13) |
| Frontend unit/component tests (Vitest) | 222 passed (46 files, reproduced 2026-08-14) |
| End-to-end tests (Playwright, real backend) | 108 passed (reproduced 2026-08-14) |
| Python lint (`ruff`) | clean |
| Frontend lint / typecheck / build | clean; JS bundle 341.6 kB ≤ 450 kB budget |

> Test counts are reproduced from actual runs, not copied from documentation.
> The E2E total varies slightly with which optional specs are enabled.

## Supported platforms

- Windows 10/11 (packaged installer + portable onedir).
- Source checkout on any OS with Python 3.13+ and Node.js 20+.

## Known downstream use

**No verifiable evidence of external users, clinics, schools, pilots, or
deployments.** This project does not claim any adoption. A pilot guide is not
yet published; if the maintainer chooses to run a pilot, adoption would then be
documented here with evidence.

## CI status

CI runs backend tests, frontend tests, lint, build, production E2E, and Windows
packaging on GitHub Actions. See `.github/workflows/ci.yml`.

## Unavailable information

- Coverage percentage (not currently measured).
- Package download counts (no published releases).

## Future goals

These are goals, not facts: first published release with checksums and SBOM;
a documented pilot program; expanded accessibility testing.
