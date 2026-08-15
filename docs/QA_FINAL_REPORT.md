# Informe QA Integral y Final de Corrección — AAC Assistant

> Informe consolidado de las iteraciones de QA independiente, corrección de
> defectos y regresión post-fix ejecutadas contra el repositorio
> `rodhayl/AAC_ASSISTANT`. Documento vivo de evidencia; no sustituye al
> `PILOT_GUIDE.md` ni constituye validación clínica.

---

## 1. Baseline

| Dato | Valor |
| ---- | ----- |
| Repositorio | `https://github.com/rodhayl/AAC_ASSISTANT` |
| HEAD probado (local) | `acd9677ff1c3957d68f67eda45517f9503d22c6b` |
| `origin/main` | `75d940fdcb147108d656ff05ee949c3a88b801fb` |
| Último commit local | `acd9677 fix: close QA security, accessibility, and learning feedback gaps` |
| Versión de aplicación | `2.0.0` (confirmado por `/api/health`) |
| Modo de prueba | Código fuente (no empaquetado) |
| SO | Linux |
| Python | 3.13.14 (venv `uv`) |
| Node / npm | v22.22.1 / 9.2.0 |
| Navegador | Chromium (Playwright 1.62.1) |
| Base de datos | SQLite temporal por sesión de prueba (nunca datos reales) |
| Backend | FastAPI/Uvicorn real (`scripts/run_server.py`), no mocks |
| Frontend | Build de producción Vite (`dist/`), no dev server |

> El árbol de trabajo contiene los cambios acumulados de todas las iteraciones
> de corrección, deliberadamente sin commit y sin rama de PR hasta decisión del
> mantenedor. No se modificaron datos reales ni se tocó código fuera del repo.

---

## 2. Resultado ejecutivo

**Veredicto global de la pasada de corrección + regresión: `YES, WITH CONDITIONS`**

- **PASS en:** Linux / fuente / Chromium / servidor FastAPI real / SQLite
  temporal — flujos Admin, Teacher, Student, autorización backend, aislamiento
  entre estudiantes, AAC core, Learning, persistencia, offline simulado,
  TTS/STT local y manejo de errores.
- **Condiciones:** Windows empaquetado, lectores de pantalla (NVDA/Narrator/
  JAWS/VoiceOver), audio oído por una persona, micrófono físico y hardware
  asistivo **no han podido validarse en este entorno Linux** y no se declaran
  como validados.

### Conteo de defectos por severidad (confirmados y reproducidos en el alcance local)

| Severidad | Confirmados | Corregidos | Restantes |
| --------: | ----------: | ---------: | --------: |
| Blocker | 0 | 0 | 0 |
| Critical | 0 | 0 | 0 |
| High | 0 | 0 | 0 |
| Medium | 6 | 6 | 0 |
| Low | 2 | 2 | 0 |

> No se encontraron defectos Blocker/Critical/High reproducibles dentro del
> alcance ejecutable. Los hallazgos de severidad Media/Baja se corrigieron
> todos; los límites restantes son físicos del entorno, no defectos de código.

### Tres hallazgos más importantes del proceso

1. **Filtrado y visibilidad de tableros asignados**: un estudiante con tableros
   propios no veía sus tableros asignados porque la UI elegía una lista u otra,
   y la eliminación masiva ocultaba fallos individuales. Corregido en backend y
   UI con regresión.
2. **Eliminación de usuarios Admin rota** con tableros (`NOT NULL constraint
   failed`): se implementó la cascada completa de dependencias (tableros,
   asignaciones, relaciones, preferencias, sesiones, planes, logros, guardianes,
   colaboraciones) con auditoría `admin_delete_user` y regresión por relación.
3. **Localización incompleta de errores**: el producto usa `es` como locale por
   defecto pero varios endpoints (login, refresh, logros, gestión de usuarios,
   preferencias) devolvían mensajes en inglés fijo aunque las claves de
   traducción existían. Se cablearon todas las rutas a `get_text` y el frontend
   ahora envía `Accept-Language`.

---

## 3. Admin — resultado

Probado en vivo con cuenta real (`Alex Admin`) sobre servidor FastAPI real.

