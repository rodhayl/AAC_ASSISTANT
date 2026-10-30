# AAC Assistant — complete historical application

A cleaned **12 February 2026** source snapshot of AAC Assistant: the original
React frontend, FastAPI backend, communication boards, learning flows, local
storage, and AI-provider integration. This replaces the earlier component-only
sample. Development of the newer application continues privately.

Base commit: `750dd4ee2384a5306f7319838566aba665a38971`. No later private refactors
or private Git history are included. This is historical software, not a claim
that the current private product has been released.

## What was actually checked

On 30 October 2026, the restored app passed a real HTTP/API workflow using a
synthetic local database and **Ollama Cloud `beam:cloud`**: log in, create a board,
add symbols, reopen it, request three useful AI suggestions, confirm generation
did not overwrite the board, apply one suggestion, and confirm persistence after
a new login. The application made a real `ollama.com/api/chat` request and received
HTTP 200. The React frontend passed its TypeScript/Vite production build.

**Browser GUI acceptance was not run:** the isolated test environment blocked
Chromium's required socket. Voice/audio, local model inference, accessibility
conformance and Windows installers were not validated. Optional voice/vector
packages were not installed or downloaded during this check. See
[VALIDATION.md](VALIDATION.md) for exact evidence and limits.

## Run locally (tested Python 3.12 and Node 24)

The core installation supports the web application and configured cloud AI,
without downloading Torch, Whisper or embedding models. From the repository root:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-core.txt
cd src/frontend
npm ci --ignore-scripts
npm run build
cd ../..
```

Keep the server on loopback and use a local test database. In the same shell:

```sh
export BACKEND_HOST=127.0.0.1
export JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
read -rsp 'Choose an initial admin password (8+ characters): ' AAC_BOOTSTRAP_ADMIN_PASSWORD; echo
export AAC_BOOTSTRAP_ADMIN_PASSWORD
python scripts/ensure_bootstrap_admin.py
unset AAC_BOOTSTRAP_ADMIN_PASSWORD
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8086 --no-access-log
```

Open `http://127.0.0.1:8086` and sign in as `admin1` using the password you chose.
The bootstrap script does not overwrite an existing administrator. Database and
uploads remain local; back them up yourself. The shell-generated JWT key is
session-scoped, so a new key requires users to sign in again. Do not commit local
configuration, keys, databases, logs or uploads. There are no shipped accounts or
passwords. `AAC_SEED_SAMPLE_DATA` is off by default; the verification used explicit
synthetic fixtures, not real users.

### Ollama Cloud or local Ollama

For Cloud, set the provider credential **only in the server environment**, before
starting the server. Do not put it in frontend settings or a `VITE_*` variable:

```sh
read -rsp 'Ollama API key: ' OLLAMA_API_KEY; echo
export OLLAMA_API_KEY
export OLLAMA_BASE_URL=https://ollama.com
export OLLAMA_MODEL=beam:cloud
```

In the application's administrator AI settings select Ollama, set the URL to
`https://ollama.com`, and select/enter an available model such as `beam:cloud`.
Model availability and quota belong to your provider account; this repository
includes neither credentials nor free inference. The adapter sends the Cloud
key only to the exact official HTTPS endpoint and does not follow redirects.
Cloud AI receives the prompt content; use fictional data for evaluation.

Local Ollama remains supported by the original adapter: configure its local URL
and an installed model. This snapshot's acceptance check used Cloud, **not local
inference**. The historical `requirements.txt` and Windows scripts are retained
for optional speech/vector/native workflows; they can install larger packages
and download models, and were not validated in this check. Prefer the core path
above unless you explicitly need those features.

## Scope and limitations

This is a complete application source snapshot, not production certification or
a clinical AAC recommendation. Keep it local; do not expose it to a public
network or use real personal/health data without a separate deployment review.
Historical limitations remain, including refresh tokens transported in a query
parameter and reused until expiration, and a legacy login route with fewer
controls. `--no-access-log` avoids request URLs in Uvicorn logs but does not make
those historical contracts production-safe. The new JWT check separates access
and refresh tokens; old sessions need a fresh login.

Only a small compatibility/security patch was made: loopback defaults, static
file containment, effective JWT validation/type separation, explicit bootstrap
passwords without printing them, and official Ollama Cloud authentication.
No new UI or later private implementation was substituted. Developer debug
artifacts/manual run notes were excluded; operational source, migrations,
packaging files and tests remain. See [SNAPSHOT_CHANGES.md](SNAPSHOT_CHANGES.md).

## License and portfolio

MIT; original [LICENSE](LICENSE) preserved. Dependencies retain their own
licenses. No ARASAAC pictograms, recordings, model weights or real user datasets
are bundled; images retrieved via ARASAAC remain subject to their own attribution,
noncommercial and share-alike terms, not the software MIT license.

For interviews, access to the current private codebase may be requested from the author.
