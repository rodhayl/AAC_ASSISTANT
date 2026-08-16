# Project metrics

A date-stamped snapshot of only verifiable facts. Figures below marked
"measured" were read directly from the repository or the GitHub public API on
the stated date. Nothing here is invented or estimated from memory.

Snapshot date: **2026-08-16**

## Repository

| Metric | Value | Source |
| ------ | ----- | ------ |
| Repository age | created 2026-02-10 | GitHub API (measured) |
| License | MIT | GitHub API (measured) |
| Visibility | public | GitHub API (measured) |
| Default branch | `main` | GitHub API (measured) |
| Stars | 0 | GitHub API (measured) |
| Forks | 0 | GitHub API (measured) |
| Open roadmap issues | 3 ([#5](https://github.com/rodhayl/AAC_ASSISTANT/issues/5), [#6](https://github.com/rodhayl/AAC_ASSISTANT/issues/6), [#9](https://github.com/rodhayl/AAC_ASSISTANT/issues/9) in milestone `v2.1.0`) | GitHub API (measured) |
| Closed roadmap issues | 2 ([#7](https://github.com/rodhayl/AAC_ASSISTANT/issues/7), [#8](https://github.com/rodhayl/AAC_ASSISTANT/issues/8) in milestone `v2.1.0`) | GitHub API (measured) |
| Published releases | 1 ([`v2.0.0`](https://github.com/rodhayl/AAC_ASSISTANT/releases/tag/v2.0.0)) | GitHub API (measured) |
| Contributors (GitHub) | 1 (`rodhayl`) | GitHub API (measured) |
| Watchers | 0 | GitHub API (measured) |

> Default branch: `main`. Dependabot may create temporary maintenance branches and pull requests.

## Code and tests (measured locally)

| Metric | Value |
| ------ | ----- |
| Backend tests (pytest) | 689 passed, 0 failed, 0 skipped (reproduced 2026-08-16; voice tests exercised with `faster-whisper` 1.2.1) |
| Backend test coverage (Coverage.py) | 82.07% statements (7,377/8,989), 66.14% branches (1,807/2,732), 78.36% combined total |
| Frontend unit/component tests (Vitest) | 256 passed (58 files, reproduced 2026-08-16) |
| Frontend test coverage (Vitest v8, honest src-only scope) | 52.12% statements, 46.17% branches, 48.21% functions, 54.20% lines (reproduced 2026-08-16) |
| End-to-end tests (Playwright, real backend) | 127 passed per browser — Chromium, Firefox, and WebKit each 127/127 (reproduced 2026-08-16 against a production build with seeded temporary SQLite data; includes the partner-overlay speech-to-text spec transcribing live through the local faster-whisper endpoint) |
| Automated accessibility scans (Axe Core) | 5 automated Axe analyses across 5 critical routes (/setup, /login, /communication, /learning, /settings) with 0 serious or critical violations |
| Python lint (`ruff`) | clean |
| Frontend lint / typecheck / build | clean; JS bundle 359.2 kB ≤ 450 kB budget, CSS 99.1 kB ≤ 150 kB budget |

> Test counts and coverage percentages are reproduced directly from machine-readable test outputs (`coverage.json`, Vitest summary, Playwright reporter).
>
> Frontend coverage is measured against the full `src/**/*.{ts,tsx}` tree
> (excluding only type declarations and the entry module), which counts files
> that no unit test imports. GUI-heavy pages are additionally exercised by the
> Playwright e2e suite. The previous snapshots used a narrower effective scope,
> so the lower percentages here reflect a wider, more honest measurement, not a
> loss of coverage.

## Supported platforms

- Windows 10/11 (packaged installer + portable onedir).
- Source checkout on any OS with Python 3.13 or 3.14 and Node.js 22.22+.

## Known downstream use

**No verifiable evidence of external users, clinics, schools, pilots, or
deployments.** This project does not claim any adoption. A standardized evaluation
protocol is published in [`docs/PILOT_GUIDE.md`](PILOT_GUIDE.md); if the maintainer
conducts or verifies a real-world evaluation, evidence will be documented here.

## CI status

CI runs backend tests with coverage, frontend tests with coverage, lint, build, production E2E
(Chromium, Firefox, and WebKit), Axe accessibility scans, and Windows packaging on GitHub Actions.
See `.github/workflows/ci.yml`.

## Unavailable information

- Historical package download telemetry (downloads are tracked exclusively via GitHub Releases asset metrics).

## Future goals

These are goals, not facts: real-world pilot evaluations following `docs/PILOT_GUIDE.md`;
manual screen-reader testing with assistive technology specialists (Issue #5);
switch/scanning access implementation (Issue #6).
