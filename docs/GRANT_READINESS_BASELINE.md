# Grant readiness baseline

Private working notes for the OpenAI Codex for Open Source application. This
file contains no credentials, secrets, or private values.

## Repository baseline (verified 2026-08-13)

- **Owner/repo:** `rodhayl/AAC_ASSISTANT` (public, MIT).
- **Default branch:** `main` (older, one consolidated commit).
- **Active branches:** `020826_improvements` (47 commits ahead of `main`),
  `080826_continuation` (85 commits ahead of `main`; `020826_improvements` is
  an ancestor of it).
- **Pull request `#1`:** `020826_improvements` → `main`, open, 47 commits.
- **Releases:** none. **Tags:** none. **Stars:** 0. **Forks:** 0.
  **Contributors:** 1 (`rodhayl`). **Open issues:** 1.
- **Workflows:** `ci.yml` (backend, frontend, e2e-production, packaging-windows).

## Branch decision

`080826_continuation` is the latest coherent and tested product state and
contains `020826_improvements` in its history. The readiness work is based on
`080826_continuation` via the branch `chore/codex-oss-readiness`. Pull request
`#1` is superseded but is left untouched until the replacement PR is approved.

## Security findings addressed

1. **Network exposure** — `BACKEND_HOST` defaulted to `0.0.0.0`. Changed to
   `127.0.0.1`; remote bind is now an explicit, documented opt-in.
2. **Predictable bootstrap credentials** — `admin1`/`Admin123` was the
   documented development default. First run now generates a random one-time
   password stored in `.env`; production refuses to bootstrap without an
   explicit strong password; the password is no longer printed.
3. **Mass-assignment in `update_user`** — now validates role allowlist, email
   format/uniqueness, and boolean active flag (fixed earlier this session).

## Secret scan

A secret scan over the reachable git history found no real secrets — only test
placeholders and documented development defaults. No API keys, tokens, private
emails, or certificates are committed.

## Form fields (read from the current form)

Field names, limits, and conditions are recorded in
`docs/CODEX_FOR_OSS_APPLICATION.md` alongside final copy. Character limits are
enforced per answer.
