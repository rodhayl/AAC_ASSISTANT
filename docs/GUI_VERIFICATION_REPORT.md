# Informe de Verificación de la GUI — AAC Assistant

Fecha de la verificación: **2026-08-17**. Esta verificación se ejecutó contra el
**servidor real** (FastAPI + SPA de producción) con una **base de datos SQLite
nueva** y datos sembrados deterministas, no contra mocks.

## 1. Entorno de verificación

| Componente | Valor |
| ---------- | ----- |
| Backend | `uvicorn src.api.main:app` en `127.0.0.1:8086` (`ENVIRONMENT=test`) |
| Frontend | Build de producción (`npm run build`, bundle JS 357.0 kB ≤ 450 kB) |
| Datos | SQLite nueva en `/tmp` con `AAC_SEED_SAMPLE_DATA=true` (admin1/Admin123, estudiante, profesor) |
| Navegador | Chromium headless (Playwright) |
| `verify_pr.py` (previa) | **ALL MAINTAINER VERIFICATION CHECKS PASSED** |

## 2. Resultado global

- **E2E Playwright: 132/132 passed (0 failed)** en 4.4 minutos, 30 archivos de
  spec, cubriendo todas las rutas y roles de la aplicación.
- **Axe Core (accesibilidad): 5 escaneos, 0 violaciones** en cualquier nivel
  (critical/serious/moderate/minor = 0) sobre las 5 rutas críticas.
- **Smoke de API en vivo: 12/12 comprobaciones OK** (ver sección 4).

## 3. Desglose por spec (132 tests)

| Spec | Tests | Área verificada |
| ---- | ----- | --------------- |
| `visual-smoke` | 32 | Render de todas las páginas, rutas y navegación |
| `role-matrix` | 12 | Matriz de permisos por rol (admin/teacher/student) |
| `pilot-gate` | 11 | Puerta de preparación para piloto |
| `settings` | 7 | Ajustes de la aplicación |
| `advanced` | 6 | Funcionalidad avanzada |
| `boards` | 5 | CRUD de tableros y listados |
| `axe-accessibility` | 5 | Escaneos Axe de 5 rutas críticas |
| `admin` | 5 | Gestión de usuarios y sistema |
| `learning-games` | 4 | Juegos de aprendizaje |
| `extended-features` | 4 | CRUD de símbolos, características extendidas |
| `dashboard` | 4 | Panel del usuario |
| `communication` | 4 | Tablero de comunicación AAC |
| `accessibility` | 4 | Navegación por teclado, foco, reduced-motion |
| `llm-integration` | 3 | Integración LLM |
| `auth` | 3 | Login/logout/tokens |
| `voice-mode` | 2 | Modo de voz |
| `settings-modes` | 2 | Modos de aprendizaje |
| `maintenance` | 2 | Mantenimiento |
| `board-editor` | 2 | Editor de tablero |
| `achievements` | 2 | Logros |
| `teacher-student-provisioning` | 1 | Alta profesor→estudiante |
| `symbol-image` | 1 | Render de imagen de símbolo + fallback |
| `refresh-bug` | 1 | Regresión de refresco |
| `realtime-collab` | 1 | Colaboración WebSocket |
| `prediction-tiers` | 1 | Predicción por niveles |
| `learning-topics` | 1 | Temas de aprendizaje |
| `first-run-setup` | 1 | Primer arranque con BD vacía |
| `data-management` | 1 | Export/import de datos |
| `board-assignment` | 1 | Asignación de tableros |
| `ai-hot-reload` | 1 | Recarga de configuración IA |

## 4. Smoke de API en vivo (12/12)

| Comprobación | Resultado |
| ------------ | --------- |
| `GET /ready` | `ready:true, status:healthy`, 4/4 providers (speech, llm, achievement, vector_store) |
| `GET /api/auth/setup-status` | `setup_required:false, has_admin:true` (BD sembrada) |
| `POST /api/auth/token` (admin1/Admin123) | Token JWT válido (257 chars) |
| `GET /api/auth/me` | Usuario admin, `is_active:true` |
| `GET /api/boards/` | 4 tableros sembrados (ej. "General Communication") |
| `GET /api/boards/symbols?limit=5` | 5 símbolos del core (cow, horse, chicken, apple…) |
| `GET /api/learning-modes/` | 2 modos de aprendizaje |
| `GET /api/settings/ai` | Configuración de provider servida |
| `GET /api/providers/voice-status` | STT `faster-whisper` instalado (modelo tiny) |
| `POST /api/analytics/usage` | `success:true` |
| `GET /` (SPA) | `<title>AAC Assistant</title>`, 13 assets de build |
| Rutas SPA (`/login`, `/settings`, `/learning`) | 200 (fallback del SPA) |

## 5. Accesibilidad (Axe Core)

| Ruta | critical | serious | moderate | minor |
| ---- | -------- | ------- | -------- | ----- |
| Setup | 0 | 0 | 0 | 0 |
| Login | 0 | 0 | 0 | 0 |
| Communication Board | 0 | 0 | 0 | 0 |
| Learning View | 0 | 0 | 0 | 0 |
| Settings View | 0 | 0 | 0 | 0 |

Además, los tests de teclado verifican: skip-to-content primero en el orden de
tabulación, símbolos del tablero operables con Enter, controles de la frase
operables por teclado, y respeto de `prefers-reduced-motion`.

## 6. Cobertura de tests (medida el mismo día)

| Suite | Resultado |
| ----- | --------- |
| Backend (pytest) | **759 passed** |
| Cobertura backend | 82.12% combinada (statements 85.35%, branches 71.47%) |
| Frontend (Vitest) | **268 passed** (53 archivos) |
| Cobertura frontend | 53.53% líneas, 55.92% statements, 49.01% functions, 46.83% branches (gate: ≥52/53/47/46) |
| E2E Playwright | **132 passed** (este informe) |
| Axe Core | 0 violaciones en 5 rutas críticas |
| `verify_pr.py` | PASS completo (ruff, compileall, import audit, i18n, pytest+cobertura, typecheck, eslint, vitest, build, markdown links) |

## 7. Limitaciones de esta verificación (no simulables en CI)

- **Audio real STT/TTS**: requiere micrófono y voces/engine locales; en headless
  Chromium el TTS cae a `SpeechSynthesis` sin voces y el STT a mocks. La ruta
  de voz se cubre a nivel de contrato y flujo (ver `voice.md` y
  `windows-assistive-validation.md`).
- **Lectores de pantalla NVDA/Narrator y validación del instalador Windows**:
  requieren hardware/Windows físico; checklist en
  `windows-assistive-validation.md`.
- La verificación usa Chromium; Firefox/WebKit no están habilitados en este
  entorno (limitación de plataforma ya documentada en `QA_FINAL_REPORT.md`).

## 8. Conclusión

La aplicación está verificada de extremo a extremo contra el servidor real:
**132/132 tests E2E, 0 violaciones de accesibilidad en las 5 rutas críticas,
12/12 comprobaciones de API en vivo**, con los 4 providers inicializados y el
SPA de producción servido correctamente. No queda funcionalidad GUI sin cubrir
por los tests automatizados; los únicos pendientes son los manuales de hardware
(sección 7).