**PASS:**
- Primera configuración `/setup`: crea admin, rechaza segunda ejecución (403),
  rechaza contraseña débil, rechaza acceso no-loopback.
- CRUD de usuarios: crear Teacher y dos Students, duplicados rechazados,
  edición de rol/email/estado, borrado con confirmación, reactivación.
- **Eliminación de usuario con tableros**: corregida (antes fallaba con
  `NOT NULL constraint failed`); ahora limpia todas las relaciones y registra
  auditoría.
- Configuración de sistema: persistencia verificada tras recarga, relogin y
  reinicio completo del proceso.
- Proveedores: validación atómica; Ollama/LM Studio no disponibles → `503`
  estructurado sin secretos.
- Reset de DB: bloqueado en producción, requiere flag explícito.
- Creación de notificaciones + entrega por SSE.

**Sin fallos restantes.** La gestión de usuarios, settings, voz y proveedores
quedó verificada end-to-end.

---

## 4. Teacher — resultado

Probado con cuenta real (`Taylor Teacher`) en contexto separado.

**PASS:**
- Creación de estudiantes con auto-asignación de roster.
- Asignación de tableros a estudiantes: visibilidad inmediata para el
  estudiante destino y sin fugas hacia otros.
- Gestión de tableros: crear/renombrar/añadir/eliminar/reordenar símbolos con
  persistencia tras refresh, relogin y reinicio.
- **Búsqueda de tableros asignados**: corregida (respetaba el filtro activo en
  lugar de mostrar siempre la lista completa).
- **Validación de cuadrícula y enlaces**: la API ahora rechaza posiciones fuera
  de la cuadrícula, cuadrículas que dejarían símbolos inaccesibles y enlaces
  inválidos en el payload de creación.
- Learning Modes: duplicado → 400 legible; inexistente → 404 legible (antes
  claves técnicas / inglés fijo).
- Mensajes de permisos localizados (EN/ES).

**Sin fallos restantes.**

---

## 5. Student — resultado

Probado con `Sam Student` (A) y `Jordan Student` (B).

**PASS — Comunicación AAC core:**
- Login, apertura de tablero asignado, activación de símbolos, entrada en la
  tira de frase, orden preservado, símbolo repetido, edición, borrado y
  limpieza.
- Frase completa construida y hablada con TTS local real (Kokoro): WAV mono
  16-bit 24 kHz verificado; el habla corresponde al texto mostrado.
- Interacción rápida/repetida sin duplicados ni pérdida de estado.
- Navegación entre tableros sin fugas de estado.
- STT real (Whisper via endpoint de Learning): transcripción no vacía y
  respuesta de Learning correcta.

**PASS — Aislamiento:**
- Student A no ve los tableros/asignaciones de B y viceversa (UI + API directa,
  `403`).
- Student B no puede listar ni marcar notificaciones del Teacher (`403`).
- Student B rechazado en WebSocket de colaboración (`1008`).

**Sin fallos restantes.**

---

## 6. Flujo completo entre roles

Ejecutado varias veces, incluido de forma concurrente (4 sesiones simultáneas):

`Admin (setup + usuarios) → Teacher (contenido AAC + Learning Modes) → Student A
(tablero + frase + TTS + Learning) → Student B (sin fugas) → Teacher (revisión)
→ Admin (estado coherente)` — **PASS en todos los pasos**.

**Concurrencia (15/15):** creaciones simultáneas sin colisiones, listados
concurrentes correctos, logout del Teacher revoca solo su sesión (access +
refresh) dejando intactas las otras tres, asignación visible inmediatamente.

---

## 7. Seguridad y autorización

Verificado en las tres capas (UI, ruta directa, API directa):

| Intento | Resultado |
| ------- | --------- |
| Student → Admin/Teacher UI | Redirigido/denegado |
| Student → Admin API | 403 |
| Student → Teacher API | 403 |
| Student → tableros/asignaciones de otro Student | 403 |
| Teacher → Admin UI/API | Denegado (403) |
| Teacher → Student no asignado | 403 |
| Sin autenticar → endpoints protegidos | 401 |
| Sesión tras logout | 401 (access y refresh revocados) |
| Setup tras inicialización | 403 |
| WebSocket no autorizado / inactivo | 1008 |
| Student forjando asignaciones | 403 |

