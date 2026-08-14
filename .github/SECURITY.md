# Security Policy

AAC Assistant stores highly personal communication content locally, so we treat
security reports seriously. Thank you for helping keep users safe.

## Supported versions

We support the most recent release on the default branch and the active
development branch that will become the next release. Older releases and
development snapshots receive fixes only when a maintainer backports them.

| Version | Supported |
| ------- | --------- |
| Latest release (see [releases](https://github.com/rodhayl/AAC_ASSISTANT/releases)) | :white_check_mark: |
| Active development branch | :white_check_mark: (best-effort) |
| Older releases / feature branches | :x: |

The project does not currently publish semantic-versioned releases. Until a
release is published, "supported" means the tip of the default branch.

## Reporting a vulnerability

Please report vulnerabilities privately. Do **not** open a public issue with
exploit details or personal data.

**Private reporting channel:** use GitHub's
[private vulnerability reporting](https://github.com/rodhayl/AAC_ASSISTANT/security/advisories/new)
(if enabled on the repository), or email the maintainer directly. Do not post
exploits, proofs of concept, database files, tokens, or personally identifiable
information in public issues, pull requests, or discussions.

### What to include

- Affected component (backend, frontend, launcher, installer, dependency).
- Affected version or commit.
- A concise description of the issue and its potential impact.
- Steps to reproduce, including any minimal payloads.
- Whether you believe the issue is already known.
- Your suggested timeline or constraints, if any.

### What to expect

- We acknowledge the report as soon as practical.
- We validate the issue and agree on a severity with you.
- We fix confirmed issues on the supported branch and publish an advisory.
- We credit reporters unless you ask to remain anonymous.

We do not promise a fixed turnaround time. This is a small, volunteer-maintained
project, so response times depend on maintainer availability.

## Out of scope

- Issues that require physical access to the operator's machine.
- Issues in a third-party service (Ollama, OpenRouter, LM Studio) outside this
  repository.
- Social-engineering or denial-of-service attacks against a local, single-user
  installation with no remote exposure.

## Security model in brief

AAC Assistant is a **local-first** desktop application. It binds to
`127.0.0.1` by default, stores data in local files, and does not require a
cloud service for core communication. See
[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) and
[docs/SECURITY_ARCHITECTURE.md](docs/SECURITY_ARCHITECTURE.md) for details.
