# Corrected Symbol Side-Effect Classifications

**Purpose**: Re-derive the wrong "Side Effects" classifications in `BACKEND_V3_SYMBOL_INVENTORY.md` from **actual behavior** (source reads + mutation-site scan), for the three named symbols and the systemic pattern they exemplify.

**Method**:
1. Read the full source of the three named symbols.
2. Programmatic scan: for all 777 symbol rows (file + line range), check whether a DB/file mutation site (from the independently verified 231-site ledger: `db|session.(add|commit|flush|delete|execute|rollback)`, `os.remove`, `os.unlink`, `remove_owned_upload`) falls **inside the symbol's own line range**.
3. Manually verified every borderline case (delegation, DDL, ORM-dirty, vector-store, state-reset) by reading the function.
**No code modified.**

---

## 1. The Three Named Symbols — Actual Behavior

### 1.1 `import_data` — SYM-0586, `src/api/routers/export_import.py:767-857`

**V3 label**: `Pure / Read / Dependency` — **WRONG**.

**Actual behavior** (read of full function):
1. Validates checksum (HMAC) and permission — read-only part.
2. **Writes** via four import helpers, each containing direct mutation sites:
   - `_import_boards` → `db.add(board)` @390, `db.flush()` @391, `db.add(...)` @393
   - `_import_assigned_boards` → `db.add(...)` @473
   - `_import_achievements` → `db.add(ach)` @502, `db.flush()` @503
   - `_import_learning_history` → `db.add(LearningSession(...))` @600
3. **Single atomic `db.commit()` @855** ("Keep the entire import atomic: commit once...").

**Correct classification**: **DB WRITE (multi-table insert: boards, assignments, achievements, learning sessions) + transaction commit + auth/checksum validation**. It is a mutation orchestrator, not pure.

### 1.2 `log_symbol_usage_legacy` — SYM-0508, `src/api/routers/analytics.py:314-339`

**V3 label**: `Pure / Read / Dependency` — **WRONG**.

**Actual behavior** (read of full function + its delegate):
- Delegates to `_log_usage_request` (analytics.py:36-65), which inserts a `SymbolUsageLog` row (via `symbol_analytics` service `session.add(usage_log)` + `flush` — mutation ledger `symbol_analytics.py:180-181`) and **`db.commit()` @64**.
- Returns `{"status": "success"}` (201).

**Correct classification**: **DB WRITE (insert into `SymbolUsageLog`) + transaction commit + exception mapping (HTTPException re-raise, 500 fallback)**. Not pure.

### 1.3 `remove_owned_upload` — SYM-0483, `src/api/file_uploads.py:177-195`

**V3 label**: `Route Handler / DB Mutation` — **WRONG**.

**Actual behavior** (read of full function):
- Pure **filesystem deletion helper**: validates `/uploads/` prefix, directory containment (`candidate.relative_to(root)`), then `candidate.unlink(missing_ok=True)` @192.
- `OSError` suppressed (best-effort cleanup). **Zero DB interaction.**

**Correct classification**: **FILESYSTEM DELETE (best-effort, path-containment-guarded)**. It is the file-deletion mechanism used by symbol delete/image-replace flows — not a DB mutation, and not a route handler.

---

## 2. Systemic Scan Results (all 777 rows)

### 2.1 Labeled `Pure / Read / Dependency` but CONTAINS a mutation site in its own body — **31 rows**

