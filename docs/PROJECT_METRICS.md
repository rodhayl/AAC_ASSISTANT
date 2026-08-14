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
| Open issues | 5 | GitHub API (measured) |
| Open pull requests | 0 | GitHub API (measured) |
| Published releases | 1 ([`v2.0.0`](https://github.com/rodhayl/AAC_ASSISTANT/releases/tag/v2.0.0)) | GitHub API (measured) |
| Contributors (GitHub) | 1 (`rodhayl`) | GitHub API (measured) |
| Watchers | 0 | GitHub API (measured) |
| Branches | `main` | GitHub API (measured) |

> `main` contains the latest coherent and tested product state following the merge of Pull Requests [#4](https://github.com/rodhayl/AAC_ASSISTANT/pull/4) and [#10](https://github.com/rodhayl/AAC_ASSISTANT/pull/10), and publication of release [`v2.0.0`](https://github.com/rodhayl/AAC_ASSISTANT/releases/tag/v2.0.0).

## Code and tests (measured locally)

| Metric | Value |
| ------ | ----- |
| Backend tests (pytest) | 653 passed, 2 skipped (reproduced 2026-08-14) |
| Backend test coverage (Coverage.py) | 80.92% statements (7,117/8,795), 64.75% branches (1,743/2,692), 77.13% combined total |
| Frontend unit/component tests (Vitest) | 227 passed (48 files, reproduced 2026-08-14) |
| Frontend test coverage (Vitest v8) | 70.49% statements (3,023/4,288), 60.28% branches (1,791/2,971), 64.54% functions (701/1,086), 72.95% lines (2,751/3,771) |
| End-to-end tests (Playwright, real backend) | 113 passed (3 auth setup + 105 functional specs + 5 automated Axe analyses) |
| Automated accessibility scans (Axe Core) | 5 automated Axe analyses across 5 critical routes (/setup, /login, /communication, /learning, /settings) with 0 serious or critical violations |
| Python lint (`ruff`) | clean |
| Frontend lint / typecheck / build | clean; JS bundle 344.5 kB ≤ 450 kB budget, CSS 97.6 kB ≤ 150 kB budget |

> Test counts and coverage percentages are reproduced directly from machine-readable test outputs (`coverage.json`, Vitest summary, Playwright reporter).

## Supported platforms

- Windows 10/11 (packaged installer + portable onedir).
- Source checkout on any OS with Python 3.13+ and Node.js 20+.

## Known downstream use

**No verifiable evidence of external users, clinics, schools, pilots, or
deployments.** This project does not claim any adoption. A standardized evaluation
protocol is published in [`docs/PILOT_GUIDE.md`](PILOT_GUIDE.md); if the maintainer
conducts or verifies a real-world evaluation, evidence will be documented here.

## CI status

CI runs backend tests with coverage, frontend tests with coverage, lint, build, production E2E,
Axe accessibility scans, and Windows packaging on GitHub Actions. See `.github/workflows/ci.yml`.

## Unavailable information

- Historical package download telemetry (downloads are tracked exclusively via GitHub Releases asset metrics).

## Future goals

These are goals, not facts: real-world pilot evaluations following `docs/PILOT_GUIDE.md`;
manual screen-reader testing with assistive technology specialists (Issue #5);
switch/scanning access implementation (Issue #6).
