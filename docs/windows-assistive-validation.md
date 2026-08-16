# Checklist manual de Windows, TTS y lectores de pantalla

Esta checklist complementa `src/frontend/e2e/pilot-gate.spec.ts`. Los casos
Playwright prueban el comportamiento web automatizable; esta guía exige probar
el artefacto Windows real, el audio físico y los lectores de pantalla. No es
una declaración de conformidad WCAG, validación clínica ni certificación de
compatibilidad.

## 0. Casos Playwright ejecutables

Ejecutar desde `src/frontend` contra un backend que sirva el build de
producción:

```bash
npm run build
PLAYWRIGHT_BASE_URL=http://127.0.0.1:8086 npm run test:e2e -- pilot-gate.spec.ts --project=chromium
```

La suite E2E completa (127 tests) se ejecuta en CI sobre Chromium, Firefox y
WebKit (`--project=chromium --project=firefox --project=webkit`); el comando de
arriba es solo un ejemplo enfocado.

El entorno debe tener las cuentas de demostración que utiliza
`e2e/auth.setup.ts` o proporcionar `E2E_ADMIN_*`, `E2E_TEACHER_*` y
`E2E_STUDENT_*`. El guard de producción debe permanecer activo; no usar
`AAC_E2E_SKIP_GUARD=1` para una validación de release.

| Caso automatizado | Cubre |
|---|---|
| `pilot-gate.spec.ts` — setup/reutilización | Estado inicializado, denegación de segundo setup y redirección de `/setup` |
| `pilot-gate.spec.ts` — API no autenticada | Denegación de `/api/users/me`, `/api/boards` y `/api/learning-modes/` |
| `pilot-gate.spec.ts` — sesiones por rol | Refresh y workflow primario de Admin, Teacher y Student |
| `pilot-gate.spec.ts` — logout | Token capturado antes de logout recibe `401` después del logout UI |
| `pilot-gate.spec.ts` — AAC | Añadir, ordenar, backspace, clear y activación por teclado |
| `pilot-gate.spec.ts` — offline | Selección local en un tablero previamente cargado sin red |
| `pilot-gate.spec.ts` — límites de rol | Rutas UI y `POST /api/auth/admin/create-user` para Student/Teacher |

Estos casos no prueban instalación Windows, audio físico, NVDA, Narrator,
hardware táctil ni compatibilidad general con lectores. Esas áreas solo pueden
marcarse `PASS` con la checklist manual y evidencia del entorno real.

## 1. Identificación y condiciones

Completar antes de comenzar. Usar solamente datos ficticios.

| Campo | Valor |
|---|---|
| Fecha/hora | `________________` |
| Tester | `________________` |
| Commit exacto | `________________` |
| Versión declarada | `________________` |
| Artefacto | Installer / Portable |
| Archivo y tamaño | `________________` |
| SHA-256 | `________________` |
| Windows y build | `________________` |
| Arquitectura | x64 / ARM64 |
| Tipo de cuenta Windows | Estándar / Administrador |
| Ruta de instalación | `________________` |
| Ruta de datos esperada | `________________` |
| Escala/resolución | `________________` |
| Red | Online / Offline / Interrumpida |
| Salida de audio | Altavoces / Auriculares |
| Micrófono | Disponible / No disponible |

Cuentas de demostración:

- Admin: `qa_admin`
- Teacher: `qa_teacher`
- Student A: `qa_student_a`
- Student B: `qa_student_b`

No registrar contraseñas, JWT, claves API, nombres reales ni frases AAC
privadas en capturas, logs o este documento.

## 2. Resultado por caso

Usar exclusivamente `PASS`, `FAIL`, `PARTIAL` o `NOT TESTED`. En cada fallo
registrar pasos exactos, captura o vídeo y el comportamiento observado.

