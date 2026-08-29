# No-Log Broad Exception Handlers — Swallow-Risk Audit

**Date**: 2026-08-28
**Scope**: The 24 broad (`except Exception` / bare `except`) handlers that contain **no `logger` call** (identified in `BACKEND_EVIDENCE_CHALLENGE_V3_SUBCLAIMS.md` §1.7, which contradicted V3's "diagnostic logging is present on all error paths"). This audit reads each handler in context and classifies **actual swallow risk** — silent failure vs. error that is surfaced elsewhere (re-raise, outer log, response payload, stored state).

**Method**: every site re-derived via AST (24 sites), then each read in context including its enclosing function and the code that catches/receives its error.

---

## 1. Classification Summary

| Class | Count | Meaning |
| :--- | ---: | :--- |
| **NEEDS LOGGING** (real swallow risk) | **9** | Exception swallowed; no re-raise, no error surfaced, no outer log |
| **OK — error surfaced** | **15** | Re-raise, outer handler logs, error in response, or stored for later reporting |
| **Total** | **24** | matches the V3-sub-claims audit |

---

## 2. NEEDS LOGGING — 9 sites (real silent-swallow risk)

### 2.1 `src/aac_app/services/learning/responses.py:424-425` — **HIGHEST RISK**
```python
ach.check_achievements(session.user_id, db=db)
except Exception:
    pass
```
- **What fails silently**: achievement checking + voice-usage progress tracking inside the answer path.
- **Impact**: users silently stop earning achievements / voice stats stop incrementing; no trace in logs.
- **Recommendation**: `logger.warning("Achievement check failed for user {}: {}", session.user_id, exc)`.

### 2.2 `src/aac_app/services/local_vector_store.py:477-478` — **MEDIUM**
```python
except Exception:
    self.metadata = []
```
- **What fails silently**: vector-store metadata load; on failure the in-memory metadata is **wiped to empty**.
- **Impact**: subsequent stale-embedding inspection/cleanup (`_inspect_stale`) runs against empty metadata — may delete embeddings that were actually valid, or skip cleanup entirely. Silent state corruption.
- **Recommendation**: `logger.error("Could not load vector-store metadata: %s", exc)` (keep the empty fallback).

### 2.3 `launcher.pyw:41-44` — **MEDIUM (startup)**
```python
try:
    from src import config
    add_candidate(config.RUNTIME_ROOT / "logs")
except Exception:
    # The config import may be the original startup failure. ...
    pass
```
- **What fails silently**: `src.config` import at launcher startup — potentially **the original startup failure** (the comment says so).
- **Impact**: the log directory candidate is skipped and the true startup failure is never recorded; the launcher proceeds with fallback dirs and the root cause stays invisible.
- **Recommendation**: `logger.warning("Config import failed while resolving log dirs: %s", exc)` (or write to the fallback startup-error file).

### 2.4 `src/api/routers/collab.py:42-43` — **LOW-MEDIUM**
```python
except Exception:
    self.disconnect(board_id, ws)
```
- **What fails silently**: WebSocket `send_json` failure → connection dropped, no log.
- **Impact**: repeated send failures (e.g., a wedged client) are invisible; operators can't tell why boards lose participants.
- **Recommendation**: `logger.debug/warning("WebSocket send failed for board {}: %s", board_id, exc)`.

### 2.5 `src/api/routers/arasaac.py:53-54` — **LOW-MEDIUM**
```python
except Exception:
    pass
```
- **What fails silently**: reading `current_user.settings.ui_language` for search locale; falls back to `"es"`.
- **Impact**: user's UI-language preference silently ignored for ARASAAC search when the settings read fails.
- **Recommendation**: `logger.debug(...)`.

### 2.6 `src/api/routers/arasaac.py:126-127` — **LOW-MEDIUM**
```python
except Exception:
    user_lang = None
```
- **What fails silently**: same settings-read pattern in `import_symbol`; language falls back to `None`.
- **Impact**: imported symbol gets default language instead of user's UI language.
- **Recommendation**: `logger.debug(...)`.

### 2.7 `src/aac_app/services/learning/service.py:220-221` — **LOW**
```python
except Exception:
    pass
return "es"
```
- **What fails silently**: user-language settings lookup; falls back to `"es"`.
- **Impact**: wrong default language for sessions; DB error here would fail the request later anyway, but the silent fallback masks the read failure.
- **Recommendation**: `logger.debug(...)`.

### 2.8 `src/aac_app/providers/local_tts_provider.py:121-122` — **LOW**
```python
except Exception:  # pragma: no cover - environment dependent
    return None
```
- **What fails silently**: Kokoro voice-catalog listing (`np.load`); returns `None`.
- **Impact**: voice list empty; TTS still degrades gracefully but the cause is invisible.
- **Recommendation**: `logger.debug(...)`.

### 2.9 `src/aac_app/providers/ollama_provider.py:37-38` — **NEGLIGIBLE**
```python
except Exception:
    env_model = None
```
- **What fails silently**: `import os` / `os.getenv("OLLAMA_MODEL")` — practically cannot fail.
- **Impact**: none in practice; purely defensive.
- **Recommendation**: optional `logger.debug(...)`; lowest priority.

---

## 3. OK / Error surfaced — 15 sites (no action needed)

| Site | What surfaces the error |
| :--- | :--- |
| `src/aac_app/db.py:129-131` | `session.rollback(); raise` — propagates; caller/framework logs |
| `src/api/deps/db.py:16-18` | `db.rollback(); raise` — propagates; Starlette logs 500 |
| `src/api/file_uploads.py:131-135` | temp-file cleanup then `raise`; propagates to route |
| `src/api/routers/symbols.py:336-339` | rollback + `remove_owned_upload` cleanup + `raise` — Starlette logs 500 |
| `src/api/routers/symbols.py:394-397` | same (image update) |
| `src/aac_app/services/learning/questions.py:262-263` | `raise RuntimeError(...) from exc` — chain preserved; caller maps to 400 and logs |
| `src/aac_app/services/learning/responses.py:154-155` | `raise RuntimeError(...) from exc` — same |
| `src/aac_app/services/learning/responses.py:319-320` | `raise RuntimeError(...) from exc` — same |
| `src/aac_app/services/prediction_service.py:439-440` | `raise RuntimeError(...) from exc` — same |
| `src/aac_app/services/prediction_service.py:482-483` | `raise RuntimeError(...) from exc` — same |
| `src/aac_app/services/learning/responses.py:403-405` | inner `raise` caught by **outer handler at :406 that logs** `logger.warning(f"Failed to log symbol usage analytics: {e}")` |
| `src/aac_app/services/runtime_translation.py:98-99` | error stored in `result_holder`; **caller at :168 logs** `logger.warning(f"Translation failed for {text!r}: {exc}")` |
| `src/api/deps/providers.py:849-856` | error captured in `_InitializationResult.error`; **caller at :924 logs** `logger.error(f"Warmup: Exception initializing {name}: {exc}")` |
| `src/api/routers/providers.py:530-531` | returns `{"models": [], "error": str(e)}` — **error visible in response payload** |
| `src/aac_app/providers/local_tts_provider.py:208-210` | `_import_error = str(exc)` stored; **surfaced via provider status/availability reporting** |

---

## 4. Priority order (if implementing)

| Priority | Sites | Rationale |
| :--- | :--- | :--- |
| P1 | `responses.py:424` (achievements) | User-visible feature silently degrades |
| P2 | `local_vector_store.py:477` (metadata wipe) | Silent state corruption risk |
| P3 | `launcher.pyw:41` (config import) | Startup root-cause invisibility |
| P4 | `collab.py:42`, `arasaac.py:53,126`, `learning/service.py:220` | Silent preference/degradation fallbacks |
| P5 | `local_tts_provider.py:121`, `ollama_provider.py:37` | Environment-dependent, low impact |

**Net effect on V3's claim**: V3's "Swallowed Bugs: 0 / Diagnostic logging is present on all error paths" is **contradicted** — 9 of 24 no-log handlers (37%) genuinely swallow failures with no trace; the 15 others are safe because the error is surfaced through re-raise, outer log, response, or stored state. The 9 at-risk sites are the concrete evidence behind the contradiction.

## 5. Implementation Follow-up (2026-08-28)

The nine at-risk handlers were instrumented without changing their fallback/re-raise behavior:

| Site | Added behavior |
| :--- | :--- |
| `learning/responses.py:424` | Warning with session/user IDs on achievement-update failure |
| `local_vector_store.py:477` | Error with exception on metadata-load failure |
| `launcher.pyw:41` | Writes configuration-import failure to `stderr` (avoids recursive startup-log discovery) |
| `collab.py:42` | Debug message with board ID before disconnect |
| `arasaac.py:53,126` | Debug messages for UI-language lookup failures |
| `learning/service.py:220` | Debug message with user ID for language lookup failure |
| `local_tts_provider.py:121` | Debug message for voice-catalog load failure |
| `local_tts_provider.py:208` | Debug message for Kokoro import failure |
| `ollama_provider.py:37` | Debug message for `OLLAMA_MODEL` lookup failure |

### Verification

- Targeted affected tests: **95 passed, 1 warning** across learning, vector-store, ARASAAC, provider, TTS, and WebSocket test files.
- Targeted syntax compilation: passed for all 9 modified source files plus `launcher.pyw`.
- `git diff --check`: clean.
- No full suite, global coverage, frontend QA, or PR gate was run.

## 6. Repository Modification Confirmation

`Production backend modified by this task: YES — 9 narrowly scoped logging additions`
`Backend tests modified by this task: NONE`
`Frontend modified by this task: NONE`
`Concurrent work reverted/overwritten: NONE`

Pre-existing unrelated working-tree changes in `ollama_provider.py` (removal of `close()`) and `api/routers/providers.py` (LM Studio fallback changes) were observed and left untouched; this task did not revert or overwrite them.