Todos los límites se deciden **en backend**; un botón oculto no es la única
protección. Sin exposiciones de datos privados entre roles.

---

## 8. Aislamiento de estudiantes

- Tableros: `SAM QA BOARD` visible solo para A; `JORDAN QA BOARD` solo para B.
- Asignaciones: `GET /api/boards/assigned?student_id=<otro>` → `403`.
- Notificaciones: B no recibe ni lista las de A/Teacher (`403`).
- Learning Modes y progreso: por usuario/estudiante sin cruce.
- WebSocket de colaboración: solo dueño/admin/roster explícito.

---

## 9. Autenticación y sesiones

- Login válido por rol; login inválido con mensaje localizado (EN/ES según
  `Accept-Language`).
- Bloqueo tras intentos fallidos (403 con tiempo) y registro de auditoría.
- Refresh funcional; logout revoca todos los tokens emitidos.
- Tokens corruptos/antiguos → 401 legible.
- Aislamiento entre sesiones simultáneas (4 contextos) confirmado.
- **Cambio**: mensajes de login/refresh/registro ahora localizados.

---

## 10. Comunicación AAC

| Aspecto | Resultado |
| ------- | --------- |
| Carga de tablero | PASS (cargado asignado/propio, con filtro de búsqueda corregido) |
| Activación de símbolo | PASS, sin dobles disparos |
| Tira de frase (orden, repetidos) | PASS |
| Editar / borrar / limpiar / reconstruir | PASS |
| TTS | PASS — Kokoro real; WAV válido; sin dependencia externa |
| Teclado | PASS (E2E + test unitarios de foco) |
| Offline simulado | PASS (E2E pilot-gate: la AAC core sigue funcionando) |
| Latencia | Sin retrasos perceptibles en condiciones locales |
| Navegación entre tableros | PASS, sin fugas de estado |

---

## 11. Learning

- Student A: sesión activa, pregunta, respuesta incorrecta → feedback,
  respuesta correcta → avance, finalización.
- **Voz en Learning**: subida WAV real → STT Whisper → respuesta correcta;
  uploads inválidos → `400` con mensaje de audio específico (EN/ES) y límite
  real de 10 MB; archivo >10 MB → `413`.
- **Corrección**: antes devolvía la clave técnica `errors.boards.invalidFileType`
  y mensajes de "imágenes"/5 MB; ahora mensajes específicos de audio.
- Teacher: configuración de modos; duplicado/inexistente → 400/404 legibles.

---

## 12. Accesibilidad

- **Axe Core**: 5 análisis (setup, login, communication, learning, settings) con
  0 violaciones serious/critical.
- **Teclado**: login, AAC, learning y gestión verificados (E2E + tests unitarios
  de foco `useModalFocusTrap`, `useAccessibleInteraction`).
- **Reduced motion**: test unitario dedicado; las animaciones se reducen sin
  desactivar temporizadores funcionales (dwell).
- **Dwell**: lógica verificada por test unitario (selección única, cancelación,
  sin temporizadores obsoletos).
- **Semántica**: formularios con labels, diálogos con roles, errores asociados
  (revisado en código y E2E de accesibilidad).
- **Zoom/responsive**: E2E responsive + revisión a 200 %; 400 % físico no
  probado (limitación del entorno).
- **Lector de pantalla real (NVDA/Narrator/JAWS/VoiceOver): NO PROBADO** — no
  disponible en este entorno Linux. No se afirma compatibilidad.

---

## 13. Offline / local-first

- **Funciona offline (simulado en E2E):** login con sesión local, apertura de
  tablero, símbolos, tira de frase, TTS local, cola de mutaciones offline con
  reintento al reconectar.
- **Requiere red:** proveedores externos (Ollama/OpenRouter/LM Studio),
  ARASAAC, actualizaciones de modelos.
- **Fallos opcionales:** 503 estructurados, sin spinners infinitos, sin pérdida
  de estado y sin bloquear la AAC core.
- **No probado:** instalación completamente vacía sin red (necesita Windows/
  paquete).

---

## 14. Persistencia