| ID | Resultado | Evidencia / observaciones |
|---|---|---|
| WIN-001 |  | Hash del instalador coincide con el artefacto entregado |
| WIN-002 |  | Instalación limpia con usuario estándar |
| WIN-003 |  | La aplicación no necesita escribir en una carpeta protegida |
| WIN-004 |  | Primera ejecución muestra setup sin Admin predeterminado inseguro |
| WIN-005 |  | Setup crea el Admin ficticio y deja la aplicación utilizable |
| WIN-006 |  | Contraseña débil se rechaza con mensaje comprensible |
| WIN-007 |  | Setup no puede reutilizarse tras la inicialización |
| WIN-008 |  | Cerrar, abrir y reiniciar conserva la cuenta |
| WIN-009 |  | Login, refresh, logout y login posterior |
| WIN-010 |  | Admin crea Teacher y dos Students; sobreviven al reinicio |
| WIN-011 |  | Teacher ve y usa únicamente el alcance previsto |
| WIN-012 |  | Student abre tablero, símbolos y sentence strip |
| WIN-013 |  | Estado importante sobrevive a cierre completo |
| WIN-014 |  | Desinstalación y tratamiento de datos siguen lo documentado |

### WIN-001 — Integridad del artefacto

1. Calcular SHA-256 del instalador y, si existe, del portable.
2. Compararlo con el registro de release o del responsable de la prueba.
3. Guardar el hash, no el archivo ni datos de usuario, en la evidencia.

**Bloquea el piloto si:** el hash no coincide o no se puede identificar qué
commit contiene el artefacto.

### WIN-002 a WIN-004 — Instalación y primera ejecución

1. Usar una VM o perfil Windows limpio.
2. Instalar como usuario estándar en la ubicación soportada.
3. Abrir la aplicación sin `Run as administrator`.
4. Confirmar que los datos operativos se escriben en la ruta documentada.
5. Reiniciar la aplicación y comprobar que no aparece una base nueva inesperada.
6. En una base nueva, confirmar que aparece setup y no una contraseña
   predeterminada funcional.

### WIN-005 a WIN-007 — Setup seguro

1. Probar campos vacíos, contraseña corta, contraseña sin mayúscula/minúscula
   o número y contraseñas que no coincidan.
2. Confirmar que el mensaje explica cómo corregir cada error.
3. Crear `qa_admin` con una contraseña fuerte ficticia.
4. Recargar, cerrar y volver a abrir.
5. Visitar `/setup` de nuevo e intentar enviar otro Admin.
6. Confirmar redirección o denegación; no debe crearse una segunda cuenta.

### WIN-008 a WIN-010 — Cuentas, sesión y persistencia

1. Como Admin, crear `qa_teacher`, `qa_student_a` y `qa_student_b`.
2. Confirmar cada cuenta después de refresh y reinicio de la aplicación.
3. Como cada rol, hacer login y refresh.
4. Cerrar sesión desde la UI.
5. Intentar volver a una ruta protegida y, si se dispone de la herramienta de
   red, repetir una petición protegida con el token anterior.
6. Confirmar que logout no es solamente una redirección visual.

### WIN-011 — Teacher y límites de estudiante

1. En una sesión Teacher separada, seleccionar Student A.
2. Crear o asignar un tablero identificable como `SAM QA BOARD`.
3. Cambiar a Student B y verificar que no se muestra el tablero de A.
4. Intentar abrir manualmente un recurso de A desde la sesión de B, si se
   dispone del identificador.
5. Confirmar denegación server-side y que Teacher conserva sus operaciones
   legítimas.

### WIN-012 — Student AAC mínimo

1. Como Student A, abrir el tablero asignado.
2. Seleccionar `hello`, `water` y `please`.
3. Confirmar orden exacto en la sentence strip.
4. Repetir un símbolo, borrar el último, limpiar y reconstruir la frase.
5. Repetir con teclado usando Tab, Enter y Space.
6. Repetir con puntero/táctil si el dispositivo lo permite.
7. Confirmar que un error de voz no borra la frase visible.

### WIN-013 a WIN-014 — Reinicio y datos

