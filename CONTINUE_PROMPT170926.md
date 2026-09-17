# CONTINUE_PROMPT — 17/09/2026 (sesión: fix del pipeline de main)

## ⚠️ ACTUALIZACIÓN CRÍTICA — todos los jobs de CI fallan en 3–4 s (mismo día)

El usuario reportó que en la pipeline fallan TODOS los jobs tanto en `pull_request` como en `push`, en 3–4 segundos cada uno: `secret-scan`, `backend`, `frontend`, `codeql (js+py)`, `dependency-review`, `e2e-clean`, `e2e-production-compat`, `e2e-production-gate`, `packaging-windows`.

**Esto NO puede ser culpa del código de la rama** (secret-scan/codeql no ejecutan tests; 3–4 s no basta ni para instalar dependencias). Diagnóstico local ya hecho:

- `ci.yml` es YAML válido (parseado con PyYAML), triggers `push`/`pull_request` estándar, `permissions: contents: read` — el archivo NO es el problema.
- Un único workflow (`ci.yml`), acciones ancladas por SHA.

**Hipótesis ordenadas (ninguna verificable sin la UI de GitHub — el agente no tiene token):**

1. **Minutos de Actions agotados** (repo privado, plan free = 2000 min/mes) — el fallo en arranque de TODOS los jobs es el síntoma clásico.
2. Actions deshabilitado o con spending limit alcanzado (Settings → Actions / Billing).
3. Incidencia de GitHub (githubstatus.com) o del pool de runners.

**Qué debe hacer el siguiente agente:**

- Pedir al usuario que abra UNA corrida fallida (Actions → cualquier run) y lea el error a nivel de job (aparece ANTES de cualquier step; suele decir algo tipo "payment issue", "minutes exhausted", "waiting for a runner" o una anotación de workflow). Ese mensaje nombra la causa.
- Si es facturación: Settings → Billing → revisar minutos incluidos y spending limit. No hay nada que arreglar en el repo.
- NO quemar pushes de diagnóstico: cada push gasta minutos y dispara la misma pared de fallos. Validar todo en local (la receta está más abajo) y empujar solo una vez.
- Importante: este fallo sistémico es INDEPENDIENTE de los 2 fixes reales de esta rama (253/253 E2E ×2 validados en local). La PR puede crearse igualmente; el merge debe esperar a que la infra de Actions funcione para poder confirmar main en verde.

---

## Misión

El siguiente agente debe **terminar el trabajo de la rama `fix/ci-toast-contrast-e2e`**: validar todo en local (SIN empujar nada más a GitHub hasta tener el gate completo en verde, para no gastar minutos de CI), guiar la creación de la PR (la crea el usuario con 1 clic) y merge­arla, verificando después que el pipeline de `main` queda verde.

## Estado actual (verificado, no asumir nada distinto)

