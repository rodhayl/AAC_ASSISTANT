# CONTINUE_PROMPT — 17/09/2026 (sesión: fix del pipeline de main)

## ⚠️ CONTEXTO CRÍTICO — GitHub Actions caído por facturación; simular la pipeline EN LOCAL

**Confirmado por el usuario: TODOS los jobs de CI (`secret-scan`, `backend`, `frontend`, `codeql`, `dependency-review`, `e2e-*`, `packaging-windows`, tanto en `push` como en `pull_request`) fallan en 3–4 s porque se agotaron los créditos/minutos de GitHub Actions. NO es culpa del código y NO hay nada que arreglar en el repo: no perdernas tiempo depurando Actions, ni abras corridas fallidas buscando errores.**

Consecuencias operativas para ti:

1. **Simula la pipeline completa en local.** Cada job de `.github/workflows/ci.yml` tiene equivalente local (mapa completo más abajo). Nada se considera validado por GitHub: tu gate local es la única verdad.
2. **Los pushes a GitHub seguirán mostrando la pipeline roja por facturación.** Es el estado esperado; no hagas pushes de diagnóstico, no esperes verdes en Actions, y anótalo en la descripción de la PR para que nadie se asuste.
3. Cero desperdicio: validar 100% en local ANTES de empujar; empujar solo para crear/actualizar la rama de la PR.

## Entorno donde vas a trabajar: WINDOWS

El agente anterior trabajó en Linux (las referencias a `~/repos/AAC_ASSISTANT` ext4, `aac-guard`, driver ntfs3, `setsid` y `pkill` son historia de ese entorno: NO te aplican). En Windows:

- **NTFS es nativo y rápido ahí** — puedes instalar, compilar y testear directamente en el checkout del repo. Las reglas anti-`rm -rf node_modules` siguen vigentes por higiene general: **el gestor de paquetes borra `node_modules` él mismo (`npm ci`); un borrado manual previo jamás es necesario.**
- **Shell**: usa PowerShell para los servers en background; Git Bash también vale si está instalado. Equivalencias: `pkill -f uvicorn` → `Get-Process python* | Stop-Process -Force` (o cierra la ventana/terminal del server); `rm -rf` → `Remove-Item -Recurse -Force`.
- **Ventaja**: `packaging-windows` (PyInstaller + Inno, `build_package.bat`) es el ÚNICO job que necesita Windows — puedes ejecutarlo REALMENTE, no solo simularlo.
- Remoto git: `origin` apunta a `github.com/rodhayl/AAC_ASSISTANT` (SSH). La rama con el fix ya está subida (ver abajo).
- Requisitos de toolchain: Python 3.13 + `uv`, Node 22, y para el job de packaging Inno Setup 6 (el CI lo instala; instálalo si vas a correr ese job).

## Misión

Terminar el trabajo de la rama `fix/ci-toast-contrast-e2e`: validar TODO en local (mapa de jobs abajo), guiar la creación de la PR (la crea el usuario con 1 clic), mergearla y dejar documentado que Actions seguirá roja por facturación hasta que se repongan créditos.

## Estado actual (verificado; no asumir nada distinto)