1. Crear un cambio identificable: tablero, símbolo, asignación o preferencia.
2. Refresh, logout/login, cerrar el ejecutable y reiniciar Windows si es viable.
3. Confirmar que el cambio persiste y que Student A/B siguen separados.
4. Si se prueba la desinstalación, registrar qué datos se conservan o eliminan
   y compararlo con la documentación; no usar una única copia de datos reales.

## 3. TTS real y audio físico

### Entorno

| Campo | Valor |
|---|---|
| Motor TTS de Windows | `________________` |
| Voz seleccionada | `________________` |
| Idioma | `________________` |
| Dispositivo de salida | `________________` |
| Volumen del sistema | `________________` |
| ¿Se oyó audio físicamente? | Sí / No |
| Método de evidencia | Observación / Grabación autorizada |

### Casos TTS

| ID | Procedimiento | Resultado esperado | Resultado |
|---|---|---|---|
| TTS-001 | Hablar un solo símbolo | Se oye exactamente la etiqueta visible |  |
| TTS-002 | Hablar `hello water please` | Se oye la frase en el orden mostrado |  |
| TTS-003 | Repetir un símbolo | La repetición se conserva, sin omisión ni duplicación extra |  |
| TTS-004 | Editar y volver a hablar | Se oye el texto actualizado, no una frase anterior |  |
| TTS-005 | Limpiar y reconstruir | Solo se habla la nueva frase |  |
| TTS-006 | Cambiar voz/idioma | La preferencia persiste y el audio sigue siendo comprensible |  |
| TTS-007 | Seleccionar una voz no disponible o provocar fallo seguro | Mensaje recuperable; la frase permanece y la app no se bloquea |  |
| TTS-008 | Repetir activación rápida | No hay habla duplicada inesperada ni congelación |  |
| TTS-009 | Desconectar red con modelos locales preparados | TTS local sigue funcionando si está documentado como local |  |

Para cada caso, distinguir `PASS` por audio realmente oído de `PARTIAL` cuando
solo se verificó el estado de la interfaz. Chromium headless o la existencia de
`window.speechSynthesis` **no** prueban que el audio haya sido emitido.

**Bloquea el piloto si:** el participante depende de voz y la frase hablada no
coincide con la frase visible, o un fallo TTS elimina/bloquea la comunicación.

## 4. NVDA

### Configuración reproducible

| Campo | Valor |
|---|---|
| Versión NVDA | `________________` |
| Sintetizador/voz | `________________` |
| Velocidad | `________________` |
| Browse/Focus mode | `________________` |
| Speech Viewer | Activado / Desactivado |
| Navegador/runtime | `________________` |

### Casos NVDA

| ID | Flujo | Criterio de aceptación | Resultado |
|---|---|---|---|
| NVDA-001 | Arranque y setup | NVDA anuncia título, encabezados, labels y errores de formulario |  |
| NVDA-002 | Login | Username, password y botón tienen nombres; error se anuncia |  |
| NVDA-003 | Navegación | Landmarks, encabezados y enlaces permiten llegar a Communication |  |
| NVDA-004 | AAC | Cada símbolo tiene nombre; la selección/estado se percibe |  |
| NVDA-005 | Sentence strip | Se percibe el texto actualizado, Backspace, Clear y Speak |  |
| NVDA-006 | Teclado | Tab/Shift+Tab/Enter/Space completan el flujo sin trampa |  |
| NVDA-007 | Learning | Prompt, respuestas, feedback correcto/incorrecto y progreso se anuncian |  |
| NVDA-008 | Logout | El control se identifica y el foco queda en una pantalla usable |  |
| NVDA-009 | Error seguro | Backend no disponible o recurso inválido produce mensaje recuperable |  |

Procedimiento mínimo: completar `Login → Communication → seleccionar tres
símbolos → editar/limpiar → Speak → Learning → Logout` sin usar el ratón para
la interacción principal. Registrar si fue necesario cambiar Browse/Focus
mode, y cualquier elemento que NVDA omitió o anunció con un nombre incorrecto.