- `github/main` = `ec60db5` ("Add permanent E2E spec for dashboard deep-link into Learning sessions"). Ese merge (PR #51) dejó el pipeline de main con **3 tests E2E fallando**.
- Rama local **`ci-repro`** en el clon ext4 `~/repos/AAC_ASSISTANT` = main + 2 commits:
  - `77dec6a` — "Fix toast contrast in dark themes and stabilize arrow-nav spec" (el fix real, ya subido a GitHub como `fix/ci-toast-contrast-e2e`)
  - Este archivo `CONTINUE_PROMPT170926.md` (se sube ahora mismo con el fix)
- Remoto: `github/fix/ci-toast-contrast-e2e` apunta a `77dec6a` (se actualiza con el push de este archivo).
- Checkout NTFS `/media/wishmaster/GitAndLLMs/GitHub/AAC_ASSISTANT`: limpio, en `main` `ec60db5` — **no trabajar ahí** (ver reglas ntfs3 abajo).
- Working tree limpio, sin servidores uvicorn residuales, sin artefactos temporales.

## Causa raíz de los 3 fallos de CI (ya diagnosticada con trazas)

1. **Contraste del toast (2 fallos: `play-redirect in dark`, `play-redirect in high-contrast-dark`)** — sonner hardcodea `[data-description]{color:#3f3f3f}` y pinta su propio fondo blanco por encima de nuestras reglas; el aviso "La voz no está disponible…" quedaba a 1.45:1 en dark y 1.00:1 (invisible) en high-contrast-dark. **Fix aplicado** en `src/frontend/src/index.css`: `background-color: rgb(var(--bg-surface)) !important` en `[data-sonner-toast].aac-toast` + `[data-description]{color:inherit !important}`. Verificado con probe de colores computados: fondo `rgb(20,20,25)` + texto ámbar oscuro ≈ 12:1.
2. **`board-arrow-nav.spec.ts` (1 fallo)** — el spec asertaba el literal `Alpha`, pero `serialize_board` (`src/api/routers/board_helpers.py`) **traduce el `custom_text` al idioma del perfil del usuario** vía Google Translate (admin1 tiene `ui_language=es-ES` → "Alpha"→"Alfa"). Además el spec hacía `.click()` para "enfocar", lo que activaba la tarjeta y sembraba la franja de frase. **Fix aplicado**: `focus()` programático, `custom_text` neutros por idioma (`K7`/`K9`/`K4`) y aserción contra la etiqueta que la API realmente sirve (GET del board antes de asertar).

## Validación ya ejecutada (en el clon ext4, server con env exacto de CI)

- Repro del job **`e2e-clean`**: **253/253 passed (6.8m)** — antes: 3 failed.
- Repro del job **`e2e-production-compat`** (seeded): **253/253 passed (6.7m)**.
- `npm run typecheck` ✓, `npm run lint -- --max-warnings=0` ✓.
- Build de producción con presupuestos ✓ (399.7/450 kB JS).
- **PENDIENTE**: el gate completo `verify_pr.py` NO se corrió sobre `77dec6a`. Es el paso 2 de abajo.

## Pasos que faltan (en orden)

1. **No empujar nada más** hasta completar el paso 2 (cada push a cualquier rama dispara CI).
2. **Gate completo en local** (en `~/repos/AAC_ASSISTANT`, NO en el NTFS):
   ```bash
   cd ~/repos/AAC_ASSISTANT
   uv run python scripts/verify_pr.py 2>&1 | tail -25
   ```
   Si falla algo, arreglarlo en `ci-repro` y solo entonces `git push github ci-repro:fix/ci-toast-contrast-e2e`.
3. **Crear la PR** (lo hace el usuario; el agente no tiene token/gh):
   `https://github.com/rodhayl/AAC_ASSISTANT/compare/main...fix/ci-toast-contrast-e2e?expand=1`
   Título sugerido: `Fix CI: toast contrast in dark themes + arrow-nav spec language localization`
4. **Merge**: probar primero `git push github ci-repro:main` (fast-forward; la vez anterior GitHub lo aceptó para la PR #51 y la marcó como merged automáticamente). Si las rulesets lo rechazan, pedir al usuario que pulse merge en la UI — **"Rebase and merge"** (mantiene historial lineal; NO usar Squash, perdería los mensajes de los 2 commits).
5. **Post-merge**: `git fetch github --prune`, confirmar `github/main` = último commit, y **vigilar la corrida de Actions de main hasta verde** (los 2 jobs E2E completos tardan ~15–20 min; `e2e-production-gate` solo corre `--grep "smoke|auth"`). Borrar `fix/ci-toast-contrast-e2e` (remoto y local) tras el merge.
6. **Trabajo separado pendiente (decidir con el usuario)**: la rama `chore/dependency-groups` (`6fe327e`, réplica de las PRs de Dependabot #48 npm y #49 python, con gate 16/16 validado en su día) sigue sin merge. Su padre es `ec60db5`, así que seguirá siendo mergeable limpia después de este merge. Las ramas `fix/stop-i18n-exception-echo`, `page-coverage-100`, `chore/codex-oss-readiness` y las de Dependabot **no son de esta sesión: no tocarlas**.

## Reglas de entorno (CRÍTICAS — repetir de AGENTS.md)

- **NTFS**: `/media/wishmaster/...` está en partición NTFS con driver `ntfs3`, que se cuelga con operaciones masivas de ficheros pequeños. NUNCA `npm ci`, `npm install`, `rm -rf node_modules`, builds o suites en ese checkout. Todo el trabajo pesado en `~/repos/AAC_ASSISTANT` (ext4). Existe el guardián `~/bin/aac-guard` que redirige npm/uv del NTFS al clon y rechaza `rm -rf` de `node_modules`. **El gestor de paquetes borra `node_modules` él mismo: un `rm -rf` previo no es necesario jamás.**
- **Servidores de fondo**: este entorno mata los procesos background entre comandos salvo que se arranquen con `setsid nohup ... &` dentro del mismo comando. El `process_type=BACKGROUND` del tool NO está implementado. Al terminar: `pkill -f "uvicorn src.api.main"`.
- **`uv run` dentro de pipes a veces se cuelga**: dividir en comandos separados (p. ej. guardar JSON en fichero y parsear después).
- **Tokens para smokes E2E**: NO mintear JWTs leyendo el secret crudo de `.env` con grep (firma inválida). Usar login real `POST /api/auth/token` (form-data, OAuth2, NO JSON) — y está rate-limitado a ~10/min/IP.
- **Storage states** de Playwright: `src/frontend/playwright/.auth/*.json` están gitignored; si el token expira, la app lo refresca sola al esperar un marcador de UI autenticada.
- Nunca commitear `.env`, `data/*.db`, storage states ni `test-results/`.
- Tras cualquier cambio de manifests: `uv run python scripts/check_dependency_usage.py` + regenerar `requirements.txt` como se hizo en `chore/dependency-groups`.
- `git diff --check` antes de cada commit.

## Receta para reproducir los jobs E2E de CI en local (por si hay que re-validar)

Script equivalente a `.github/workflows/ci.yml` job `e2e-clean` (guardado en `/tmp/ci-e2e-clean.sh`, efímero — recrearlo si no existe):

```bash
cd ~/repos/AAC_ASSISTANT
export ENVIRONMENT=test TESTING=1 ALLOWED_ORIGINS=http://127.0.0.1:8086
export JWT_SECRET_KEY=ci-e2e-clean-secret-key-with-at-least-32-characters
export BACKEND_HOST=127.0.0.1 BACKEND_PORT=8086 DATA_DIR=.ci-e2e-data APP_VERSION=2.0.0
export AAC_SEED_SAMPLE_DATA=false AAC_BOOTSTRAP_ADMIN_ON_FIRST_RUN=true
export AAC_BOOTSTRAP_ADMIN_USERNAME=admin1 AAC_BOOTSTRAP_ADMIN_PASSWORD=Admin123
export AAC_ENABLE_SYMBOL_IMAGE_BACKFILL=false
export PLAYWRIGHT_BASE_URL=http://127.0.0.1:8086
export E2E_ADMIN_USERNAME=admin1 E2E_ADMIN_PASSWORD=Admin123
export E2E_STUDENT_USERNAME=student1 E2E_STUDENT_PASSWORD=Student123
export E2E_TEACHER_USERNAME=teacher1 E2E_TEACHER_PASSWORD=Teacher123
export E2E_PROVISION_VIA_API=1
pkill -f "uvicorn src.api.main"; rm -rf .ci-e2e-data; mkdir -p .ci-e2e-data
setsid nohup uv run python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8086 > /tmp/repro-server.log 2>&1 &
# esperar /api/health 200, luego:
cd src/frontend && npm run verify:prod-build && npx playwright test
```

Para el job seeded (`e2e-production-compat`): same con `AAC_SEED_SAMPLE_DATA=true` y `AAC_SEED_ADMIN1_PASSWORD=Admin123 AAC_SEED_STUDENT1_PASSWORD=Student123 AAC_SEED_TEACHER1_PASSWORD=Teacher123`.

Tests que fallaban (verificación rápida): `e2e/board-arrow-nav.spec.ts` (1 test) y `e2e/contrast-audit.spec.ts › admin routes › play-redirect in dark / in high-contrast-dark`.

## Higiene al cerrar

- `pkill -f "uvicorn src.api.main"`; sin `test-results/`, sin `.ci-e2e-data/`, sin configs temporales (`playwright.tmp-all.config.ts` ya borrado).
- Sin tareas/servidores huérfanos; `git status` limpio en ambos checkouts.
