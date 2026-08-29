# Backend Evidence Challenge — Raw Independent Inventory

**Purpose**: Raw members underlying every important independent count, so a human reviewer can reproduce them. Generated from the current working tree via AST, regex, and live FastAPI introspection. V3 inventory rows were not used as input.

---

## 1. Production Files (104)

### 1.1 `src/` Python files (103)

```
src/__init__.py
src/aac_app/__init__.py
src/aac_app/db.py
src/aac_app/models/__init__.py
src/aac_app/models/achievement.py
src/aac_app/models/analytics.py
src/aac_app/models/audit_log.py
src/aac_app/models/base.py
src/aac_app/models/board.py
src/aac_app/models/collaboration.py
src/aac_app/models/guardian.py
src/aac_app/models/learning.py
src/aac_app/models/notification.py
src/aac_app/models/settings.py
src/aac_app/models/symbol.py
src/aac_app/models/user.py
src/aac_app/providers/__init__.py
src/aac_app/providers/base_provider.py
src/aac_app/providers/groq_provider.py
src/aac_app/providers/lmstudio_provider.py
src/aac_app/providers/local_speech_provider.py
src/aac_app/providers/local_tts_provider.py
src/aac_app/providers/ollama_provider.py
src/aac_app/providers/openrouter_provider.py
src/aac_app/schema.py
src/aac_app/seed.py
src/aac_app/services/__init__.py
src/aac_app/services/aac_expander_service.py
src/aac_app/services/achievement_catalog.py
src/aac_app/services/achievement_system.py
src/aac_app/services/arasaac.py
src/aac_app/services/arasaac_library_import.py
src/aac_app/services/audit_service.py
src/aac_app/services/auth_service.py
src/aac_app/services/board_generation_service.py
src/aac_app/services/credential_service.py
src/aac_app/services/guardian_profile_service.py
src/aac_app/services/learning/__init__.py
src/aac_app/services/learning/common.py
src/aac_app/services/learning/history.py
src/aac_app/services/learning/questions.py
src/aac_app/services/learning/responses.py
src/aac_app/services/learning/service.py
src/aac_app/services/learning/session.py
src/aac_app/services/learning/summaries.py
src/aac_app/services/local_vector_store.py
src/aac_app/services/lockout_service.py
src/aac_app/services/ngram_builder.py
src/aac_app/services/notification_events.py
src/aac_app/services/prediction_service.py
src/aac_app/services/runtime_translation.py
src/aac_app/services/symbol_analytics.py
src/aac_app/services/symbol_catalog.py
src/aac_app/services/symbol_image_backfill.py
src/aac_app/services/symbol_semantics.py
src/aac_app/services/template_manager.py
src/aac_app/services/translation_service.py
src/aac_app/services/user_service.py
src/aac_app/services/vector_utils.py
src/aac_app/utils/__init__.py
src/aac_app/utils/jwt_utils.py
src/aac_app/utils/module_availability.py
src/aac_app/utils/runtime.py
src/api/__init__.py
src/api/deps/__init__.py
src/api/deps/access.py
src/api/deps/auth.py
src/api/deps/db.py
src/api/deps/providers.py
src/api/deps/settings.py
src/api/file_uploads.py
src/api/limiter.py
src/api/logging_config.py
src/api/main.py
src/api/routers/__init__.py
src/api/routers/achievements.py
src/api/routers/admin.py
src/api/routers/analytics.py
src/api/routers/arasaac.py
src/api/routers/auth.py
src/api/routers/auth_helpers.py
src/api/routers/auth_preferences.py
src/api/routers/auth_users.py
src/api/routers/board_ai.py
src/api/routers/board_assignments.py
src/api/routers/board_helpers.py
src/api/routers/boards.py
src/api/routers/collab.py
src/api/routers/config.py
src/api/routers/export_import.py
src/api/routers/guardian_profiles.py
src/api/routers/learning.py
src/api/routers/learning_modes.py
src/api/routers/notifications.py
src/api/routers/providers.py
src/api/routers/settings.py
src/api/routers/symbols.py
src/api/routers/users.py
src/api/schemas.py
src/api/server.py
src/api/spa.py
src/config.py
src/scripts/account_admin.py
```

