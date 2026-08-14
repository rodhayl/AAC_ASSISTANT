# Project metrics

A date-stamped snapshot of only verifiable facts. Figures below marked
"measured" were read directly from the repository or the GitHub public API on
the stated date. Nothing here is invented or estimated from memory.

Snapshot date: **2026-08-14**

## Repository (pre-PR dated snapshot)

| Metric | Value | Source |
| ------ | ----- | ------ |
| Repository age | created 2026-02-10 | GitHub API (measured) |
| License | MIT | GitHub API (measured) |
| Visibility | public | GitHub API (measured) |
| Default branch | `main` | GitHub API (measured) |
| Stars | 0 | GitHub API (measured) |
| Forks | 0 | GitHub API (measured) |
| Open issues | 0 | GitHub API (measured) |
| Open pull requests | 0 (prior to PR creation) | GitHub API (measured) |
| Published releases | none | GitHub API (measured) |
| Contributors (GitHub) | 1 (`rodhayl`) | GitHub API (measured) |
| Watchers | 0 | GitHub API (measured) |
| Branches | `main`, `020826_improvements`, `080826_continuation`, `chore/codex-oss-readiness`, `chore/repository-cleanup-and-pr` | GitHub API (measured) |

> The cleanup and readiness branch `chore/repository-cleanup-and-pr` contains
> the latest coherent and tested product state, consolidating all security,
> accessibility, CI, packaging, and structural improvements.

## Code and tests (measured locally)

| Metric | Value |
| ------ | ----- |
| Backend tests (pytest) | 651 passed (reproduced 2026-08-14) |
| Frontend unit/component tests (Vitest) | 224 passed (47 files, reproduced 2026-08-14) |
| End-to-end tests (Playwright, real backend) | 108 passed |
| Python lint (`ruff`) | clean |
| Frontend lint / typecheck / build | clean; JS bundle 344.5 kB ≤ 450 kB budget, CSS 96.9 kB ≤ 150 kB budget |

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
