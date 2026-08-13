# Codex for Open Source — application draft

Final copy for the narrative fields of the
[Codex for Open Source](https://openai.com/form/codex-for-oss/) form. Private
values (legal name, email, OpenAI Organization ID) are **not** stored here; use
the placeholders below and fill them in at submission time.

> Character limits below were read from the current form (500 characters for
> each narrative field) and every answer is verified to fit, including spaces
> and punctuation. Re-verify on the live form before submitting, because field
> names and limits can change.

## Identifiers

| Field | Value |
| ----- | ----- |
| GitHub username | `rodhayl` |
| Repository URL | `https://github.com/rodhayl/AAC_ASSISTANT` |
| First name | `[MAINTAINER_FIRST_NAME]` |
| Last name | `[MAINTAINER_LAST_NAME]` |
| Email | `[CHATGPT_ACCOUNT_EMAIL]` |
| OpenAI Organization ID | `[OPENAI_ORG_ID]` — do not commit |
| Maintainer role | Primary maintainer (confirm ownership/maintenance before submitting) |
| I'm interested in | Codex Security, and API credits for my project |

## Narrative answers

### 1. Why does this repository qualify?

**Character count: 481 / 500**

> I am the primary maintainer of AAC Assistant, a local-first communication
> platform for people with speech and communication disabilities. I handle
> pull-request review, issue triage, releases, testing, and security. Adoption
> is currently limited (public repo, one maintainer), but the project addresses
> a genuine accessibility need: it keeps sensitive communication data under
> local control, with a real security surface across authentication, roles,
> uploads, and Windows packaging.

**Factual basis:** one maintainer (`rodhayl`) verified via GitHub API; MIT,
public; local-first architecture and security controls verified in the codebase.
Adoption is honestly stated as limited.

### 2. How will you use API credits for your project?

**Character count: 389 / 500**

> I would use API credits for open-source maintenance only: first-pass
> pull-request review, regression-test generation, issue triage, release-note
> and changelog drafting, and security remediation. I would review every output
> before acting and use credits only on this repository. Credits would not add
> cloud dependence to the core AAC experience, which stays local-first and
> offline-capable.

**Factual basis:** all uses are maintainer workflows, not new product features;
explicitly preserves local-first design.

### 3. Why does your project need Codex Security?

**Character count: 389 / 500**

> The project has a meaningful security surface for a local-first app:
> authentication and roles, JWT sessions, file uploads, dependency pinning,
> desktop packaging, and network exposure. Codex Security would help me review
> these paths, generate security regression tests, and remediate findings more
> thoroughly than a solo maintainer can alone, while I remain responsible for
> final decisions.

**Factual basis:** the enumerated surfaces are real and documented in
`docs/THREAT_MODEL.md` and `docs/SECURITY_ARCHITECTURE.md`.

### 4. Anything else we should know?

**Character count: 428 / 500**

> The project is early-stage with no verified external users or pilots, and I
> state that honestly. I have reproduced 647 backend tests, 214 frontend tests,
> and a Playwright suite against a real backend. The codebase is actively
> developed and hardened this cycle (loopback default, random bootstrap
> credentials, documented threat model). Codex would reduce the solo-maintainer
> burden of review, triage, documentation, and releases.

**Factual basis:** test totals reproduced from actual runs on 2026-08-13;
security changes landed in the same cycle.

## Claims still requiring maintainer confirmation

- Role: **Primary maintainer** — confirm you own the repository and are
  responsible for its maintenance.
- The private values listed under Identifiers must be supplied at submission.
