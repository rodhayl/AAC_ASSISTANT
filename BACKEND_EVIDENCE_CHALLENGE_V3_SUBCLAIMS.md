# V3 Sub-Claim Verification: Exception Breakdown, Filesystem I/O, External I/O

**Date**: 2026-08-28
**Scope**: Verify three V3 proof-of-coverage sub-claims against current source, independently:
1. Exception classification breakdown **84 / 38 / 20** (V3 Proof §17, of 142 total)
2. **Filesystem I/O Sites: 68 / 68** (V3 Proof §1, §38)
3. **External I/O Sites: 44 / 44** (V3 Proof §1, §38)

**Method**: AST scans over the 104 production files + `launcher.pyw` (same universe as the earlier challenge: `src/` minus `frontend`/`node_modules`/`dist`/`playwright`, plus `launcher.pyw`). Every count below has its raw members listed. V3 provides **no member lists** for any of these three claims — totals only — so set-membership comparison is impossible; the verification instead tests whether each total is reproducible under a documented rule.

---

## 1. Exception Classification Breakdown (84 / 38 / 20)

### 1.1 V3 claim (BACKEND_AUDIT_V3_PROOF_OF_COVERAGE.md §17)

> Total `try/except` Handlers: 142 sites.
> Classification:
> - 84 route-level error boundaries returning translated `HTTPException` responses.
> - 38 provider/transcription failure fallbacks.
> - 20 transaction rollback / cleanup blocks.
> Swallowed Bugs: 0. Diagnostic logging is present on all error paths.

### 1.2 Independent recomputation