### 1.2 Entry point (1)

```
launcher.pyw
```

### 1.3 Exclusions challenged

| Excluded | Why excluded | Challenge verdict |
| :--- | :--- | :--- |
| `src/frontend/node_modules/flatted/python/flatted.py` | Vendored third-party dependency inside node_modules | **CORRECT** — not project-owned production code |
| `scripts/*.py` (16 files) | Operator/maintenance scripts outside `src/` | **PARTIALLY DEFENSIBLE** — they ARE project-owned and executable (`verify_pr.py`, `run_server.py`, `migrate_passwords.py` run in production ops), but V3's 104-file universe explicitly scoped to `src/` + launcher. Documented, not hidden. |
| `tests/` | Test code | CORRECT |

---

## 2. FastAPI Operations (127) — live route table

### 2.1 Full tuple list (method, path, module.handler)

```
GET    /api/achievements            src.api.routers.achievements.list_all_achievements
GET    /api/achievements/           src.api.routers.achievements.list_all_achievements   (trailing-slash dup)
POST   /api/achievements            src.api.routers.achievements.create_achievement
POST   /api/achievements/           src.api.routers.achievements.create_achievement     (trailing-slash dup)
GET    /api/achievements/categories     src.api.routers.achievements.get_categories
GET    /api/achievements/criteria-types src.api.routers.achievements.get_criteria_types
GET    /api/achievements/leaderboard    src.api.routers.achievements.get_leaderboard
GET    /api/achievements/user/{user_id} src.api.routers.achievements.get_user_achievements
POST   /api/achievements/user/{user_id}/check   src.api.routers.achievements.check_achievements
GET    /api/achievements/user/{user_id}/points  src.api.routers.achievements.get_user_points
DELETE /api/achievements/{achievement_id}       src.api.routers.achievements.delete_achievement
PUT    /api/achievements/{achievement_id}       src.api.routers.achievements.update_achievement
POST   /api/achievements/{achievement_id}/award src.api.routers.achievements.award_achievement
POST   /api/admin/reset-db            src.api.routers.admin.reset_database
GET    /api/analytics/category-preferences    src.api.routers.analytics.get_category_preferences
GET    /api/analytics/frequent-sequences      src.api.routers.analytics.get_frequent_sequences
POST   /api/analytics/log             src.api.routers.analytics.log_symbol_usage_legacy
POST   /api/analytics/next-symbol     src.api.routers.analytics.get_next_symbol_suggestions_post
POST   /api/analytics/usage           src.api.routers.analytics.log_symbol_usage
GET    /api/analytics/usage-stats     src.api.routers.analytics.get_usage_statistics
POST   /api/arasaac/import            src.api.routers.arasaac.import_arasaac_symbol
GET    /api/arasaac/search            src.api.routers.arasaac.search_arasaac
POST   /api/auth/admin/create-user    src.api.routers.auth_users.admin_create_user
POST   /api/auth/admin/unlock-account src.api.routers.auth_users.admin_unlock_account
POST   /api/auth/change-password      src.api.routers.auth_users.change_password
POST   /api/auth/login                src.api.routers.auth.login
POST   /api/auth/logout               src.api.routers.auth.logout
GET    /api/auth/me                   src.api.routers.auth_users.get_current_user_info
GET    /api/auth/preferences          src.api.routers.auth_preferences.get_preferences
PUT    /api/auth/preferences          src.api.routers.auth_preferences.update_preferences
PUT    /api/auth/profile              src.api.routers.auth_users.update_profile
POST   /api/auth/refresh              src.api.routers.auth.refresh_access_token
POST   /api/auth/register             src.api.routers.auth.register
POST   /api/auth/setup                src.api.routers.auth.initial_admin_setup
GET    /api/auth/setup-status         src.api.routers.auth.get_setup_status
POST   /api/auth/token                src.api.routers.auth.login_for_access_token
GET    /api/auth/users                src.api.routers.auth_users.get_users
GET    /api/auth/users/student-summaries  src.api.routers.auth_users.get_student_summaries
DELETE /api/auth/users/{user_id}      src.api.routers.auth_users.delete_user
GET    /api/auth/users/{user_id}      src.api.routers.auth_users.get_user
PUT    /api/auth/users/{user_id}      src.api.routers.auth_users.update_user
GET    /api/auth/users/{user_id}/preferences  src.api.routers.auth_preferences.get_user_preferences
PUT    /api/auth/users/{user_id}/preferences  src.api.routers.auth_preferences.update_user_preferences
GET    /api/boards                    src.api.routers.boards.get_boards
GET    /api/boards/                   src.api.routers.boards.get_boards              (trailing-slash dup)
POST   /api/boards                    src.api.routers.board_ai.create_board
POST   /api/boards/                   src.api.routers.board_ai.create_board          (trailing-slash dup)
GET    /api/boards/assigned           src.api.routers.board_assignments.get_assigned_boards
GET    /api/boards/symbols            src.api.routers.symbols.get_symbols
POST   /api/boards/symbols            src.api.routers.symbols.create_symbol
GET    /api/boards/symbols/categories src.api.routers.symbols.get_symbol_categories
PUT    /api/boards/symbols/reorder    src.api.routers.symbols.reorder_symbols
POST   /api/boards/symbols/upload     src.api.routers.symbols.upload_symbol
DELETE /api/boards/symbols/{symbol_id} src.api.routers.symbols.delete_symbol
PUT    /api/boards/symbols/{symbol_id} src.api.routers.symbols.update_symbol
POST   /api/boards/symbols/{symbol_id}/image  src.api.routers.symbols.update_symbol_image
DELETE /api/boards/{board_id}         src.api.routers.boards.delete_board
GET    /api/boards/{board_id}         src.api.routers.boards.get_board
PUT    /api/boards/{board_id}         src.api.routers.boards.update_board
POST   /api/boards/{board_id}/ai/suggestions      src.api.routers.board_ai.generate_ai_suggestions
POST   /api/boards/{board_id}/ai/suggestions/apply src.api.routers.board_ai.apply_ai_suggestion
POST   /api/boards/{board_id}/assign  src.api.routers.board_assignments.assign_board_to_student
DELETE /api/boards/{board_id}/assign/{student_id} src.api.routers.board_assignments.unassign_board_from_student
POST   /api/boards/{board_id}/symbols src.api.routers.symbols.add_symbol_to_board
PUT    /api/boards/{board_id}/symbols/batch  src.api.routers.symbols.batch_update_board_symbols
DELETE /api/boards/{board_id}/symbols/{symbol_id} src.api.routers.symbols.remove_symbol_from_board
PUT    /api/boards/{board_id}/symbols/{symbol_id} src.api.routers.symbols.update_board_symbol
WS     /api/collab/boards/{board_id}  src.api.routers.collab.board_channel
GET    /api/config                    src.api.routers.config.get_config
GET    /api/data/export               src.api.routers.export_import.export_data
POST   /api/data/import               src.api.routers.export_import.import_data
GET    /api/guardian-profiles/students            src.api.routers.guardian_profiles.list_students_with_profiles
DELETE /api/guardian-profiles/students/{student_id} src.api.routers.guardian_profiles.delete_student_profile
GET    /api/guardian-profiles/students/{student_id} src.api.routers.guardian_profiles.get_student_profile
POST   /api/guardian-profiles/students/{student_id} src.api.routers.guardian_profiles.create_student_profile
PUT    /api/guardian-profiles/students/{student_id} src.api.routers.guardian_profiles.update_student_profile
GET    /api/guardian-profiles/students/{student_id}/effective-profile src.api.routers.guardian_profiles.get_effective_profile
GET    /api/guardian-profiles/students/{student_id}/history src.api.routers.guardian_profiles.get_profile_history
GET    /api/guardian-profiles/students/{student_id}/system-prompt src.api.routers.guardian_profiles.get_student_system_prompt
GET    /api/guardian-profiles/templates            src.api.routers.guardian_profiles.list_templates
GET    /api/guardian-profiles/templates/{template_name} src.api.routers.guardian_profiles.get_template
POST   /api/guardian-profiles/templates/{template_name}/preview src.api.routers.guardian_profiles.preview_template
GET    /api/health                    src.api.main.root
GET    /api/learning-modes/           src.api.routers.learning_modes.get_learning_modes
POST   /api/learning-modes/           src.api.routers.learning_modes.create_learning_mode
POST   /api/learning-modes/preview    src.api.routers.learning_modes.preview_learning_mode_system_prompt
DELETE /api/learning-modes/{mode_id}  src.api.routers.learning_modes.delete_learning_mode
PUT    /api/learning-modes/{mode_id}  src.api.routers.learning_modes.update_learning_mode
GET    /api/learning/history/{user_id} src.api.routers.learning.get_history
POST   /api/learning/start            src.api.routers.learning.start_session
POST   /api/learning/{session_id}/answer src.api.routers.learning.submit_answer
POST   /api/learning/{session_id}/answer/symbols src.api.routers.learning.submit_symbol_answer
POST   /api/learning/{session_id}/answer/voice src.api.routers.learning.submit_voice_answer
POST   /api/learning/{session_id}/ask  src.api.routers.learning.ask_question
POST   /api/learning/{session_id}/end  src.api.routers.learning.end_session
GET    /api/learning/{session_id}/progress src.api.routers.learning.get_progress
GET    /api/notifications              src.api.routers.notifications.get_notifications
POST   /api/notifications              src.api.routers.notifications.create_notification
POST   /api/notifications/             src.api.routers.notifications.create_notification   (trailing-slash dup)
PUT    /api/notifications/read-all     src.api.routers.notifications.mark_all_notifications_read
GET    /api/notifications/stream       src.api.routers.notifications.notifications_stream
DELETE /api/notifications/{notification_id} src.api.routers.notifications.delete_notification
PUT    /api/notifications/{notification_id}/read src.api.routers.notifications.mark_notification_read
GET    /api/providers/ai/models/lmstudio src.api.routers.providers.get_lmstudio_models
GET    /api/providers/health           src.api.routers.providers.providers_health
PUT    /api/providers/stt/model        src.api.routers.providers.update_stt_model
POST   /api/providers/tts/install      src.api.routers.providers.install_tts_dependencies
POST   /api/providers/tts/synthesize   src.api.routers.providers.tts_synthesize
GET    /api/providers/voice-status     src.api.routers.providers.voice_status
POST   /api/providers/voice/install    src.api.routers.providers.install_voice_dependencies
POST   /api/providers/warmup           src.api.routers.providers.warmup_models
GET    /api/settings/ai                src.api.routers.settings.get_ai_settings
PUT    /api/settings/ai                src.api.routers.settings.update_ai_settings
GET    /api/settings/ai/models/groq    src.api.routers.settings.get_groq_models
GET    /api/settings/ai/models/lmstudio src.api.routers.settings.get_lmstudio_models
GET    /api/settings/ai/models/ollama  src.api.routers.settings.get_ollama_models
GET    /api/settings/ai/models/openrouter src.api.routers.settings.get_openrouter_models
GET    /api/settings/ui                src.api.routers.settings.get_ui_language
PUT    /api/settings/ui                src.api.routers.settings.update_ui_language
POST   /api/users/assign-student       src.api.routers.users.assign_student
DELETE /api/users/assign-student/{student_id}/{teacher_id} src.api.routers.users.unassign_student
GET    /api/users/me                   src.api.routers.users.get_current_user_info
PUT    /api/users/me                   src.api.routers.users.update_current_user
POST   /api/users/reset-password       src.api.routers.users.reset_user_password
GET    /api/users/students             src.api.routers.users.get_students
POST   /api/users/students             src.api.routers.users.create_student
GET    /ready                          src.api.main.readiness_check
```

