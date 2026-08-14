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
- Interactive first-run administrator onboarding flow (`/setup`) with loopback restriction.
- Security and documentation hardening (threat modeling, privacy guidelines, zero default credentials).
- Production E2E suite exercising core flows against the real backend.
- Initial public release (`v2.0.0`) with Windows installer, portable package, SHA-256 checksums, and SBOM.

## Planned

- Switch-access and scanning input driven by dwell-time preferences.
- Comprehensive `prefers-reduced-motion` support across all UI animations.
- Documented screen-reader validation pass and formal accessibility testing.
- Documented pilot / user-validation guide for clinical and specialist trials.
- Hardened remote deployment security guidance (for operators opting into network binding).

## Not planned

- Cloud-hosted core communication (the core experience stays local-first).
- Mandatory telemetry or analytics.
- Requiring an internet connection for basic AAC use.