- `origin/main` = `ec60db5` ("Add permanent E2E spec for dashboard deep-link into Learning sessions"). Su merge (PR #51) dejó 3 tests E2E fallando **según la última corrida de CI que sí llegó a ejecutarse**.
- Rama remota **`origin/fix/ci-toast-contrast-e2e`** = `dbe1690`, con 3 commits sobre main:
  - `77dec6a` — "Fix toast contrast in dark themes and stabilize arrow-nav spec" (el fix real: 2 ficheros, `src/frontend/src/index.css` + `src/frontend/e2e/board-arrow-nav.spec.ts`)
  - `07470b0` + `dbe1690` — este prompt de handoff (dos revisiones)
- En Linux quedó validado (253/253 E2E ×2 entornos, typecheck, lint, build); **en tu máquina Windows debes revalidar** (deps distintas, no hay `.venv` ni `node_modules` aún ahí).

## Causa raíz de los 3 fallos originales de CI (ya diagnosticada con trazas)

1. **Contraste del toast (2 fallos: `play-redirect in dark`, `play-redirect in high-contrast-dark`)** — sonner hardcodea `[data-description]{color:#3f3f3f}` y pinta su propio fondo blanco por encima de nuestras reglas; el aviso "La voz no está disponible…" quedaba a 1.45:1 en dark y 1.00:1 (invisible) en high-contrast-dark. **Fix aplicado** en `src/frontend/src/index.css`: `background-color: rgb(var(--bg-surface)) !important` en `[data-sonner-toast].aac-toast` + `[data-description]{color:inherit !important}`. Verificado con probe de colores computados: fondo `rgb(20,20,25)` + texto ámbar ≈ 12:1.
2. **`board-arrow-nav.spec.ts` (1 fallo)** — el spec asertaba el literal `Alpha`, pero `serialize_board` (`src/api/routers/board_helpers.py`) **traduce el `custom_text` al idioma del perfil del usuario** vía Google Translate (admin1 tiene `ui_language=es-ES` → "Alpha"→"Alfa"). Además el spec hacía `.click()` para "enfocar", lo que activaba la tarjeta y sembraba la franja de frase. **Fix aplicado**: `focus()` programático, `custom_text` neutros por idioma (`K7`/`K9`/`K4`) y aserción contra la etiqueta que la API realmente sirve (GET del board antes de asertar).

## Mapa de simulación local de la pipeline (job → comando)

Trabaja en la raíz del repo. Instala primero: `uv sync --locked --group dev` y en `src/frontend`: `npm ci` + `npx playwright install chromium`.

| Job de CI | Equivalente local |
|---|---|
| **todo en uno** (backend+frontend+cobertura+docs+audits) | `uv run python scripts/verify_pr.py` — si algún paso falla en Windows por asunciones POSIX, lanza los pasos individuales de la tabla |
| `secret-scan` | Opcional: binario `gitleaks detect --source . ` (respetará `.gitleaks.toml`). Auditoría de secrets ya verificada limpia; no bloquea |
| `backend` | `uv run ruff check src tests scripts` · `uv run python scripts/audit_codebase.py` · `uv run python scripts/check_dependency_usage.py` · `uv run python -m compileall -q src scripts` · `uv pip check` · `uv run pytest --cov=src --cov-report=term-missing:skip-covered --cov-branch -q` · los 3 `pip-audit --strict` (requirements.txt; export voice/tts; all-groups — ver `ci.yml` líneas 50–57) |
| `frontend` | En `src/frontend`: `npm run typecheck` · `npm run lint -- --max-warnings=0` · `npm audit --omit=dev --audit-level=moderate` · `npm audit --audit-level=high` · `npm run test -- --run --coverage --coverage.reporter=text-summary` · `npm run i18n:audit` · `npm run build` · `npm run check:bundle-size` · `npm run verify:prod-build -- --freshness-only` · `npm run build:e2e` |
| `e2e-clean` | Receta Playwright completa con DB sin seed (abajo) — ~253 tests, 7 min |
| `e2e-production-compat` | Igual con `AAC_SEED_SAMPLE_DATA=true` + `AAC_SEED_ADMIN1_PASSWORD=Admin123 AAC_SEED_STUDENT1_PASSWORD=Student123 AAC_SEED_TEACHER1_PASSWORD=Teacher123` |
| `e2e-production-gate` | Igual que e2e-clean pero `ENVIRONMENT=production`, password de CI `CiProd-Gate-Admin1-2f7c`, `AAC_ENABLE_SYMBOL_IMAGE_BACKFILL=false`, y `npx playwright test --grep "smoke|auth"` (subset) |
| `packaging-windows` | **Ejecútalo de verdad en Windows**: `build_package.bat` (requiere Inno Setup 6) + los pasos de verificación de artefactos del workflow |
| `codeql`, `dependency-review` | Analizadores de GitHub; sin equivalente local real. Skip documentado |

## Receta e2e-clean en PowerShell (Windows)

```powershell
cd <raíz-del-repo>
$env:ENVIRONMENT="test"; $env:TESTING="1"
$env:ALLOWED_ORIGINS="http://127.0.0.1:8086"
$env:JWT_SECRET_KEY="ci-e2e-clean-secret-key-with-at-least-32-characters"
$env:BACKEND_HOST="127.0.0.1"; $env:BACKEND_PORT="8086"
$env:DATA_DIR=".ci-e2e-data"; $env:APP_VERSION="2.0.0"
$env:AAC_SEED_SAMPLE_DATA="false"
$env:AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN="true"
$env:AAC_BOOTSTRAP_ADMIN_USERNAME="admin1"; $env:AAC_BOOTSTRAP_ADMIN_PASSWORD="Admin123"
$env:AAC_ENABLE_SYMBOL_IMAGE_BACKFILL="false"
$env:PLAYWRIGHT_BASE_URL="http://127.0.0.1:8086"
$env:E2E_ADMIN_USERNAME="admin1"; $env:E2E_ADMIN_PASSWORD="Admin123"
$env:E2E_STUDENT_USERNAME="student1"; $env:E2E_STUDENT_PASSWORD="Student123"
$env:E2E_TEACHER_USERNAME="teacher1"; $env:E2E_TEACHER_PASSWORD="Teacher123"
$env:E2E_PROVISION_VIA_API="1"
if (Test-Path .ci-e2e-data) { Remove-Item -Recurse -Force .ci-e2e-data }
New-Item -ItemType Directory .ci-e2e-data | Out-Null
Start-Process -NoNewWindow uv -ArgumentList "run","python","-m","uvicorn","src.api.main:app","--host","127.0.0.1","--port","8086" -RedirectStandardOutput ..\server.log -RedirectStandardError ..\server-err.log
# esperar a que http://127.0.0.1:8086/api/health devuelva 200 (bucle curl/Invoke-WebRequest)
cd src/frontend
npm run verify:prod-build
npx playwright test
# al terminar: Get-Process python* | Stop-Process -Force  (y borrar .ci-e2e-data)
```

Variables de tokens/smokes: **NO mintear JWTs** leyendo el secret crudo de `.env` (firma inválida por parsing distinto de pydantic-settings). Usa login real `POST /api/auth/token` (form-data OAuth2, NO JSON; rate-limit ~10/min/IP). Storage states en `src/frontend/playwright/.auth/*.json` (gitignored; si el token expira, la app lo refresca sola al esperar un marcador de UI autenticada).

## Pasos que faltan (en orden)

1. Clonar/actualizar el repo en Windows y checkout de `fix/ci-toast-contrast-e2e` (`git fetch origin && git switch fix/ci-toast-contrast-e2e`).
2. Instalar deps (`uv sync --locked --group dev`; `npm ci`; `npx playwright install chromium`) y correr el **mapa de simulación completo** de arriba. Arregla lo que falle en esta rama; haz `git diff --check` antes de cada commit.
3. Empujar (solo si hiciste cambios): `git push origin fix/ci-toast-contrast-e2e`.
4. **Crear la PR** (la hace el usuario; 1 clic): `https://github.com/rodhayl/AAC_ASSISTANT/compare/main...fix/ci-toast-contrast-e2e?expand=1`
   Título: `Fix CI: toast contrast in dark themes + arrow-nav spec language localization`
   En la descripción añadir: *"GitHub Actions aparecerá roja por agotamiento de créditos (fallo de arranque en todos los jobs, no relacionado con este cambio). Pipeline simulada al 100% en local: [rellenar con tus resultados]."*
5. **Merge**: probar primero `git push origin fix/ci-toast-contrast-e2e:main` (fast-forward; la vez anterior GitHub lo aceptó y marcó la PR como merged automáticamente). Si las rulesets lo rechazan, pedir al usuario que pulse merge en la UI — **"Rebase and merge"** (historial lineal; NO Squash: perdería los mensajes de los commits).
6. **Post-merge**: `git fetch origin --prune`; confirmar `origin/main` = último commit; borrar `fix/ci-toast-contrast-e2e` (remoto y local). **NO esperar a que Actions de main esté verde**: seguirá roja por facturación hasta que se repongan créditos (los resets suelen ser mensuales en el día de alta del plan, o se sube el spending limit en Settings → Billing). Cuando GitHub vuelva a facturar, la pipeline debe salir verde sola — si no, AHORA sí hay algo que investigar.
7. **Pendiente separado (decidir con el usuario)**: la rama `chore/dependency-groups` (`6fe327e`, réplica de las PRs de Dependabot #48 npm y #49 python, gate 16/16 validado en su día en Linux) sigue sin merge; su padre es `ec60db5`, así que seguirá mergeable limpia. Ramas `fix/stop-i18n-exception-echo`, `page-coverage-100`, `chore/codex-oss-readiness` y las de Dependabot **no son de esta sesión: no tocarlas**.

## Reglas de higiene (de AGENTS.md, aplican igual en Windows)

- Nunca commitear `.env`, `data/*.db`, `src/frontend/playwright/.auth/*.json`, `test-results/`, `.ci-e2e-data/`.
- Tras cambios de manifests: `uv run python scripts/check_dependency_usage.py` + regenerar `requirements.txt` (`uv export --locked --no-dev --format requirements-txt --output-file requirements.txt`).
- NO modificar comportamiento de launch/packaging de Windows salvo que la tarea lo pida (solo EJECUTAR `build_package.bat` está bien).
- Suites completos solo cuando la tarea lo justifique (aquí lo justifica: es una validación de pipeline).
- Al cerrar: sin procesos uvicorn vivos, sin `.ci-e2e-data/`, sin `test-results/`, `git status` limpio.

## Tests que fallaban originalmente (verificación rápida del fix)

- `e2e/board-arrow-nav.spec.ts` (1 test)
- `e2e/contrast-audit.spec.ts › admin routes › play-redirect in dark / in high-contrast-dark`

Con el fix, todo el suite (253) pasa en ambos entornos (validado en Linux; revalida en Windows).