Count: **127** (126 HTTP + 1 WS). Distinct paths: **103**. Normalized: **100**. Excluded: `/docs`, `/docs/oauth2-redirect`, `/openapi.json`, `/redoc` (FastAPI docs), `/uploads` mount (2 mounts).

### 2.2 Reconciliation with the "126 / 127 / 100 / 67" figures

- **126** = V3's HTTP-only count (correct for HTTP, missing WS).
- **127** = full app operations (126 HTTP + WS collab).
- **103** = distinct registered paths (including trailing-slash variants).
- **100** = normalized paths (trailing slashes collapsed).
- **67** = V1 manual grouping count, stale; not reproducible from the route table.

---

## 3. DB Mutation Sites (231) — full raw list

Generated by regex over all 104 files. Each entry: `(file, line)` — all 231 matched V3's ledger exactly (V3-only: 0, independent-only: 0). Breakdown:

| Kind | Count |
| :--- | ---: |
| `db.add(` / `session.add(` | 63 |
| `db.commit(` / `session.commit(` | 67 |
| `db.delete(` / `session.delete(` | 11 |
| `db.execute(` | 28 |
| `db.flush(` / `session.flush(` | 41 |
| `db.rollback(` / `session.rollback(` | 11 |
| `os.remove(` / `os.unlink(` | 4 |
| `remove_owned_upload(` | 6 |
| **Total** | **231** |