**No marcar PASS** por inspección del DOM o por Axe. Debe oírse la salida de
NVDA durante el flujo.

## 5. Narrator

### Configuración reproducible

| Campo | Valor |
|---|---|
| Versión/build Windows | `________________` |
| Voz/idioma | `________________` |
| Scan mode | Activado / Desactivado |
| Cursor de Narrator | Activado / Desactivado |
| Velocidad/verbosidad | `________________` |

### Casos Narrator

| ID | Flujo | Criterio de aceptación | Resultado |
|---|---|---|---|
| NAR-001 | Arranque/login | Campos y errores tienen anuncio útil |  |
| NAR-002 | Navegación | Se llega a Communication con teclado |  |
| NAR-003 | AAC | Símbolos y sentence strip tienen nombres/estado comprensible |  |
| NAR-004 | Edición | Backspace, Clear y Speak son localizables y accionables |  |
| NAR-005 | Learning | Prompt y feedback no se pierden durante el cambio de pregunta |  |
| NAR-006 | Logout | Logout es localizable y deja una pantalla usable |  |

Completar al menos `Login → AAC → Logout` con Narrator activo. Si un criterio
no puede probarse con Narrator por una limitación de la plataforma, marcar
`NOT TESTED` y explicar la limitación; no convertirlo en PASS por analogía con
NVDA.

## 6. Accesibilidad manual complementaria

| ID | Prueba | Criterio | Resultado |
|---|---|---|---|
| A11Y-001 | Zoom 200% | No se ocultan controles críticos ni aparece solapamiento impeditivo |  |
| A11Y-002 | Zoom 400% | Login y AAC siguen siendo operables, aunque requieran scroll |  |
| A11Y-003 | Contraste alto de Windows | Texto, foco y selección siguen siendo distinguibles |  |
| A11Y-004 | Reduced motion | Animación visual reducida sin desactivar dwell/temporización funcional |  |
| A11Y-005 | Dwell | Selección ocurre una vez; salir cancela cuando corresponde |  |
| A11Y-006 | Touch | Scroll no activa símbolos accidentalmente; targets son utilizables |  |
| A11Y-007 | Audio desconectado | Fallo de audio no produce pantalla blanca ni pérdida de frase |  |

## 7. Evidencia y decisión

### Evidencia recopilada

- [ ] Hash del artefacto.
- [ ] Versión/build de Windows.
- [ ] Capturas sin datos privados.
- [ ] Vídeo o registro de audio autorizado, si aplica.
- [ ] Registro de pasos y resultado por caso.
- [ ] Logs sanitizados sin contraseñas, tokens ni frases privadas.
- [ ] Incidencias con severidad y reproducibilidad.

### Defectos encontrados

| ID | Severidad | Caso | Pasos resumidos | Evidencia | ¿Bloquea piloto? |
|---|---|---|---|---|---|
| `____` | Blocker/Critical/High/Medium/Low | `____` | `____` | `____` | Sí / No |

### Regla de decisión

- **GO:** todos los casos P0 aplicables pasan y TTS/lector requerido se probó
  realmente en el entorno objetivo.
- **GO WITH CONDITIONS:** no hay Blocker/Critical/High, pero existe una
  limitación explícita de entorno o una validación no requerida para el primer
  piloto que tiene propietario y fecha.
- **NO-GO:** falla instalación, login/logout, autorización, aislamiento,
  persistencia, comunicación AAC, TTS necesario o lector de pantalla necesario.

Resultado final: `GO / GO WITH CONDITIONS / NO-GO`

### Áreas no probadas

1. `____________________________________________________________`
2. `____________________________________________________________`
3. `____________________________________________________________`

Esta checklist no permite afirmar compatibilidad general con Windows, NVDA,
Narrator o TTS a partir de un único entorno. La conclusión debe incluir la
versión exacta probada y cada área marcada `NOT TESTED`.
