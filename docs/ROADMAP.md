# Roadmap

This roadmap reflects current maintainer plans. Items are goals, not
commitments, and may change as the project evolves.

## Completed

- Local-first FastAPI + React architecture with role-based access.
- Communication boards, symbol library, and sentence building.
- Learning sessions with adaptive questions and achievements.
- Local speech-to-text (faster-whisper, bundled in the Windows installer).
- Offline semantic-search and voice model bundling.
- Windows installer with safe upgrade/close behavior.
- Production E2E suite exercising core flows against the real backend.

## In progress

- Security and documentation hardening for maintainability and review.
- Expanding real-backend end-to-end coverage and removing test mocks where the
  backend can be exercised directly.

## Planned

- Switch-access and scanning input driven by dwell-time preferences.
- `prefers-reduced-motion` support across animations.
- A documented screen-reader test pass and WCAG 2.2 AA target.
- Formal semantic versioning with published releases and checksums.
- Optional multi-user network deployment guidance (explicit opt-in only).

## Not planned

- Cloud-hosted core communication (the core experience stays local-first).
- Mandatory telemetry or analytics.
- Requiring an internet connection for basic AAC use.