Representative members (full set is the 231 (file:line) pairs; key sites):
- `src/aac_app/db.py:128-130` (session_scope commit/rollback)
- `src/aac_app/seed.py:132,141,205-206,217,240,248,264,273,316,418,420,456,473,475`
- `src/aac_app/services/achievement_system.py:93,295-296,302,319-320,346,357-358,578,580`
- `src/aac_app/services/learning/session.py:57-58,67-68,81-82,103`
- `src/aac_app/services/learning/responses.py:402-404,517,523-524`
- `src/api/deps/db.py:15,17`
- `src/api/routers/auth.py:130-131,143,204,225,244,283,307-308,312,372-373,523-524,540,602-603,606`
- `src/api/routers/auth_users.py:132-133,161,408-409,423,536-538,592-755` (delete_user cascade: `db.execute(delete(...))` at 685,697,699,700,701,702,744; commit at 755)
- `src/api/routers/board_ai.py:101-102,157,159,185,252,263,267,281,460,493-494,498`
- `src/api/routers/boards.py:188,215-216`
- `src/api/routers/export_import.py:390-393,473,502-503,533,600,855`
- `src/api/routers/symbols.py:80,254-255,289,292,333,335,337-338,371,393,395-396,402,427-429,458-459,579,621,636-637`
- `src/api/routers/users.py:42,118,176-177,223-224,314`
- `src/scripts/account_admin.py:32`

