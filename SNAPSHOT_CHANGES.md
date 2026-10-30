# Snapshot changes

No September–October private product implementation was imported.

## Small source changes from the selected February commit

1. `src/aac_app/providers/ollama_provider.py`: runtime Cloud bearer authentication
   restricted to exactly `https://ollama.com`; redirects disabled; provider error
   body omitted from error logging; prompt/response text snippets are not logged. Existing local adapter/API behavior retained.
2. `src/aac_app/utils/jwt_utils.py` and one refresh call in
   `src/api/routers/auth.py`: reject invalid effective keys, issue explicitly typed
   access tokens, and require the correct token type when decoding. Refresh remains
   functional; earlier untyped sessions require a new login.
3. `src/config.py`, `src/frontend/vite.config.ts`, `env.properties.example`:
   loopback defaults instead of all-interface binding, including the Python/Windows
   launchers; explicit host configuration remains supported. Windows installation
   scripts no longer generate a preset bootstrap password. The historical guide
   documents these local-demo settings, without a production-hardening claim.
4. `src/api/main.py`: resolve static paths and require containment within the built
   frontend directory before returning a file.
5. `scripts/ensure_bootstrap_admin.py`: require an explicitly chosen password for
   fresh bootstrap; do not print passwords. Existing administrators are preserved.

## Export-only cleanup and supporting material

Excluded manual verification notes under TEST_SCENARIOS, developer debug scripts,
the captured failed-login image, a one-off frontend password-reset script and a
debug E2E file and the unused React template SVG. The used Vite SVG is
retained with its upstream MIT license in THIRD_PARTY_NOTICES.md. No application service, route, UI page, model, migration or provider
was removed. Original operational password/lockout tools and packaging source are
retained; they are explicit operator tools, not run by this publication.

Added tested core dependency pins, focused regression test files, and this
README/validation documentation. No environments, generated frontend build,
node_modules, runtime database, uploads, logs, credentials, original Git history,
workflow or release artifact is included. Build the frontend locally before use.

Additional export cleanup excludes ten manual diagnostic/reset helpers that target
the configured database or an existing localhost server rather than isolated
test fixtures. Application routes/services and parameterized operator tooling
remain included; isolated in-memory test fixtures are retained.

The final cleanup also excludes remaining non-isolated manual Python scenarios,
legacy repair scripts and the historical Playwright harness/configuration that
assumed accounts on a running server. The original dependency lock remains
unchanged. Database validation no longer recommends an excluded repair script.