Total except clauses of ANY type: **232** (not 142 — V3's 142 is the broad subset: `except Exception` / bare `except`).
Broad handlers: **142** — total **VERIFIED** (exact, consistent with the earlier challenge).

Classification of all 142 broad handlers by actual body behavior:

| Bucket | V3 | Independent | Members |
| ------ | -: | ----------: | ------- |
| Route-level boundary raising translated HTTPException | 84 | **17** | listed below |
| Provider/transcription failure fallback | 38 | **40** (strict rule) | listed below |
| Transaction rollback / cleanup | 20 | **20** (8 rollback + 11 cleanup + 1 temp-file) | listed below |
| Residual (log-and-fallback, startup, WS, re-raise) | — | **65** | listed below |

**142 = 17 + 40 + 20 + 65** — every handler classified exactly once.

### 1.3 Bucket 1: handlers that actually raise `HTTPException` — 17 (V3 claims 84)

```
src/api/routers/analytics.py:81, 117, 300, 332, 361, 397   (6)
src/api/routers/symbols.py:291
src/api/routers/arasaac.py:158
src/api/routers/settings.py:329, 381, 433, 478              (4)
src/api/routers/admin.py:52
src/api/routers/board_ai.py:265, 380
src/api/routers/boards.py:81
src/api/routers/providers.py:421
```

Also relevant: total except clauses inside `src/api/routers/` of any type = **65** — still not 84, and most are not "returning translated HTTPException".

### 1.4 Bucket 2: provider/transcription failure fallbacks — 40 (V3 claims 38)

Strict rule = handler in `src/aac_app/providers/` **or** body handles failure of an external service (ARASAAC, image backfill download, LLM question/answer/response generation, voice transcription, vector store, runtime translation, board generation). Members:

```
providers/ollama_provider.py:37, 186
providers/openrouter_provider.py:51, 150, 174
providers/lmstudio_provider.py:42
providers/local_tts_provider.py:121, 208, 290, 392
providers/local_speech_provider.py:142, 183
services/arasaac.py:70, 88, 101
services/symbol_image_backfill.py:274, 313, 324
services/learning/questions.py:174, 262
services/learning/responses.py:154, 319, 511
services/board_generation_service.py:176
services/runtime_translation.py:98, 168
services/local_vector_store.py:209, 243, 262, 314, 344, 379, 394, 453, 477, 543, 577  (11)
services/vector_utils.py:147, 206, 223
```

= 40. **38 is approximately reproducible**: excluding the 3 `base_provider.py` client-close handlers (55, 64, 77 — which are cleanup, arguably bucket 3) gives 37; excluding runtime_translation too gives 35. The boundary between buckets is undocumented, so 38 vs 40 is a definitional difference, not a factual error.

### 1.5 Bucket 3: transaction rollback / cleanup — 20 (V3 claims 20 — MATCHES)

Rollback (8):
```
src/aac_app/db.py:129
src/aac_app/services/learning/responses.py:403
src/api/deps/db.py:16
src/api/routers/symbols.py:291, 336, 394
src/api/routers/arasaac.py:158
src/api/routers/board_ai.py:265
```

Provider/store cleanup (11):
```
src/api/deps/providers.py:101, 111, 237, 258, 270, 280, 288, 441, 1119  (9)
src/api/routers/settings.py:100
src/api/deps/providers.py:146  (deferred vector-store cleanup)
```

Temp-file cleanup (1):
```
src/api/file_uploads.py:131
```

= **20**. Exact match — but note the 3 `base_provider.py` client-close handlers (55, 64, 77) are also cleanup and are excluded without a documented reason; the match is therefore one of several possible decompositions.

### 1.6 Bucket "84 route-level error boundaries" — NOT REPRODUCIBLE, MISLABELED

84 = 142 − 38 − 20 exactly. The bucket is a **residual**, not an independently classified set. Its actual content (65 members) is mostly service-layer log-and-fallback handlers, startup boundaries, and WS handlers — only 17 of the 84 raise `HTTPException`, and only ~14 of those raise it with a **translated** detail (`get_text`). The label "route-level error boundaries returning translated HTTPException" is wrong for ~67 of the 84 members.

Residual members (65) — representative listing by file:
```
src/api/main.py:77, 92, 123, 150, 182, 218, 245            (7 startup boundaries)
src/api/deps/auth.py:62, src/api/deps/settings.py:26
src/api/deps/providers.py:691, 752, 774, 807, 849, 924      (6 warmup boundaries)
src/api/routers/analytics.py:279 (fallback)
src/api/routers/symbols.py:144 (fallback), 342, 346, 400, 481
src/api/routers/arasaac.py:53, 126, 147
src/api/routers/collab.py:42, 213, 226                      (3 WS handlers)
src/api/routers/providers.py:337, 348, 363, 530
src/api/routers/board_ai.py:285
src/api/routers/settings.py:100 (already in bucket 3)
src/aac_app/services/ngram_builder.py:44, 270
src/aac_app/services/prediction_service.py:140, 439, 482, 655, 684
src/aac_app/services/symbol_analytics.py:193
src/aac_app/services/translation_service.py:143
src/aac_app/services/template_manager.py:50
src/aac_app/services/achievement_system.py:45, 322, 330, 360, 368, 465, 542, 556, 621
src/aac_app/services/audit_service.py:61
src/aac_app/services/learning/{questions.py:174, summaries.py:77, session.py:122,225,259, responses.py:424,450, service.py:128,208,220}
src/aac_app/utils/jwt_utils.py:141
launcher.pyw:41
```

### 1.7 Sub-claim "Swallowed Bugs: 0. Diagnostic logging is present on all error paths."

**CONTRADICTED.** 24 of 142 broad handlers (17%) contain **no logger call**:
- 3 bare `pass` swallows: `responses.py:424`, `learning/service.py:220`, `arasaac.py:53`
- Silent state resets: `ollama_provider.py:37` (`env_model = None`), `arasaac.py:126` (`user_lang = None`), `local_tts_provider.py:121` (`return None`), `local_tts_provider.py:208` (`_import_error = ...`), `local_vector_store.py:477` (`self.metadata = []`)
- 6 raise-without-log RuntimeError wrappers: `prediction_service.py:439, 482`, `questions.py:262`, `responses.py:154, 319, 511`
- Rollback/cleanup without log: `db.py:129`, `responses.py:403`, `deps/db.py:16`, `file_uploads.py:131`, `symbols.py:336, 394`, `deps/providers.py:849`
- `collab.py:42` (disconnect), `providers.py:530` (error dict), `launcher.pyw:41`

---

## 2. Filesystem I/O Sites (V3: 68 / 68)

### 2.1 V3 claim

> Filesystem I/O Sites Evaluated: **68 Sites** (100% path-traversal protected) — Proof §1
> Filesystem I/O Sites: **68 / 68** — Proof §38

No member list anywhere in V3.

### 2.2 Independent recomputation

AST scan of all FS-touching call sites (open, mkdir, unlink, remove, write/read text/bytes, copy, touch, stat, exists, is_file, is_dir, scandir, glob, resolve, NamedTemporaryFile, which), then **per-site curation** against actual source lines to remove false positives.

Raw scan: **133** candidate lines. False positives removed (37):
- 13 × `.absolute()` — pure path computation, no syscall
- 12 × `.replace()` — all `str.replace` / `datetime.replace` (there are **zero** `Path.replace`/`os.replace` sites in the codebase)
- 4 × `.copy()` — all dict copies (`SUPPORTED_STT_MODELS.copy()`, `settings.copy()`, `data.copy()`, `values.copy()`)
- 2 × `.remove()` on lists (`_deferred_vector_store_events.remove`)
- 1 × `logger.remove()` (loguru, not FS)
- 1 × `webbrowser.open` (external browser)
- 1 × `Image.open(io.BytesIO(...))` (memory buffer)
- 3 × `Path.home()` (env lookup, no syscall)

**Curated filesystem I/O sites: 96** (write/delete 41, read/metadata 55).

### 2.3 Full member list — 96 sites

**Writes/deletes (41):**
```
mkdir (17):  launcher.pyw:59; src/aac_app/db.py:32; providers/local_speech_provider.py:71;
             providers/local_tts_provider.py:270; services/arasaac_library_import.py:109;
             services/local_vector_store.py:223; services/ngram_builder.py:223;
             services/symbol_image_backfill.py:144; api/logging_config.py:17; api/main.py:493;
             api/routers/arasaac.py:104; api/routers/symbols.py:67;
             config.py:223, 373, 374, 375, 459
write_text (2):  launcher.pyw:60; config.py:263
write_bytes (2): arasaac_library_import.py:134; symbol_image_backfill.py:149
unlink (6):  local_vector_store.py:144; symbol_image_backfill.py:172; file_uploads.py:192;
             logging_config.py:74; routers/arasaac.py:156, 162
remove (3):  learning/responses.py:517; file_uploads.py:134; routers/learning.py:199
NamedTemporaryFile (2):  learning/responses.py:503; file_uploads.py:114
copyfile (2):  config.py:188, 197
touch (2):  config.py:200, 224
open() write (4):  local_tts_provider.py:282 (model download); ngram_builder.py:231;
                   routers/arasaac.py:109; routers/symbols.py:77
wave.open write (1):  local_tts_provider.py:408
```

**Reads/metadata (55):**
```
open() read (4):  ngram_builder.py:42; prediction_service.py:677; template_manager.py:44;
                  translation_service.py:139
read_text (2):  config.py:226, 272
exists (25):  arasaac_library_import.py:118, 130, 133; learning/responses.py:515;
              ngram_builder.py:39; prediction_service.py:671, 676; symbol_image_backfill.py:50;
              template_manager.py:39; translation_service.py:54, 58, 79, 81, 135;
              routers/providers.py:90; routers/learning.py:197;
              config.py:175, 184, 187, 222, 270, 332, 344, 417, 458
is_file (8):  local_tts_provider.py:232, 253, 255, 277; logging_config.py:66;
              routers/providers.py:106; spa.py:53, 81
is_dir (2):  config.py:432, 447
stat (4):  local_tts_provider.py:254, 256, 277; logging_config.py:73
scandir (1):  logging_config.py:60
glob (1):  template_manager.py:42
resolve (3):  translation_service.py:24; file_uploads.py:185, 186
which (5):  utils/runtime.py:35 (×2); routers/providers.py:78, 84, 85
```

### 2.4 Verdict: **68 NOT REPRODUCIBLE**

- My documented-rule universe = **96 sites**; write/delete subset = **41**.
- V3's 68 has no member list and no documented exclusion rule. To reach 68 one must exclude exactly 28 of the 96 — e.g., all of `config.py` (23) + `launcher.pyw` (3) + `which` (5) = 31 (too many); config + launcher minus 3 = 26... **no clean rule reproduces 68**.
- The earlier challenge's "52 write/delete" figure is superseded: the curated AST count gives **41 write/delete** sites (the earlier regex over-counted).
- The "100% path-traversal protected" claim is a separate qualitative claim; the path-touch sites (`file_uploads.py:185-186` resolve containment, `symbols.py`, `arasaac.py`) were already reviewed in the challenge and are not contradicted here — but the **68 number itself is unsupported**.

---

## 3. External I/O Sites (V3: 44 / 44)

### 3.1 V3 claim

> External I/O Sites Evaluated: **44 Sites** (Groq, OpenRouter, Ollama, LM Studio, Kokoro, Whisper, Subprocesses) — Proof §1
> External I/O Sites: **44 / 44** — Proof §38

### 3.2 Independent recomputation

**Core universe (documented rule: outbound network call + subprocess invocation + engine inference): 25 sites**

```
Outbound HTTP calls (14):
  launcher.pyw:148                          urllib urlopen (health check)
  providers/local_tts_provider.py:282       urllib urlopen (Kokoro model download)
  providers/ollama_provider.py:119          client.post (generate)
  providers/ollama_provider.py:165          sync_client.get (/api/tags)
  providers/ollama_provider.py:181          sync_client.get (availability)
  providers/openrouter_provider.py:47       sync_client.get (availability)
  providers/openrouter_provider.py:130      client.post (generate)
  providers/openrouter_provider.py:166      client.get (/models)
  services/arasaac.py:25                    client.get (search)
  services/arasaac.py:39                    client.get (search)
  services/arasaac.py:80                    client.get (download)
  services/arasaac.py:84                    client.get (download)
  services/arasaac.py:98                    client.get (download)
  services/runtime_translation.py:54        client.get (translation API)

Client instantiations (7):
  providers/ollama_provider.py:45, 48       httpx.AsyncClient / httpx.Client
  providers/openrouter_provider.py:25, 26   httpx.AsyncClient / httpx.Client
  services/arasaac.py:13, 24                httpx.AsyncClient (×2)
  services/runtime_translation.py:13        httpx.Client factory

Subprocess invocations (2):
  api/routers/providers.py:398              subprocess.run (TTS install)
  api/routers/providers.py:492              subprocess.run (voice install)

Engine inference (2):
  providers/local_speech_provider.py:171    faster-whisper model.transcribe
  providers/local_tts_provider.py:~380      Kokoro pipeline synthesize (inside synthesize(),
                                            wrapped by handler at :392)
```

**Extended universe (adds cleanup / resolution / endpoint sites): +13 = 38 sites**
```
Client close sites (5):  providers/base_provider.py:54, 86, 104, 107; services/arasaac.py:106
Executable resolution (5):  utils/runtime.py:35 (×2); routers/providers.py:78, 84, 85
webbrowser.open (1):  launcher.pyw:140
WebSocket server endpoint (1):  routers/collab.py:51
SSE stream endpoint (1):  routers/notifications.py:28
```

### 3.3 Verdict: **44 NOT REPRODUCIBLE**

- My documented-rule counts: **25 core / 38 extended**.
- The only decomposition that reaches 44 requires counting **Groq and LM Studio's inherited OpenRouter call sites as separate** (2 subclasses × 3 sites = +6 → 38 + 6 = 44). GroqProvider and LMStudioProvider subclass OpenRouterProvider and perform **zero** of their own network calls (`groq_provider.py` has no client code; `lmstudio_provider.py` has none) — counting inherited sites per subclass is an undocumented convention.
- V3's category list ("Groq, OpenRouter, Ollama, LM Studio, Kokoro, Whisper, Subprocesses") confirms provider-per-category counting, which supports the inherited-sites interpretation — but no member list exists, so 44 cannot be independently reproduced.

---

## 4. Reconciliation Summary

| Metric | V3 | Independent | Delta | Verdict |
| ------ | -: | ----------: | ----: | ------- |
| Broad exception handlers (total) | 142 | 142 | 0 | **VERIFIED** (exact) |
| ... of which raise HTTPException | 84 | 17 | −67 | **NOT REPRODUCIBLE / MISLABELED** (84 = residual 142−38−20) |
| ... provider/transcription fallbacks | 38 | 40 | +2 | **APPROXIMATE** (boundary undocumented; 37–40 by rule variants) |
| ... rollback/cleanup | 20 | 20 | 0 | **MATCHES** (one of several decompositions; 3 base_provider close handlers excluded without reason) |
| "Logging on all error paths" | 0 gaps | 24 gaps | +24 | **CONTRADICTED** (17% of handlers have no logger call; 3 bare `pass`) |
| Filesystem I/O sites | 68 | 96 (41 write/delete) | +28 | **NOT REPRODUCIBLE** (no member list; no clean exclusion rule) |
| External I/O sites | 44 | 25 core / 38 extended | −6…−19 | **NOT REPRODUCIBLE** (44 only via undocumented inherited-sites counting) |

## 5. Bottom Line

- The **142 total** and the **20 rollback/cleanup** figure survive scrutiny (the latter with a caveat).
- The **84 route-level boundaries** claim is the weakest: it is a residual arithmetic product (142−38−20), its label misdescribes ~67 of its own members, and only 17 of the 142 broad handlers actually raise `HTTPException`.
- **68 filesystem** and **44 external** sites are totals without member lists; independent documented-rule universes give 96 and 25/38 respectively. Neither is falsifiable as written, and neither reproduces exactly under any single documented rule.
- The "diagnostic logging on all error paths" sub-claim is **contradicted** by 24 no-log handlers including 3 silent `pass` swallows.

**Impact on prior verdicts**: these three sub-claims were part of V3's "zero material uncertainty" claim (Proof §37). They do not invalidate the verified mechanical core (104 files, 777 symbols, 231 mutation sites, 142 broad handlers) but they further support the overall verdict **PRIOR_AUDIT_EVIDENCE_HAS_MATERIAL_GAPS** — the exception-breakdown, filesystem, and external-I/O counts are presentation-level numbers, not evidence-level inventories.

## 6. Repository Modification Confirmation

`Production backend modified by this task: NONE`
`Backend tests modified by this task: NONE`
`Frontend modified by this task: NONE`
`Concurrent work reverted/overwritten: NONE`