---

## 4. Destructive Flows (independently derived from raw mutation inventory)

1. **Delete User** — `DELETE /api/auth/users/{id}` → `auth_users.py:543-756`: 12-table cascade (`db.execute(delete(...))` × ~10 + `db.delete(user)` at 744), commit at 755; last-active-admin guard at 567-575.
2. **Delete Symbol** — `DELETE /api/boards/symbols/{symbol_id}` → `symbols.py:409-429`: `db.delete(symbol)` + commit, then `remove_owned_upload(image_path, ...)` post-commit (line 429).
3. **Replace Symbol Image** — `POST /api/boards/symbols/{symbol_id}/image` → `symbols.py:356-402`: writes new file, on commit failure unlinks new file (396), unlinks old file (402).
4. **Delete Board** — `DELETE /api/boards/{board_id}` → `boards.py:169-216`: `db.delete(db_board)` + commit; cascade via FK.
5. **Reset Password** — `POST /api/users/reset-password` → `users.py:228-315`: `mark_credentials_changed` + commit; revokes sessions.
6. **Import Data (replace)** — `POST /api/data/import` → `export_import.py:767-857`: bulk add + single commit (855); replaces/updates user data.

Plus: **startup repair flows** in `schema.py` (label dedup deletes, `seed.py:473` duplicate delete).