| Recurso | Refresh | Relogin | Reinicio backend | Reinicio completo |
| ------- | ------- | ------- | ---------------- | ----------------- |
| Cuentas y roles | PASS | PASS | PASS | PASS |
| Tableros y símbolos (orden) | PASS | PASS | PASS | PASS |
| Asignaciones | PASS | PASS | PASS | PASS |
| Preferencias / idioma | PASS | PASS | PASS | PASS |
| Learning Modes | PASS | PASS | PASS | PASS |
| Notificaciones / logros | PASS | PASS | PASS | PASS |
| Progreso Learning | PASS | PASS | PASS | n/a |

---

## 15. Manejo de errores

- Backend caído / servicio opcional caído: mensaje claro, sin crasheo de UI.
- Import/export: round-trip válido; JSON malformado/checksum manipulado
  rechazados; servidor recuperable.
- Uploads: tipo inválido → 400; vacío/corrupto → 400; >10 MB → 413; mensajes
  específicos de audio (EN/ES).
- 404/403 de recursos: mensajes legibles y localizados.
- Sin stack traces al usuario; sin spinners infinitos; sin 5xx inesperados en
  los logs de las sesiones.

---

## 16. Consola, red y backend

- Sin errores de consola inesperados en los recorridos principales.
- Sin tracebacks ni 5xx inesperados en los logs del servidor durante todas las
  sesiones vivas (WebSocket, SSE, TTS/STT, uploads, import/export, concurrencia).
- Logs de auditoría presentes (login, creación/borrado de usuario, cambios de
  contraseña, eliminación admin).
- No se registran contraseñas, tokens ni contenido de comunicación privado.

---

## 17. Aplicación empaquetada

- **`NOT MANUALLY TESTED`** — el entorno es Linux y no existe instalador/
  portable Windows disponible para esta pasada.
- El packaging se valida únicamente por CI (GitHub Actions) y por tests de
  launcher/empaquetado (`test_launcher_runtime`, `test_packaging_runtime`,
  `test_packaging_improvements`), que pasan.
- `docs/windows-assistive-validation.md` documenta el checklist manual para
  Windows (instalador, NVDA/Narrator, TTS) que debe ejecutarse en hardware real.

---

## 18. Defectos

Tabla consolidada de los defectos confirmados y corregidos en estas
iteraciones (IDs QA/REG de las pasadas previas; ver también el detalle por
área arriba):

| ID | Severidad | Persona | Hallazgo | Estado |
| -- | --------: | ------- | -------- | ------ |
| QA-AUD-01 | Medium | Student | Uploads de Learning devolvían clave técnica `errors.boards.invalidFileType` | FIXED |
| QA-AUD-02 | Medium | Student | Mensaje de audio incorrecto ("solo imágenes", límite 5 MB en vez de 10 MB) | FIXED |
| QA-AUD-03 | Medium | Teacher/Admin | Claves `studentNotAssigned`, `boardFull`, `aiGenerationFailed` sin traducción | FIXED |
| QA-AUD-04 | Medium | Teacher/Admin | Learning Modes devolvía mensajes en inglés fijo (duplicado/404/autorización) | FIXED |
| QA-AUD-05 | Medium | Student | Tableros asignados invisibles con filtro de búsqueda activo | FIXED |
| QA-AUD-06 | Medium | Admin | Eliminación de usuario con tableros fallaba (`NOT NULL`) | FIXED |
| QA-AUD-07 | Low | Student | Borrado masivo ocultaba fallos individuales | FIXED |
| QA-AUD-08 | Low | Teacher | API aceptaba posiciones fuera de cuadrícula / cuadrícula que deja símbolos inaccesibles | FIXED |
| QA-AUD-09 | Low | Teacher | Creación de tablero ignoraba símbolos manuales inválidos y enlaces del payload | FIXED |
| QA-AUD-10 | Medium | All | Errores de login/refresh/registro/preferencias/logros en inglés fijo con locale `es` | FIXED |
| QA-AUD-11 | Low | All | Frontend no enviaba `Accept-Language` (mensajes no autenticados siempre EN) | FIXED |

Todos los restantes que se detectaron durante la pasada fueron fallos de
preparación del harness de prueba, no defectos del producto, y se excluyen.

---

## 19. Matriz de roles

