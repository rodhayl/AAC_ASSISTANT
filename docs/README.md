# AAC Assistant Documentation

Welcome to the AAC Assistant documentation index. This directory contains detailed architectural, operational, security, accessibility, and governance documentation.

For high-level project overview and quick-start instructions, see the root [README.md](../README.md).

---

## Documentation Index

### 1. Getting Started & Architecture

- **[Project Guide](01_PROJECT_GUIDE.md)** — Architectural design, configuration reference, backend/frontend stack details, and operations.
- **[Voice Input Guide](voice.md)** — Optional speech-to-text integration using `faster-whisper` and offline models.
- **[Security Architecture](SECURITY_ARCHITECTURE.md)** — Authentication mechanisms (Argon2), authorization, JWT tokens, credential versioning, and file validation.
- **[Threat Model](THREAT_MODEL.md)** — Security boundaries, protected assets, threat analysis, and residual risk mitigations.

### 2. Privacy & Accessibility

- **[Privacy and Data Handling](PRIVACY_AND_DATA.md)** — Local-first design, data persistence in SQLite/uploads, zero-telemetry policy, and operator controls.
- **[Accessibility Guide](ACCESSIBILITY.md)** — Accessibility features, switch/keyboard navigation, dwell selection, screen reader support, and known limitations.

### 3. Testing & Quality Assurance

- **[Test Scenarios Overview](test_scenarios/execute_all_scenarios.md)** — Role-oriented QA validation guide and scenario overview.
- **[Test Scenarios Collection](test_scenarios/)** — 10 detailed role-based scenarios covering Admin, Teacher, and Student user workflows.
- **[Frontend npm Audit](frontend-npm-audit.md)** — Production dependency vulnerability audit record.

### 4. Packaging & Releases

- **[Release Readiness Runbook](RELEASE_READINESS.md)** — Operational checklist, automated gate requirements, and recovery procedures.
- **[Release Notes](RELEASE_NOTES.md)** — Detailed release notes for v2.0.0.
- **[Changelog](../CHANGELOG.md)** — High-level release history across versions.
- **[Project Roadmap](ROADMAP.md)** — Planned features, technical milestones, and future work.

### 5. Project Governance & Community

- **[Contributing Guidelines](../.github/CONTRIBUTING.md)** — How to contribute code, report bugs, and submit improvements.
- **[Code of Conduct](../.github/CODE_OF_CONDUCT.md)** — Community standards and enforcement guidelines.
- **[Security Policy](../.github/SECURITY.md)** — Supported versions and private vulnerability reporting instructions.
- **[Support Guide](../.github/SUPPORT.md)** — Support resources, issue reporting, and discussion channels.

### 6. Project Status & Metrics

- **[Project Metrics](PROJECT_METRICS.md)** — Date-stamped, verifiable repository and codebase metrics snapshot.
- **[Plans & ADRs](plans/)** — Historical architectural plans, refactoring notes, and task records.