**Conclusion**: the defensible count is **6 destructive flows** (V3 Proof §10) — matching. The "5" figure from earlier summaries omits Import Data. The "16 distinct ops + 1 repair" from the final ledger is a finer-grained enumeration of the same set (each flow's route + its rollback/unlink sub-operations).

---

## 5. Filesystem Mutation Sites (write/delete; 52 broad matches, 9 direct writes)

Direct file writes (9):
- `src/aac_app/services/arasaac_library_import.py:134` (`path.write_bytes`)
- `src/aac_app/services/ngram_builder.py:231` (`open(output_path, "w")`)
- `src/aac_app/services/symbol_image_backfill.py:149` (`file_path.write_bytes`)
- `src/aac_app/services/local_tts_provider.py:408` (`wave.open(buffer, "wb")`)
- `src/api/routers/arasaac.py:109` (`file_path.open("wb")`)
- `src/api/routers/symbols.py:77` (`path.open("wb")`)
- `src/config.py:188,197` (`shutil.copyfile` legacy/example env)
- `src/config.py:263` (`path.write_text` — JWT secret persistence)
- `launcher.pyw:60` (`startup_error.log` write_text)

File deletes (4 + 6 helper calls):
- `os.remove`: `src/aac_app/services/learning/responses.py:517`, `src/api/file_uploads.py:134`, `src/api/routers/learning.py:199`
- `os.unlink`: `src/api/logging_config.py:74`
- `remove_owned_upload` calls: `symbols.py:80,338,396,402,429` (5) + definition `file_uploads.py:177`
- `path.unlink`: `local_vector_store.py:144`, `symbol_image_backfill.py:172`, `file_uploads.py:192`, `arasaac.py:156,162`

---

## 6. External I/O Sites (56 broad matches)

- **httpx clients**: `ollama_provider.py:45,48` (AsyncClient + sync Client), `openrouter_provider.py:25-26`, `arasaac.py:13,24`, `runtime_translation.py:13,50` (client factory + timeout)
- **urllib**: `local_tts_provider.py:267,282` (model download), `launcher.pyw:13-14,148` (readiness poll)
- **subprocess**: `providers.py:398,492` (voice/TTS dependency install)
- **websocket**: `collab.py` (22-229, connection lifecycle)
- **shutil.which**: `providers.py:78,84-85`, `utils/runtime.py:35` (native executable detection)

---

## 7. Provider Implementations (6)

1. `GroqProvider` — `src/aac_app/providers/groq_provider.py`
2. `OllamaProvider` — `src/aac_app/providers/ollama_provider.py`
3. `OpenRouterProvider` — `src/aac_app/providers/openrouter_provider.py`
4. `LMStudioProvider` — `src/aac_app/providers/lmstudio_provider.py`
5. `LocalSpeechProvider` — `src/aac_app/providers/local_speech_provider.py`
6. `LocalTTSProvider` — `src/aac_app/providers/local_tts_provider.py`

All inherit from `BaseLLMProvider` (LLM ones) and implement `close_sync`/`close_async`; `BaseLLMProvider.close` (async alias) at `base_provider.py:110-112`.

---

## 8. Broad Exception Handlers (142) — full raw list

All `except Exception` / bare `except` handlers by file:line (AST scan):

```
src/aac_app/db.py:129
src/aac_app/providers/base_provider.py:55,64,77
src/aac_app/providers/lmstudio_provider.py:42
src/aac_app/providers/local_speech_provider.py:142,183,222
src/aac_app/providers/local_tts_provider.py:121,208,290,392
src/aac_app/providers/ollama_provider.py:37,186
src/aac_app/providers/openrouter_provider.py:51,150,174
src/aac_app/services/achievement_system.py:45,322,330,360,368,465,542,556,621
src/aac_app/services/arasaac.py:70,88,101
src/aac_app/services/audit_service.py:61
src/aac_app/services/board_generation_service.py:176
src/aac_app/services/learning/questions.py:174,262
src/aac_app/services/learning/responses.py:154,319,403,406,424,450,511
src/aac_app/services/learning/service.py:128,208,220
src/aac_app/services/learning/session.py:122,225,259
src/aac_app/services/learning/summaries.py:77
src/aac_app/services/local_vector_store.py:209,243,262,314,344,379,394,453,477,543,577
src/aac_app/services/ngram_builder.py:44,270
src/aac_app/services/prediction_service.py:140,439,482,655,684
src/aac_app/services/runtime_translation.py:98,168
src/aac_app/services/symbol_analytics.py:193
src/aac_app/services/symbol_image_backfill.py:274,313,324
src/aac_app/services/template_manager.py:50
src/aac_app/services/translation_service.py:143
src/aac_app/services/vector_utils.py:147,206,223
src/aac_app/utils/jwt_utils.py:141
src/api/deps/auth.py:62
src/api/deps/db.py:16
src/api/deps/providers.py:101,111,146,237,258,270,280,288,441,691,752,774,807,849,924,1119
src/api/deps/settings.py:26
src/api/file_uploads.py:131
src/api/main.py:77,92,123,150,182,218,245
src/api/routers/admin.py:52
src/api/routers/analytics.py:81,117,279,300,332,361,397
src/api/routers/arasaac.py:53,126,147,158
src/api/routers/board_ai.py:265,285,380
src/api/routers/boards.py:81
src/api/routers/collab.py:42,213,226
src/api/routers/providers.py:337,348,363,421,530
src/api/routers/settings.py:100,329,381,433,478
src/api/routers/symbols.py:144,291,336,342,346,394,400,481
launcher.pyw:41
```

Total: **142**. High-risk samples inspected: `db.py:129` (rollback+log), `jwt_utils.py:141` (token decode → None), `file_uploads.py:131` (unlink temp), `symbols.py:336-346` (commit-fail unlink), `analytics.py:332` (the logSymbolFailed fix), `providers.py` (client teardown), `collab.py:226` (WS close). All log or translate; none silently swallow without a path forward.

---

## 9. Lifecycle Hooks

- `lifespan` in `src/api/main.py` (startup: init DB, schema.ensure, seed, template validation, provider warmup thread, background tasks; shutdown: drain tasks, cancel warmup, close providers)
- `_start_provider_warmup_thread` in `src/api/deps/providers.py`
- Background tasks: `index_task`, `backfill_task`, `arasaac_task`, `ngram_task` (main.py)
- `launcher.pyw` named-event shutdown watcher (`_start_shutdown_watcher` / `_stop_shutdown_watcher`)

---

## 10. Module-Level Mutable State (candidates)

Bare-name mutable objects (9): `db.py:27 _resource_lock=RLock()`, `notification_events.py:80 _subscriber_lock=RLock()`, `prediction_service.py:59 _catalog_lock=RLock()`, `prediction_service.py:61 _catalog_cache=WeakKeyDictionary()`, `symbol_analytics.py:54 _history_transition_lock=RLock()`, `symbol_analytics.py:55 _history_transition_cache=WeakKeyDictionary()`, `symbol_image_backfill.py:290 _scheduled_tasks=set()`, `providers.py:91 _pending_llm_close_tasks=set()`, `settings.py:11 _settings_cache_lock=RLock()`.

Qualified/threading members (additional): `providers.py:61 _startup_lock=threading.Lock()`, `:62 _startup_generation=0`, `:63 _warmup_generation_local=threading.local()`, `:68 _provider_lock=threading.Lock()`, `:74 _speech_release_lock=threading.Lock()`, `runtime_translation.py:13 _translation_client_factory`, `:22 _translation_slots=BoundedSemaphore`, `:28 _consecutive_failures=0`, `:29 _circuit_open_until=0.0`, `:30 _circuit_lock=threading.Lock()`, `local_vector_store.py:47 _engine_listener_lock`, `:51 vector_store_operation_lock=RLock()`.

V3's 16 is a curated subset (excludes scalar counters and factory assignments); rule undocumented.