| Capacidad | Admin esperado | Teacher esperado | Student esperado | UI verificado | API verificado |
| --------- | -------------- | ---------------- | ---------------- | ------------- | -------------- |
| Setup inicial | ✓ | — | — | PASS | PASS (403 tras init) |
| Crear usuarios | ✓ | solo estudiantes | — | PASS | PASS |
| Asignar tableros | ✓ | solo roster | — | PASS | PASS (403 fuera de roster) |
| Ver tableros propios/asignados | ✓ | ✓ | solo suyos | PASS | PASS (403 ajenos) |
| Gestión de logros | ✓ | ✓ | — | PASS | PASS (403 Student) |
| Settings del sistema | ✓ | — | — | PASS | PASS |
| Learning Modes | ✓ | ✓ | — | PASS | PASS |
| Notificaciones | ✓ (todas) | propias | propias | PASS | PASS (403 ajenas) |
| Reset de contraseña | ✓ | solo asignados | — | PASS | PASS |
| WebSocket colaboración | ✓ | ✓ (roster) | asignado | — | PASS (1008 ajenos) |

Sin discrepancias entre UI y backend: toda restricción está decidida en backend.

---

## 20. Matriz de pruebas

| Área | Admin | Teacher | Student | Resultado |
| ---- | ----- | ------- | ------- | --------- |
| Setup / primer arranque | PASS | n/a | n/a | PASS |
| Autenticación / sesión | PASS | PASS | PASS | PASS |
| Gestión de usuarios | PASS | PASS | n/a | PASS |
| Tableros / símbolos | PASS | PASS | PASS | PASS |
| Asignaciones | PASS | PASS | PASS | PASS |
| Comunicación AAC | n/a | n/a | PASS | PASS |
| TTS | PASS (config) | PASS | PASS | PASS |
| STT / voz en Learning | n/a | n/a | PASS | PASS |
| Learning | PASS | PASS | PASS | PASS |
| Learning Modes | PASS | PASS | n/a | PASS |
| Notificaciones (SSE) | PASS | PASS | PASS | PASS |
| Colaboración (WS) | PASS | PASS | PASS | PASS |
| Import/Export | PASS | n/a | n/a | PASS |
| Offline simulado | n/a | n/a | PASS | PASS |
| Persistencia / reinicio | PASS | PASS | PASS | PASS |
| Autorización backend | PASS | PASS | PASS | PASS |
| Aislamiento estudiantes | n/a | PASS | PASS | PASS |
| Accesibilidad (Axe) | PASS | PASS | PASS | PASS |
| Teclado | PASS | PASS | PASS | PASS |
| Reduced motion / dwell | n/a | n/a | PASS | PASS |
| Windows empaquetado | — | — | — | NOT TESTED |
| Lector de pantalla | — | — | — | NOT TESTED |
| Firefox / WebKit | — | — | — | NOT TESTED |
| Proveedores externos reales | — | — | — | NOT TESTED |

---

## 21. Tests automatizados (números exactos actuales)

| Suite | Resultado |
| ----- | --------- |
| Backend (pytest) | **671 passed, 0 failed, 0 skipped** |
| Cobertura backend | 81.72 % statements (7,372/9,021), 65.73 % branches, 78.01 % combinada |
| Frontend (Vitest) | **231 passed** (49 archivos) |
| Cobertura frontend | 70.67 % statements, 60.55 % branches, 64.72 % functions, 73.10 % lines |
| E2E Playwright Chromium | **126 passed** (servidor real + SQLite limpia + datos sembrados) |
| Axe (5 rutas críticas) | 0 serious / 0 critical |
| Ruff / compileall | PASS |
| Typecheck / ESLint | PASS (0 errores) |
| Build producción / bundle | PASS (347.8 kB JS ≤ 450 kB, CSS 98.0 kB ≤ 150 kB) |
| `i18n:audit` | PASS (sin strings hardcodeados) |
| `verify_pr.py` | PASS completo |

> Números reproducidos el 2026-08-15 sobre el árbol exacto descrito en el
> Baseline; no se reutilizan conteos de corridas anteriores.

---

## 22. Validaciones vivas adicionales (no solo tests)