These are unambiguous classification errors (the mutation is in the symbol's own line range):

| SYM | File | Symbol | Mutation site(s) inside body |
| :--- | :--- | :--- | :--- |
| SYM-0015 | `src/aac_app/db.py` | `get_session` (123-133) | `commit` @128, `rollback` @130 — it is a **transaction boundary**, not pure |
| SYM-0117 | `src/aac_app/seed.py` | `_ensure_bootstrap_admin` (85-141) | `add` @132, `flush` @141 |
| SYM-0178 | `services/arasaac_library_import.py` | `_mark_imported` (60-71) | `db.add(AppSettings(...))` @69 |
| SYM-0179 | same | `import_arasaac_library` (74-171) | `db.add` @143 + `path.write_bytes` @134 |
| SYM-0436 | `src/api/deps/db.py` | `get_db` (10-20) | `commit` @15, `rollback` @17 — transaction boundary |
| SYM-0484 | `src/api/logging_config.py` | `_cleanup_old_logs` (45-81) | `os.unlink` @74 |
| SYM-0498 | `routers/achievements.py` | `award_achievement` (367-438) | `add` @423, `commit` @424 |
| SYM-0500 | same | `check_achievements` (462-484) | `commit` @481 |
| SYM-0504 | `routers/analytics.py` | `_log_usage_request` (36-65) | `commit` @64 (writes SymbolUsageLog) |
| SYM-0514 | `routers/arasaac.py` | `import_arasaac_symbol` (62-171) | `add` @138, `commit` @139, `rollback` @153,159 + `file_path.open("wb")` |
| SYM-0517 | `routers/auth.py` | `initial_admin_setup` (62-171) | `add` @130, `flush` @131, `commit` @143 |
| SYM-0519 | same | `logout` (353-374) | `mark_credentials_changed` + `commit` @373 |
| SYM-0521 | same | `register` (482-542) | `add` @523, `flush` @524, `commit` @540 |
| SYM-0540 | `routers/auth_users.py` | `change_password` (350-425) | `mark_credentials_changed` @407 + commit |
| SYM-0550 | `routers/board_ai.py` | `apply_ai_suggestion` (391-501) | `delete` @460, `add` @493, `commit` @494,498 |
| SYM-0552 | `routers/board_assignments.py` | `assign_board_to_student` (50-98) | `add` @96, `commit` @97 |
| SYM-0553 | same | `unassign_board_from_student` (102-141) | `delete` @139, `commit` @140 |
| SYM-0582 | `routers/export_import.py` | `_import_assigned_boards` (434-479) | `add` @473 |
| SYM-0583 | same | `_import_achievements` (482-544) | `add` @502, `flush` @503 |
| SYM-0584 | same | `_import_learning_history` (547-610) | `add` @600 |
| SYM-0586 | same | `import_data` (767-857) | see §1.1 |
| SYM-0603 | `routers/learning.py` | `submit_voice_answer` (152-207) | `os.remove(temp_path)` @199 |
| SYM-0613 | `routers/notifications.py` | `notifications_stream` (29-99) | `rollback` @54 |
| SYM-0616 | same | `mark_notification_read` (199-224) | `commit` @222 |
| SYM-0617 | same | `mark_all_notifications_read` (228-249) | `commit` @247 |
| SYM-0635 | `routers/settings.py` | `set_settings` (49-66) | `add` @62 |
| SYM-0654 | `routers/symbols.py` | `reorder_symbols` (264-299) | `commit` @289 |
| SYM-0659 | same | `add_symbol_to_board` (435-485) | `add` @458, `commit` @459 |
| SYM-0663 | same | `remove_symbol_from_board` (627-638) | `delete` @636, `commit` @637 |
| SYM-0668 | `routers/users.py` | `assign_student` (123-181) | `add` @176, `commit` @177 |
| SYM-0669 | same | `unassign_student` (185-225) | `delete` @223, `commit` @224 |

### 2.2 Labeled `Route Handler / DB Mutation` but contains NO mutation site — **27 rows**

Split by manual verification:

**Correct label (mutation via DDL, delegation, or ORM-dirty) — 5:**
| SYM | Symbol | Why correct |
| :--- | :--- | :--- |
| SYM-0503 | `admin.reset_database` | `Base.metadata.drop_all` + `create_all` (DDL — not captured by the SQLAlchemy-call regex, but genuinely destructive DB mutation) |
| SYM-0014 | `db.create_tables` | `Base.metadata.create_all(engine)` (DDL) |
| SYM-0600 | `learning.start_session` | orchestrates `service.start_learning_session` which commits internally (`learning/session.py:103`) |
| SYM-0660 | `symbols._update_single_symbol` | mutates ORM attributes (`db_board_symbol.symbol_id = ...`) → dirty-tracking DB write |
| SYM-0012 | `db.create_engine_instance` | DB infrastructure (engine + PRAGMAs) — borderline; call it **PARTIAL** |

**Wrong label — no DB mutation at all — 22:**
| SYM | Symbol | Actual behavior |
| :--- | :--- | :--- |
| SYM-0001 | `launcher._startup_log_directories` | filesystem mkdir + log dir setup |
| SYM-0002 | `launcher._write_startup_error` | filesystem write (`startup_error.log`) |
| SYM-0004 | `launcher._start_shutdown_watcher` | named-event thread setup |
| SYM-0013 | `db.create_session_factory` | factory construction (no DB call) |
| SYM-0096 | `local_tts_provider.reset_local_tts_provider` | module-state reset (singleton) |
| SYM-0192 | `auth_service.verify_password_and_update` | **pure hash verification**; returns replacement hash for the *caller* to persist |
| SYM-0407 | `vector_utils.delete_symbol` | **vector-store delete** (embedding), not DB |
| SYM-0408 | `vector_utils._delete_symbol` | same |
| SYM-0411 | `jwt_utils.create_access_token` | **pure token generation** (`_encode_token`), no DB |
| SYM-0415 | `jwt_utils.create_refresh_token` | same |
| SYM-0437 | `providers._new_startup_state` | state object construction |
| SYM-0441 | `providers._start_deferred_vector_store_close` | async task scheduling |
| SYM-0442 | `providers._defer_vector_store_for_reset` | state bookkeeping |
| SYM-0443 | `providers._detach_vector_store_for_reset` | vector-store close |
| SYM-0470 | `providers.get_startup_state` | read-only state accessor |
| SYM-0472 | `providers.reset_providers` | **module-state reset** (singletons + locks), no DB |
| SYM-0473 | `providers.reset_speech_provider` | singleton reset |
| SYM-0474 | `providers.reset_llm_providers` | singleton reset |
| SYM-0475 | `providers.reset_providers_async` | singleton reset (async) |
| SYM-0480 | `file_uploads.read_upload_bytes` | **pure bounded file read** |
| SYM-0482 | `file_uploads.read_image_upload` | pure image validation (returns content+suffix) |
| SYM-0483 | `file_uploads.remove_owned_upload` | **filesystem delete** (see §1.3) |
| SYM-0527 | `auth_helpers.validate_preference_updates` | pure validation (400 on bad values) |

---

## 3. Root Cause

The V3 "Side Effects" column was **canned boilerplate** assigned per *kind* (function/method/class) rather than derived from the symbol's body:
- All route handlers and helpers got one of two generic strings (`Pure / Read / Dependency` or `Route Handler / DB Mutation`) with no per-symbol analysis.
- The `Callers/Reachability` column shows the same pattern ("Route Handler / Dependency / Helper Call" on launcher functions that are none of those).

**Net effect**: at least **53 of 777 rows (6.8%)** have demonstrably incorrect side-effect labels (31 false-pure + 22 false-DB-mutation), plus ~5 borderline. The three named symbols are representative, not exceptional.

## 4. Corrected Classification for the Three Named Symbols

| Symbol | V3 label | Correct label | Evidence |
| :--- | :--- | :--- | :--- |
| `import_data` | Pure / Read | **DB WRITE (multi-table) + commit** | export_import.py:390-393,473,502-503,600,855 |
| `log_symbol_usage_legacy` | Pure / Read | **DB WRITE (insert) + commit** | analytics.py:36-65 (`_log_usage_request`), commit @64; symbol_analytics.py:180-181 |
| `remove_owned_upload` | Route Handler / DB Mutation | **FILESYSTEM DELETE (best-effort)** | file_uploads.py:177-195, unlink @192 |

## 5. Verification Evidence (commands)

- Full source reads: `analytics.py:300-359`, `export_import.py:760-857`, `file_uploads.py:175-195`
- Borderline verification reads: `jwt_utils.py:60-89`, `file_uploads.py:50-60`, `providers.py:992-1023`, `auth_service.py:67-96`, `vector_utils.py:205-225`, `auth_helpers.py:109-147`, `symbols.py:488-544`
- 231-site mutation ledger (independently verified set-identical in the challenge) intersected with every symbol row's line range
- V3 row extraction: `grep log_symbol_usage_legacy|import_data|remove_owned_upload|_log_usage_request BACKEND_V3_SYMBOL_INVENTORY.md`

**No application source, test, or frontend file was modified by this task.**