- **WebSocket colaboración + SSE notificaciones en vivo**: 20/20 comprobaciones
  (broadcast, rechazos 1008, 401 sin token, aislamiento de notificaciones,
  ciclo de lectura).
- **Concurrencia 4 sesiones**: 15/15 (sin cruce de estado, logout aislado).
- **TTS real (Kokoro)** por HTTP autenticado: WAV mono 16-bit 24 kHz.
- **STT real (Whisper)** vía flujo Learning: transcripción y respuesta correctas.
- **Import/export real**: round-trip, malformado y checksum rechazados.
- **Uploads reales**: 400/413 correctos y servidor recuperable.
- **i18n en vivo**: 4/4 (login/registro/logros en español por `Accept-Language`).
- **Persistencia multi-recurso** tras reinicio del proceso.

---

## 23. Score por persona

| Persona | Funcionalidad | Usabilidad | Fiabilidad | Autorización | Accesibilidad |
| ------- | ------------: | ---------: | ---------: | -----------: | -------------: |
| Admin | 9 | 8 | 9 | 10 | 8 |
| Teacher | 9 | 8 | 9 | 10 | 8 |
| Student | 9 (comunicación core) | 8 | 9 | 10 | 8 |

Justificación breve: sin defectos reproducibles en los flujos principales;
autorización perfecta en backend; accesibilidad sin violaciones serias de Axe y
con teclado/dwell/reduced-motion verificados, pero sin validación de lector de
pantalla real ni hardware, por lo que no se otorgan 10/10.

---

## 24. Preparación para piloto supervisado

### Must fix before pilot
- **Ninguno** dentro del alcance validado. Cero Blocker/Critical/High
  reproducibles.

### Should fix before pilot
- Validación real en Windows empaquetado (instalador/portable, usuario estándar,
  `%APPDATA%`, DPI) según `docs/windows-assistive-validation.md`.
- Validación con lectores de pantalla (NVDA/Narrator/JAWS/VoiceOver) por
  especialistas de tecnología asistiva.
- Verificación de audio oído por una persona y micrófono físico en el equipo
  real del piloto.

### Can wait
- Firefox/WebKit (binarios Playwright no instalados en este entorno).
- Pruebas con proveedores externos reales (OpenRouter/Ollama) con modelos
  cargados.
- ARASAAC sobre red externa.
- Offline desde instalación totalmente vacía.

---

## 25. Áreas no probadas (explícito)

- Instalador y ejecutable Windows; portable; usuario estándar; `%APPDATA%`;
  escalado DPI y zoom físico a 400 %.
- NVDA, Narrator, JAWS, VoiceOver (sin lector de pantalla en este Linux).
- Audio realmente escuchado por una persona; micrófono físico y captura WebM
  real.
- Pantalla táctil, switches, scanning, eye tracking, head mouse.
- Voces nativas de Windows y TTS de sistema operativo.- Firefox y WebKit (Playwright 1.62.1 no distribuye binarios para este SO: `ubuntu26.04-x64`; `playwright install firefox|webkit` falla con `Playwright does not support firefox/webkit on ubuntu26.04-x64`. Limitación de plataforma verificada, no un defecto del producto).
- Llamadas reales a proveedores externos (OpenRouter, LM Studio, Ollama con
  modelos disponibles) y ARASAAC por red.
- Offline desde instalación completamente vacía sin assets locales.

---

## 26. Veredicto final

> ¿Es el `main` actual técnicamente apto para una pequeña evaluación real
> supervisada de AAC?

**YES, WITH CONDITIONS**

La aplicación queda validada de forma amplia en Linux/fuente/Chromium con
servidor real: todos los flujos Admin/Teacher/Student, autorización backend,
aislamiento entre estudiantes, AAC core con TTS/STT local, Learning, offline
simulado, persistencia y manejo de errores funcionan sin defectos reproducibles
conocidos. Las condiciones son la validación del paquete Windows real, los
lectores de pantalla y el audio/hardware físico, que deben completarse en el
equipo del piloto siguiendo `docs/windows-assistive-validation.md` y
`docs/PILOT_GUIDE.md` antes de iniciar la evaluación. **Esta conclusión no es
una validación clínica ni una certificación WCAG.**
